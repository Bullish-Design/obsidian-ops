#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"

ops-demo run --host "$HOST" --port "$PORT"
