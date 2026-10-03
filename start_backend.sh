#!/bin/bash
# Start the autopay recovery backend server
# Usage: ./start_backend.sh

cd "$(dirname "$0")"

echo "Starting Autopay Recovery Backend..."
echo "Server will run on http://localhost:8080"
echo ""

uv run uvicorn backend.server:app --host 0.0.0.0 --port 8080
