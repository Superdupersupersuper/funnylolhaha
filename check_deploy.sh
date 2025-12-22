#!/bin/bash

echo "🔍 Checking Render Deployment Status"
echo "===================================="
echo ""

echo "📍 Fetching production file..."
PROD_CONTENT=$(curl -s "https://funnylolhaha.onrender.com/analytics_ui.html?v=$(date +%s)" | sed -n '667p')

echo "Line 667 content:"
echo "$PROD_CONTENT"
echo ""

if echo "$PROD_CONTENT" | grep -q "API_BASE declared later with conditional logic"; then
    echo "✅ DEPLOYMENT SUCCESSFUL!"
    echo ""
    echo "The fix is now live on production."
    echo "Test the site: https://funnylolhaha.onrender.com"
    echo ""
    echo "Verification steps:"
    echo "1. Open the site in your browser"
    echo "2. Press F12 to open Developer Tools"
    echo "3. Check Console - should see NO SyntaxError"
    echo "4. Page should load transcripts successfully"
    exit 0
elif echo "$PROD_CONTENT" | grep -q "const API_BASE = '/api'"; then
    echo "⏳ DEPLOYMENT PENDING"
    echo ""
    echo "Production is still serving the old version."
    echo "This is normal for Render Free tier."
    echo ""
    echo "Possible reasons:"
    echo "• Render deployment queue (free tier can be slow)"
    echo "• CDN caching (Cloudflare)"
    echo "• Build in progress"
    echo ""
    echo "What to do:"
    echo "1. Wait another 5-10 minutes"
    echo "2. Run this script again: ./check_deploy.sh"
    echo "3. Or manually trigger deploy at: https://dashboard.render.com"
    exit 1
else
    echo "❓ UNKNOWN STATE"
    echo ""
    echo "Could not determine deployment status."
    echo "Check manually: https://funnylolhaha.onrender.com/analytics_ui.html"
    exit 2
fi


