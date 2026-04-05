#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
VLLM_BASE_URL="${VLLM_BASE_URL:-http://remora-server:8000/v1}"
VLLM_MODEL="${VLLM_MODEL:-}"
VLLM_API_KEY="${VLLM_API_KEY:-}"

CMD=(ops-demo run --host "$HOST" --port "$PORT" --vllm-base-url "$VLLM_BASE_URL")

if [[ -n "$VLLM_MODEL" ]]; then
  CMD+=(--vllm-model "$VLLM_MODEL")
fi

if [[ -n "$VLLM_API_KEY" ]]; then
  CMD+=(--vllm-api-key "$VLLM_API_KEY")
fi

"${CMD[@]}"
