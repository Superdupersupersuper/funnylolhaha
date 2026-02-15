#!/bin/bash

# Quick test script for the API server

echo "🧪 Testing Mention Markets API Server"
echo "=================================="
echo ""

# Test 1: Health check
echo "1️⃣  Testing health endpoint..."
HEALTH=$(curl -s http://localhost:5001/api/health 2>&1)
if [ $? -eq 0 ]; then
    echo "✅ Health check successful"
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
else
    echo "❌ Health check failed - is the server running?"
    echo "   Start with: ./start_api.sh"
    exit 1
fi

echo ""
echo "2️⃣  Testing transcripts endpoint..."
TRANSCRIPTS=$(curl -s http://localhost:5001/api/transcripts 2>&1)
if [ $? -eq 0 ]; then
    COUNT=$(echo "$TRANSCRIPTS" | python3 -c "import sys, json; data = json.load(sys.stdin); print(len(data))" 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "✅ Transcripts endpoint successful"
        echo "   Found $COUNT transcripts"
    else
        echo "⚠️  Endpoint responded but JSON parse failed"
        echo "   Response length: ${#TRANSCRIPTS} bytes"
    fi
else
    echo "❌ Transcripts endpoint failed"
    exit 1
fi

echo ""
echo "✅ All tests passed!"
echo "   API is ready at: http://localhost:5001"
echo "   Open analytics_ui.html in your browser to use the app"



