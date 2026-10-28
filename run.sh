#!/usr/bin/env bash
set -e

# Setup environment PATH
export PATH="$HOME/.docker/bin:/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================="
echo "                   Starting Knowledge Gateway                    "
echo "================================================================="

# 1. Virtual Environment Bootstrap
if [ ! -d ".venv" ]; then
    echo "[+] Creating virtual environment..."
    python3.13 -m venv .venv || python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

PYTHON=".venv/bin/python"

# 2. Check and compile ONNX model if needed
if [ ! -f "models/reranker.onnx" ]; then
    echo "[+] Exporting local ONNX neural re-ranking model..."
    $PYTHON models/export_onnx_model.py
fi

# 3. Check Docker PostgreSQL and Redis
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "[+] Starting Docker dependencies (PostgreSQL 5433 & Redis 6379)..."
    docker compose -f docker-compose.test.yml up -d postgres redis >/dev/null 2>&1 || true
fi

# 4. Read port from config or environment
PORT="${GATEWAY_PORT:-8080}"
HOST="${GATEWAY_HOST:-0.0.0.0}"

echo ""
echo "================================================================="
echo "  [✓] Knowledge Gateway running on http://localhost:$PORT        "
echo "  [✓] UI Dashboard & Live Tailing: http://localhost:$PORT        "
echo "  [✓] REST API Docs (Swagger): http://localhost:$PORT/docs       "
echo "================================================================="
echo ""

exec .venv/bin/uvicorn src.server:app --host "$HOST" --port "$PORT" --reload
