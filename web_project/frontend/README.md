# DeepSeek-OCR Frontend

Vue 3 + Vite single-page app that guides users through the OCR workflow:

1. 上传/拖拽图片
2. 选择推理模式
3. 配置提示词并触发 FastAPI 推理接口

The UI expects the backend to expose the FastAPI endpoints from `../backend/app.py`.

## Configuration

- `VITE_API_BASE_URL` – defaults to `http://localhost:8000`. Point it to wherever the FastAPI server runs.
- `VITE_MAX_IMAGE_MB` – optional override for the upload hint shown in the UI. The real limit still comes from the backend response.

Create a local `.env` if needed:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Getting Started

```bash
cd web_project/frontend
npm install
npm run dev
```

Production build:

```bash
npm run build
```
