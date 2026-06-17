#!/usr/bin/env bash
# PPTAgent 本地启动脚本
# 用法: ./scripts/run_local.sh [backend|frontend|all]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="$ROOT_DIR/pptagent_ui"

# 激活 conda 环境
if [ -f "$(conda info --base 2>/dev/null)/etc/profile.d/conda.sh" ]; then
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate pptagent
else
  echo "Error: conda not found. Please install conda and create env: conda create -n pptagent python=3.11"
  exit 1
fi

# 加载 .env（若存在）
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
  echo "[Config] Loaded $ROOT_DIR/.env"
else
  echo "[Warning] $ROOT_DIR/.env not found. Copy .env.example to .env and fill in API keys."
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "Error: OPENAI_API_KEY is not set. Create .env from .env.example."
  exit 1
fi

# WebSocket 支持（backend 进度推送必需）
python -c "import websockets" 2>/dev/null || pip install 'uvicorn[standard]' websockets -q

start_backend() {
  echo "[Backend] Starting on http://0.0.0.0:9297"
  cd "$UI_DIR"
  python backend.py
}

start_frontend() {
  echo "[Frontend] Starting on http://localhost:8088"
  cd "$UI_DIR"
  npm run serve
}

case "${1:-all}" in
  backend)
    start_backend
    ;;
  frontend)
    start_frontend
    ;;
  all)
    start_backend &
    BACKEND_PID=$!
    sleep 3
    start_frontend &
    FRONTEND_PID=$!
    trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT
    wait
    ;;
  *)
    echo "Usage: $0 [backend|frontend|all]"
    exit 1
    ;;
esac
