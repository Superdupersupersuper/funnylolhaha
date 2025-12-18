#!/bin/bash
# Start the MentionMarkets Analytics Engine

echo "================================================================================"
echo "🚀 MENTIONMARKETS ANALYTICS ENGINE"
echo "================================================================================"
echo ""
echo "Starting API server on http://localhost:5001"
echo "Opening analytics interface in browser..."
echo ""
echo "Current database status:"
sqlite3 data/transcripts.db "SELECT COUNT(*) || ' transcripts from ' || MIN(date) || ' to ' || MAX(date) FROM transcripts WHERE date LIKE '____-__-__';"
echo ""
echo "Press Ctrl+C to stop"
echo "================================================================================"
echo ""

# Start API server
python3 analytics_api.py &
API_PID=$!

# Wait for server to start
sleep 3

# Open browser
open analytics_ui.html

# Wait for Ctrl+C
wait $API_PID
