#!/bin/bash
# Startup script for Mention Market Tool API Server

echo "================================================================================"
echo "MENTION MARKET TOOL - SERVER STARTUP"
echo "================================================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "api_server.py" ]; then
    echo "Error: api_server.py not found!"
    echo "Please run this script from the scraper_python directory"
    exit 1
fi

# Check if database exists
if [ ! -f "data/transcripts.db" ]; then
    echo "⚠️  Warning: Database not found. Creating..."
    python3 database.py
fi

echo "Starting API server on http://localhost:5000"
echo ""
echo "📊 Open in your browser:"
echo "   file://$(pwd)/index.html"
echo ""
echo "Press Ctrl+C to stop the server"
echo "================================================================================"
echo ""

# Start the server
python3 api_server.py
