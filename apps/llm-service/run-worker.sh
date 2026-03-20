#!/usr/bin/env bash
# Ejecuta el worker LLM en segundo plano (usa venv). Log en worker.log
cd "$(dirname "$0")"
PYTHON="python3"
[[ -x venv/bin/python ]] && PYTHON="venv/bin/python"
pkill -f "src.main" 2>/dev/null || true
nohup "$PYTHON" -m src.main >> worker.log 2>&1 &
echo "Worker arrancado. PID: $! (using $PYTHON)"
echo "Ver log: tail -f $(pwd)/worker.log"
