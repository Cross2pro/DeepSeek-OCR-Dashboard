import ast
import asyncio
import base64
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from functools import partial
from pathlib import Path
from typing import Any, Dict, Tuple, Optional, List

import torch
import uvicorn
import fitz
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from transformers import AutoModel, AutoTokenizer
from PIL import Image, ImageOps

LOGGER = logging.getLogger("deepseek_ocr_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_PROMPT = os.getenv(
    "DEEPSEEK_OCR_DEFAULT_PROMPT",
    "<image>\n<|grounding|>Convert the document to markdown.",
)
MAX_IMAGE_SIZE_MB = float(os.getenv("DEEPSEEK_MAX_IMAGE_MB", "15"))
MAX_IMAGE_BYTES = int(MAX_IMAGE_SIZE_MB * 1024 * 1024)
REF_PATTERN = re.compile(r"(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)", re.DOTALL)

MODE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "gundam": {
        "label": "Gundam (动态裁剪)",
        "description": "默认模式，使用640分辨率局部裁剪，适合复杂排版。",
        "base_size": 1024,
        "image_size": 640,
        "crop_mode": True,
        "test_compress": True,
        "speed": "中等",
        "quality": "更高",
    },
    "base": {
        "label": "Base 1024",
        "description": "固定1024分辨率，不裁剪，兼顾速度和效果。",
        "base_size": 1024,
        "image_size": 1024,
        "crop_mode": False,
        "test_compress": False,
        "speed": "中等",
        "quality": "高",
    },
    "small": {
        "label": "Small 640",
        "description": "固定640分辨率，不裁剪，速度较快。",
        "base_size": 640,
        "image_size": 640,
        "crop_mode": False,
        "test_compress": False,
        "speed": "较快",
        "quality": "中等",
    },
    "tiny": {
        "label": "Tiny 512",
        "description": "512基础尺寸，适合快速粗略浏览。",
        "base_size": 512,
        "image_size": 512,
        "crop_mode": False,
        "test_compress": False,
        "speed": "最快",
        "quality": "基础",
    },
    "large": {
        "label": "Large 1280",
        "description": "1280基础尺寸，追求极致细节，需要更久推理时间。",
        "base_size": 1280,
        "image_size": 1280,
        "crop_mode": False,
        "test_compress": False,
        "speed": "最慢",
        "quality": "最高",
    },
}


class ModesResponse(BaseModel):
    defaultPrompt: str
    modes: Dict[str, Dict[str, Any]]
    maxImageMb: float


class OCRPage(BaseModel):
    pageIndex: int
    text: str
    rawText: str
    layout: Optional[Dict[str, Any]] = None
    imageData: Optional[str] = None
    durationMs: Optional[float] = None


class OCRResponse(BaseModel):
    mode: str
    prompt: str
    text: str
    rawText: str
    durationMs: float
    fileName: str
    fileSize: int
    layout: Optional[Dict[str, Any]] = None
    pages: List[OCRPage]


allowed_origin_values = [
    origin.strip()
    for origin in os.getenv("DEEPSEEK_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
if not allowed_origin_values:
    allowed_origin_values = ["*"]

app = FastAPI(title="DeepSeek OCR Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origin_values,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

runtime: Dict[str, Any] = {"model": None, "tokenizer": None}
runtime_lock = asyncio.Lock()
inference_lock = asyncio.Lock()

# 进度跟踪
progress_store: Dict[str, Dict[str, Any]] = {}


def _model_dir() -> Path:
    default_path = Path(__file__).resolve().parents[2] / "ocr_project" / "model"
    override = os.getenv("DEEPSEEK_OCR_MODEL_PATH")
    target = Path(override).expanduser() if override else default_path
    if not target.exists():
        raise RuntimeError(f"模型路径不存在: {target}")
    return target


def _output_root() -> Path:
    root = Path(os.getenv("DEEPSEEK_OCR_RUNS_DIR", Path(__file__).resolve().parent / "runs"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ensure_prompt_has_image(prompt: str) -> str:
    prompt = prompt.strip() or DEFAULT_PROMPT
    return prompt if "<image>" in prompt else f"<image>\n{prompt}"


def _clean_prediction(text: str) -> str:
    if not text:
        return ""
    cleaned = text.replace("<｜end▁of▁sentence｜>", "")
    cleaned = cleaned.replace("<|end_of_text|>", "")
    return cleaned.strip()


def _build_layout_metadata(raw_text: str, image_path: Path) -> Dict[str, Any]:
    if not raw_text:
        return {"width": None, "height": None, "items": []}

    try:
        with Image.open(image_path) as img:
            image = ImageOps.exif_transpose(img)
            width, height = image.size
    except Exception as exc:
        LOGGER.warning("Unable to load %s for layout extraction: %s", image_path, exc)
        return {"width": None, "height": None, "items": []}

    matches = REF_PATTERN.findall(raw_text)
    layout_items = []
    for idx, match in enumerate(matches):
        label_type = match[1]
        coords_literal = match[2]
        try:
            coords = ast.literal_eval(coords_literal)
        except Exception:
            continue

        if not isinstance(coords, (list, tuple)):
            continue

        boxes = []
        for box_idx, coords_entry in enumerate(coords):
            if not isinstance(coords_entry, (list, tuple)) or len(coords_entry) != 4:
                continue
            x1, y1, x2, y2 = coords_entry
            try:
                abs_x1 = int(max(0, min(999, float(x1))) / 999 * width)
                abs_y1 = int(max(0, min(999, float(y1))) / 999 * height)
                abs_x2 = int(max(0, min(999, float(x2))) / 999 * width)
                abs_y2 = int(max(0, min(999, float(y2))) / 999 * height)
            except Exception:
                continue

            abs_x2 = max(abs_x2, abs_x1 + 1)
            abs_y2 = max(abs_y2, abs_y1 + 1)

            boxes.append(
                {
                    "index": box_idx,
                    "absolute": [abs_x1, abs_y1, abs_x2, abs_y2],
                    "normalized": [
                        round(abs_x1 / width, 6) if width else 0.0,
                        round(abs_y1 / height, 6) if height else 0.0,
                        round(abs_x2 / width, 6) if width else 0.0,
                        round(abs_y2 / height, 6) if height else 0.0,
                    ],
                }
            )

        if boxes:
            layout_items.append(
                {
                    "id": f"{label_type}-{idx}",
                    "label": label_type,
                    "boxes": boxes,
                }
            )

    return {"width": width, "height": height, "items": layout_items}


def _convert_pdf_to_images(pdf_path: Path, target_dir: Path, scale: float = 2.0) -> List[Path]:
    page_dir = target_dir / "pages"
    page_dir.mkdir(exist_ok=True)

    doc = fitz.open(pdf_path)
    image_paths: List[Path] = []
    matrix = fitz.Matrix(scale, scale)
    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image_path = page_dir / f"page_{page_index + 1}.png"
        pix.save(str(image_path))
        image_paths.append(image_path)
    return image_paths


def _encode_image_to_data_url(image_path: Path) -> str:
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime = mime_map.get(image_path.suffix.lower(), "image/png")
    with image_path.open("rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _load_runtime() -> None:
    if torch.cuda.is_available() is False:
        raise RuntimeError("DeepSeek-OCR 推理需要 CUDA GPU，但当前环境未检测到。")
    if runtime["model"] is not None:
        return

    model_path = _model_dir()
    LOGGER.info("Loading DeepSeek-OCR from %s", model_path)

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

    attn_impl = os.getenv("DEEPSEEK_ATTN_IMPL") or "flash_attention_2"
    model = AutoModel.from_pretrained(
        model_path,
        _attn_implementation=attn_impl,
        trust_remote_code=True,
        use_safetensors=True,
        torch_dtype=torch.bfloat16,
        device_map="cuda",
    )

    torch.set_grad_enabled(False)
    model = model.eval()
    runtime["tokenizer"] = tokenizer
    runtime["model"] = model
    LOGGER.info("DeepSeek-OCR is ready.")


def _run_inference(
    image_path: Path, mode_key: str, prompt: str, output_dir: Path
) -> Tuple[str, str, Dict[str, Any]]:
    config = MODE_CONFIGS.get(mode_key)
    if config is None:
        raise ValueError(f"不支持的模式: {mode_key}")

    tokenizer = runtime["tokenizer"]
    model = runtime["model"]
    if tokenizer is None or model is None:
        raise RuntimeError("模型尚未加载完成。")

    outputs = model.infer(
        tokenizer,
        prompt=prompt,
        image_file=str(image_path),
        output_path=str(output_dir),
        base_size=config["base_size"],
        image_size=config["image_size"],
        crop_mode=config["crop_mode"],
        test_compress=config["test_compress"],
        save_results=False,
        eval_mode=True,
    )

    if outputs is None:
        raise RuntimeError("推理返回为空。")

    raw_text = outputs
    cleaned_text = _clean_prediction(raw_text)
    layout = _build_layout_metadata(raw_text, image_path)
    return cleaned_text, raw_text, layout


async def _save_upload_to_tmp(upload: UploadFile) -> Tuple[Path, int]:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="请选择需要识别的图片。")
    suffix = Path(upload.filename).suffix or ".png"
    tmp_dir = Path(tempfile.mkdtemp(prefix="deepseek_ocr_", dir=_output_root()))
    tmp_path = tmp_dir / f"input{suffix}"
    size = 0
    try:
        upload.file.seek(0)
        # Avoid reading unbounded content into memory.
        with tmp_path.open("wb") as buffer:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"图片体积超过限制（{MAX_IMAGE_SIZE_MB:.1f} MB）。",
                    )
                buffer.write(chunk)
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"保存图片失败: {exc}") from exc
    finally:
        upload.file.seek(0)

    return tmp_path, size


@app.on_event("startup")
async def startup_event() -> None:
    async with runtime_lock:
        await run_in_threadpool(_load_runtime)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "modelLoaded": runtime["model"] is not None,
        "modes": list(MODE_CONFIGS.keys()),
    }


@app.get("/api/modes", response_model=ModesResponse)
async def list_modes() -> ModesResponse:
    return ModesResponse(
        defaultPrompt=DEFAULT_PROMPT,
        modes=MODE_CONFIGS,
        maxImageMb=MAX_IMAGE_SIZE_MB,
    )


@app.post("/api/ocr", response_model=OCRResponse)
async def run_ocr(
    image: UploadFile = File(...),
    mode: str = Form("gundam"),
    prompt: str = Form(DEFAULT_PROMPT),
    task_id: str = Form(None),
) -> OCRResponse:
    # 如果提供了 task_id，则更新进度
    def update_progress(stage: str, current: int, total: int, message: str):
        if task_id and task_id in progress_store:
            progress_store[task_id].update({
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
                "percent": int((current / total) * 100) if total > 0 else 0,
            })

    filename = image.filename or "upload"
    suffix = Path(filename).suffix.lower()
    content_type = image.content_type or ""
    is_pdf = suffix == ".pdf" or content_type == "application/pdf"
    if not is_pdf and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="仅支持图片或 PDF 文件。")

    if task_id:
        progress_store[task_id] = {
            "stage": "upload",
            "current": 0,
            "total": 100,
            "message": "正在保存上传文件...",
            "percent": 0,
        }

    prompt_value = _ensure_prompt_has_image(prompt)
    tmp_file, file_size = await _save_upload_to_tmp(image)
    output_dir = tmp_file.parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    if task_id:
        update_progress("preprocessing", 10, 100, "文件上传完成，正在预处理...")

    if is_pdf:
        page_paths = _convert_pdf_to_images(tmp_file, tmp_file.parent)
        if not page_paths:
            raise HTTPException(status_code=400, detail="无法解析 PDF 文件内容。")
        if task_id:
            update_progress("preprocessing", 20, 100, f"PDF 已拆分为 {len(page_paths)} 页")
    else:
        page_paths = [tmp_file]

    start = time.perf_counter()
    page_results: List[Dict[str, Any]] = []
    aggregate_texts: List[str] = []
    aggregate_raw: List[str] = []
    total_pages = len(page_paths)

    try:
        async with inference_lock:
            for idx, page_path in enumerate(page_paths):
                # 更新进度: 推理阶段占 20%-90%
                if task_id:
                    base_progress = 20
                    inference_range = 70  # 20% - 90%
                    page_progress = base_progress + int((idx / total_pages) * inference_range)
                    update_progress(
                        "inference",
                        page_progress,
                        100,
                        f"正在识别第 {idx + 1}/{total_pages} 页..."
                    )

                single_start = time.perf_counter()
                text, raw_text, layout = await run_in_threadpool(
                    partial(_run_inference, page_path, mode, prompt_value, output_dir)
                )
                single_duration = round((time.perf_counter() - single_start) * 1000, 2)

                image_data = _encode_image_to_data_url(page_path) if is_pdf else None

                page_results.append(
                    {
                        "pageIndex": idx,
                        "text": text,
                        "rawText": raw_text,
                        "layout": layout,
                        "imageData": image_data,
                        "durationMs": single_duration,
                    }
                )
                aggregate_raw.append(f"[Page {idx + 1}]\n{raw_text}".strip())
                aggregate_texts.append(f"## 第 {idx + 1} 页\n{text}".strip())

                # 更新单页完成进度
                if task_id:
                    page_done_progress = base_progress + int(((idx + 1) / total_pages) * inference_range)
                    update_progress(
                        "inference",
                        page_done_progress,
                        100,
                        f"第 {idx + 1}/{total_pages} 页识别完成"
                    )
    finally:
        shutil.rmtree(tmp_file.parent, ignore_errors=True)

    if task_id:
        update_progress("postprocessing", 95, 100, "正在整理结果...")

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    layout = page_results[0]["layout"] if page_results else None
    aggregate_text = "\n\n".join(aggregate_texts) if aggregate_texts else ""
    aggregate_raw_text = "\n\n".join(aggregate_raw) if aggregate_raw else ""

    pages_payload = [
        OCRPage(
            pageIndex=page["pageIndex"],
            text=page["text"],
            rawText=page["rawText"],
            layout=page["layout"],
            imageData=page["imageData"],
            durationMs=page.get("durationMs"),
        )
        for page in page_results
    ]

    if task_id:
        update_progress("complete", 100, 100, "识别完成！")
        # 清理进度记录（延迟清理，给前端时间获取最终状态）
        asyncio.get_event_loop().call_later(60, lambda: progress_store.pop(task_id, None))

    return OCRResponse(
        mode=mode,
        prompt=prompt_value,
        text=aggregate_text or page_results[0]["text"],
        rawText=aggregate_raw_text or page_results[0]["rawText"],
        durationMs=duration_ms,
        fileName=filename,
        fileSize=file_size,
        layout=layout,
        pages=pages_payload,
    )


@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    """SSE 端点，用于实时推送推理进度"""
    async def event_generator():
        last_state = None
        no_change_count = 0
        max_no_change = 300  # 最多等待 5 分钟（300 秒）

        while True:
            if task_id in progress_store:
                current_state = progress_store[task_id].copy()
                if current_state != last_state:
                    last_state = current_state
                    no_change_count = 0
                    yield f"data: {json.dumps(current_state, ensure_ascii=False)}\n\n"
                    
                    # 如果已完成，发送完成事件后结束
                    if current_state.get("stage") == "complete":
                        yield f"event: complete\ndata: {json.dumps(current_state, ensure_ascii=False)}\n\n"
                        break
                else:
                    no_change_count += 1
            else:
                no_change_count += 1
            
            # 超时退出
            if no_change_count >= max_no_change:
                yield f"event: timeout\ndata: {json.dumps({'message': '连接超时'}, ensure_ascii=False)}\n\n"
                break
            
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/task/create")
async def create_task() -> Dict[str, str]:
    """创建新的任务 ID"""
    task_id = str(uuid.uuid4())
    progress_store[task_id] = {
        "stage": "pending",
        "current": 0,
        "total": 100,
        "message": "等待开始...",
        "percent": 0,
    }
    return {"taskId": task_id}


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=bool(os.getenv("DEV_RELOAD", "0") == "1"),
    )
