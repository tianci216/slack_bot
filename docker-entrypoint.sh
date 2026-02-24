#!/bin/bash
set -e

echo "[entrypoint] Installing function dependencies..."
for req in /app/functions/*/requirements.txt; do
    if [ -f "$req" ]; then
        func_name=$(basename "$(dirname "$req")")
        echo "[entrypoint] Installing deps for: $func_name"
        pip install --quiet --no-cache-dir -r "$req"
    fi
done

echo "[entrypoint] Starting bot..."
exec python main.py
