# Render Sync Fix - Deployment Instructions

## Problem
The sync button on Render wasn't working because:
1. **Missing dependency**: `selenium` was not in `requirements.txt`
2. **Chrome driver initialization**: Needed better fallback strategies for cloud environments

## Changes Made

### 1. Updated `requirements.txt`
- Added `selenium>=4.15.0`
- Added `webdriver-manager>=4.0.0` (auto-manages ChromeDriver)

### 2. Enhanced `rollcall_sync.py`
- Added multiple Chrome driver initialization strategies:
  - Strategy 1: Use `webdriver-manager` (auto-downloads ChromeDriver)
  - Strategy 2: Standard Chrome initialization
  - Strategy 3: Try explicit Chrome binary paths for cloud environments
- Better error logging to help diagnose issues

### 3. All Previous Fixes Still Included
- Robust sort selection (3 fallback strategies)
- Fixed discovery stop condition (won't truncate early)
- Extended date parsing (supports multiple URL formats)

## Deployment Steps

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Fix sync: Add selenium dependency and improve Chrome driver initialization"
git push origin main
```

### Step 2: Wait for Render Auto-Deploy
- Render should automatically detect the push and start deploying
- Check Render dashboard: https://dashboard.render.com
- Look for the `mention-markets-api` service status

### Step 3: Verify Deployment
1. Go to https://funnylolhaha.onrender.com/
2. Open browser console (F12)
3. Check `/api/health` endpoint - should return 200 OK

### Step 4: Test the Sync
1. Click the "⟳ Sync Transcripts" button
2. Watch the button text change to show progress
3. Check browser console for any errors
4. Wait for sync to complete (may take 2-5 minutes)

### Step 5: Check Results
- New transcripts from Dec 19+ should appear
- Check `/api/scraper/status` endpoint to see sync results
- Verify transcripts show up in the UI

## Troubleshooting

### If Sync Still Fails:

**Check Render Logs:**
1. Go to Render dashboard
2. Click on `mention-markets-api` service
3. Click "Logs" tab
4. Look for errors related to:
   - Chrome driver initialization
   - Selenium import errors
   - Database connection issues

**Common Issues:**

1. **"Selenium not available"**
   - Check that `selenium` is in `requirements.txt`
   - Verify Render build logs show `selenium` installing

2. **"Failed to initialize Chrome driver"**
   - Render free tier might not have Chrome installed
   - Check logs for specific Chrome driver error
   - May need to upgrade Render plan or use alternative scraping method

3. **"Database not found"**
   - Check `MENTION_MARKETS_DB_PATH` environment variable
   - Verify database file exists at that path
   - May need to initialize database first

**Check Sync Status:**
```bash
# Via browser console or curl:
curl https://funnylolhaha.onrender.com/api/scraper/status
```

**Manual Sync Trigger:**
```bash
curl -X POST https://funnylolhaha.onrender.com/api/scraper/refresh
```

## Expected Behavior

When sync works correctly:
1. Button shows "⟳ Syncing..." then "Running..."
2. Progress messages appear in button text
3. After completion: "✓ Complete!"
4. New transcripts appear in the UI
5. `/api/scraper/status` shows:
   - `added: X` (new transcripts)
   - `updated: Y` (re-scraped transcripts)
   - `discovered: Z` (total URLs found)

## Next Steps

If sync still doesn't work after these changes:
1. Share Render logs (from dashboard)
2. Share browser console errors
3. Share `/api/scraper/status` response
4. We can investigate further based on specific error messages

