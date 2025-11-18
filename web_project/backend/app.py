import asyncio
import logging
import os
import shutil
import tempfile
import time
from functools import partial
from pathlib import Path
from typing import Any, Dict, Tuple

import torch
import uvicorn
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from transformers import AutoModel, AutoTokenizer

LOGGER = logging.getLogger("deepseek_ocr_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_PROMPT = os.getenv(
    "DEEPSEEK_OCR_DEFAULT_PROMPT",
    "<image>\n<|grounding|>Convert the document to markdown.",
)
MAX_IMAGE_SIZE_MB = float(os.getenv("DEEPSEEK_MAX_IMAGE_MB", "15"))
MAX_IMAGE_BYTES = int(MAX_IMAGE_SIZE_MB * 1024 * 1024)

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


class OCRResponse(BaseModel):
    mode: str
    prompt: str
    text: str
    rawText: str
    durationMs: float
    fileName: str
    fileSize: int


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
    )

    torch.set_grad_enabled(False)
    model = model.eval().cuda().to(torch.bfloat16)
    runtime["tokenizer"] = tokenizer
    runtime["model"] = model
    LOGGER.info("DeepSeek-OCR is ready.")


def _run_inference(image_path: Path, mode_key: str, prompt: str, output_dir: Path) -> str:
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

    return _clean_prediction(outputs)


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
) -> OCRResponse:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="仅支持图片文件。")

    prompt_value = _ensure_prompt_has_image(prompt)
    tmp_image, file_size = await _save_upload_to_tmp(image)
    output_dir = tmp_image.parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    start = time.perf_counter()
    try:
        async with inference_lock:
            text = await run_in_threadpool(
                partial(_run_inference, tmp_image, mode, prompt_value, output_dir)
            )
    finally:
        shutil.rmtree(tmp_image.parent, ignore_errors=True)

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    raw_text = text

    return OCRResponse(
        mode=mode,
        prompt=prompt_value,
        text=text,
        rawText=raw_text,
        durationMs=duration_ms,
        fileName=image.filename or "image",
        fileSize=file_size,
    )


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=bool(os.getenv("DEV_RELOAD", "0") == "1"),
    )
