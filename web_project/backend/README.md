# DeepSeek-OCR FastAPI Backend

This service loads the local `DeepSeek-OCR` Hugging Face weights once and exposes a lightweight HTTP API for the web frontend.

## Requirements

- Python ≥ 3.10
- CUDA-capable GPU (the upstream `model.infer` implementation uses `.cuda()` internally)
- The DeepSeek-OCR weights extracted under `ocr_project/model`
- PyTorch with CUDA support that matches your driver (install via the wheels provided in `../wheels` or from the official download page)

## Install

```bash
cd web_project/backend
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
# Install PyTorch separately if needed, e.g.
# pip install --no-index --find-links ../../wheels torch torchvision
pip install -r requirements.txt
```

> **Note**  
> `torch` itself is not pinned inside `requirements.txt` so you can pick the correct CUDA build for your machine.

## Run

```bash
cd web_project/backend
uvicorn app:app --host 0.0.0.0 --port 8000
```

or simply use the repository level `./start.sh`, which launches both the backend and the Vite dev server.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `DEEPSEEK_OCR_MODEL_PATH` | `../../ocr_project/model` | Where the tokenizer + weights live |
| `DEEPSEEK_ATTN_IMPL` | `flash_attention_2` | Forwarded to `AutoModel.from_pretrained` |
| `DEEPSEEK_ALLOWED_ORIGINS` | `*` | CORS allow-list (comma separated) |
| `DEEPSEEK_MAX_IMAGE_MB` | `15` | Upload guardrail, also returned to the frontend |
| `DEEPSEEK_OCR_DEFAULT_PROMPT` | `<image>\n<|grounding|>Convert the document to markdown.` | Default SFT prompt |
| `DEEPSEEK_OCR_RUNS_DIR` | `backend/runs` | Temporary folder for uploads + outputs |

## API

- `GET /health` – quick status check
- `GET /api/modes` – mode metadata + default prompt and upload limit
- `POST /api/ocr` *(multipart form)* – fields: `image` (file), `mode`, `prompt`

Response payload:

```json
{
  "mode": "gundam",
  "prompt": "<image>\\n<|grounding|>Convert the document to markdown.",
  "text": "...cleaned text...",
  "rawText": "...raw model output...",
  "durationMs": 2310.5,
  "fileName": "math.png",
  "fileSize": 184832
}
```

All inference requests are serialized through an `asyncio.Lock` to avoid OOM when multiple clients hit the GPU simultaneously.
