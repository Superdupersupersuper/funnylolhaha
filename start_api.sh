#!/bin/bash

# Start the Mention Markets API Server
# This script checks if the server is already running and starts it if not

PORT=5001
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔍 Checking if API server is already running on port $PORT..."

# Check if port is in use
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✅ API server is already running on port $PORT"
    echo "   Visit: http://localhost:$PORT/api/health"
    exit 0
fi

echo "🚀 Starting API server..."
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "   Using virtual environment: venv"
    source venv/bin/activate
fi

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install flask flask-cors flask-compress
fi

# Start the server
echo "   Server will be available at: http://localhost:$PORT"
echo "   Press Ctrl+C to stop"
echo ""

python3 api_server.py
