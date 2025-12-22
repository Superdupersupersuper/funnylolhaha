#!/bin/bash

echo "🚀 Deploying fix for duplicate API_BASE declaration"
echo "=================================================="
echo ""

# Check if we have uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "⚠️  You have uncommitted changes. Committing them now..."
    git add index.html analytics_ui.html
    git commit -m "Fix duplicate API_BASE declaration in index.html and analytics_ui.html"
fi

# Check if we're ahead of origin
AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null)
if [ "$AHEAD" -gt 0 ]; then
    echo "📤 You have $AHEAD commit(s) to push"
    echo "   Attempting to push to origin/main..."
    echo ""
    
    if git push origin main; then
        echo ""
        echo "✅ Successfully pushed to GitHub!"
        echo "   Render should auto-deploy in ~2-3 minutes"
        echo "   Monitor deployment at: https://dashboard.render.com"
        echo ""
        echo "🌐 Production site: https://funnylolhaha.onrender.com"
        echo ""
        echo "Wait 2-3 minutes, then test:"
        echo "   1. Open https://funnylolhaha.onrender.com in your browser"
        echo "   2. Open Developer Tools (F12)"
        echo "   3. Check Console - no SyntaxError should appear"
        echo "   4. Page should load transcripts successfully"
        exit 0
    else
        echo ""
        echo "❌ Push failed. This usually means:"
        echo "   1. You need to authenticate with GitHub"
        echo "   2. You don't have push access to the repository"
        echo ""
        echo "📋 Manual push instructions:"
        echo "   Run: git push origin main"
        echo "   You may be prompted for GitHub credentials"
        echo ""
        exit 1
    fi
else
    echo "✅ Already up to date with origin/main"
    echo "   Nothing to push!"
    exit 0
fi


