#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
export OPENROUTER_API_KEY=''
.venv/bin/python -c 'import onnx; onnx.checker.check_model(onnx.load("models/reranker.onnx"))'
if [ "${1:-}" = --integration ]; then
  export KG_RUN_INTEGRATION=1
  docker compose -p kg-validation -f docker-compose.test.yml up -d --wait
  trap 'docker compose -p kg-validation -f docker-compose.test.yml down' EXIT
  .venv/bin/python -m pytest -q
else
  .venv/bin/python -m pytest -q -m 'not integration'
fi
