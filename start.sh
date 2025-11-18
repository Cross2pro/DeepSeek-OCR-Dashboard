#!/bin/bash

set -euo pipefail

BACKEND_PORT=${OCR_BACKEND_PORT:-8000}
BACKEND_DIR="/home/remote/lee/documents/projects/ds-OCR/web_project/backend"
FRONTEND_DIR="/home/remote/lee/documents/projects/ds-OCR/web_project/frontend"

launch_backend() {
  if command -v uvicorn >/dev/null 2>&1; then
    uvicorn app:app --host 0.0.0.0 --port "${BACKEND_PORT}"
    return
  fi

  if command -v python3 >/dev/null 2>&1 && python3 -c "import uvicorn" >/dev/null 2>&1; then
    python3 -m uvicorn app:app --host 0.0.0.0 --port "${BACKEND_PORT}"
    return
  fi

  if command -v python >/dev/null 2>&1 && python -c "import uvicorn" >/dev/null 2>&1; then
    python -m uvicorn app:app --host 0.0.0.0 --port "${BACKEND_PORT}"
    return
  fi

  echo "未检测到 uvicorn，请先执行 'pip install -r web_project/backend/requirements.txt' 并确认当前 shell 激活了相应虚拟环境。"
  exit 1
}

echo "Starting FastAPI backend on port ${BACKEND_PORT}..."
(
  cd "${BACKEND_DIR}"
  launch_backend
) &
BACKEND_PID=$!

echo "Starting frontend..."
(
  cd "${FRONTEND_DIR}"
  npm run dev
) &
FRONTEND_PID=$!

trap 'kill ${BACKEND_PID} ${FRONTEND_PID}' INT TERM

echo "Web project started. Frontend: http://localhost:5173  Backend: http://localhost:${BACKEND_PORT}"
wait
