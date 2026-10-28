#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
export KNOWLEDGE_GATEWAY_CONFIG="${KNOWLEDGE_GATEWAY_CONFIG:-config.demo.yaml}"
read -r configured_host configured_port < <(.venv/bin/python -c 'from src.config import load_config; c=load_config(); print(c.gateway.host, c.gateway.port)')
args=(src.server:app --host "${GATEWAY_HOST:-$configured_host}" --port "${GATEWAY_PORT:-$configured_port}")
if [ -f .env ]; then args+=(--env-file .env); fi
if [ "${GATEWAY_RELOAD:-0}" = 1 ]; then args+=(--reload); fi
exec .venv/bin/python -m uvicorn "${args[@]}"
