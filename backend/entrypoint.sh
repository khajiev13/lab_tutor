#!/bin/bash
set -e

# Enable reload if UVICORN_RELOAD environment variable is set
if [ "$UVICORN_RELOAD" = "true" ]; then
    echo "Starting uvicorn with hot reload enabled..."
    exec /app/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload
else
    echo "Starting uvicorn in production mode..."
    exec /app/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
fi

