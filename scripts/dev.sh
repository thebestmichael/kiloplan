#!/usr/bin/env bash
# Starts everything KiloPlan needs for local use: the API, the frontend and Ollama.
# Run from anywhere: ./scripts/dev.sh    Stop with Ctrl+C.
set -euo pipefail

cd "$(dirname "$0")/.."

export PATH="$HOME/.local/bin:$HOME/.local/ollama/bin:$PATH"

pids=()

stop() {
    trap - INT TERM EXIT
    echo
    echo "Stopping..."
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap stop INT TERM EXIT

in_use() {
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

start() {
    local name=$1 port=$2
    shift 2
    if in_use "$port"; then
        echo "$name: already running on port $port, left as it is"
        return
    fi
    echo "$name: starting on port $port"
    "$@" &
    pids+=($!)
}

if ! command -v uv >/dev/null; then
    echo "uv is not installed. See https://docs.astral.sh/uv/" >&2
    exit 1
fi
if [ ! -d frontend/node_modules ]; then
    echo "Installing frontend dependencies..."
    (cd frontend && npm install)
fi

start "API" 8000 uv run uvicorn kiloplan.api.main:app --reload --port 8000
start "Frontend" 5173 npm --prefix frontend run dev -- --port 5173 --strictPort
if command -v ollama >/dev/null; then
    start "Ollama" 11434 ollama serve
else
    echo "Ollama: not installed, so the assistant will not answer (https://ollama.com)"
fi

echo
echo "KiloPlan is at http://localhost:5173  (Ctrl+C to stop)"

if [ ${#pids[@]} -eq 0 ]; then
    echo "Everything was already running; nothing for this script to manage."
    trap - INT TERM EXIT
    exit 0
fi
wait
