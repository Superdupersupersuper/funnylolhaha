# Scraper Fix Summary - Render Deployment

## Issues Fixed

### 1. **Browser Automation Not Working on Render**
**Problem**: Chrome/ChromeDriver not available on Render's free tier, causing sync to fail silently

**Solution**: 
- Added **Playwright** as primary browser automation (bundles Chromium, works better on cloud)
- Added **Dockerfile** to properly install Chrome in Render environment
- Updated `render.yaml` to use Docker runtime instead of Python runtime
- Added fallback from Playwright → Selenium → Error with detailed messages

### 2. **Better Error Reporting**
**Problem**: Errors were silent, hard to diagnose

**Solution**:
- Added `_last_error` tracking for detailed error messages
- Improved error messages in API status endpoint
- Better logging throughout sync process

### 3. **Code Changes**

**Files Modified**:
- `rollcall_sync.py` - Added Playwright support, improved error handling
- `requirements.txt` - Added `playwright>=1.40.0`
- `render.yaml` - Changed to Docker runtime
- `Dockerfile` - NEW - Installs Chrome and Playwright browsers

**Key Changes**:
1. `_init_driver()` now tries Playwright first, then Selenium
2. `_discover_urls_in_range()` supports both Playwright and Selenium
3. `_parse_transcript_page()` supports both browser types
4. Proper cleanup for both Playwright and Selenium

## Deployment Steps

1. **Commit and push**:
```bash
git add .
git commit -m "Fix: Add Playwright support and Dockerfile for Render deployment"
git push origin main
```

2. **Render will auto-deploy** using the Dockerfile (2-5 minutes)

3. **Test the sync**:
   - Visit https://funnylolhaha.onrender.com/
   - Click "⟳ Sync Transcripts"
   - Check progress messages
   - Verify transcripts from Dec 19+ appear

## Expected Behavior

### Browser Initialization:
1. Tries Playwright first (bundled Chromium)
2. Falls back to Selenium with Chrome
3. Falls back to Selenium with webdriver-manager
4. Shows detailed error if all fail

### Sync Process:
1. Determines sync window (from max DB date to today)
2. Initializes browser (Playwright or Selenium)
3. Discovers URLs from RollCall search page
4. Filters to URLs that need scraping
5. Scrapes each transcript
6. Normalizes and saves to database

## Troubleshooting

### If sync still fails:

**Check Render logs**:
1. Go to Render dashboard
2. Click on `mention-markets-api` service
3. Check "Logs" tab for errors

**Common issues**:
- **"Playwright browsers not installed"**: Run `playwright install chromium` in build
- **"Chrome not found"**: Dockerfile should install it, check build logs
- **"Selenium not available"**: Check requirements.txt includes selenium

**Check sync status**:
```bash
curl https://funnylolhaha.onrender.com/api/scraper/status
```

Look for:
- `error`: Detailed error message
- `progress`: Current sync step
- `discovered`: Number of URLs found
- `added`: New transcripts added

## Testing

After deployment, verify:
1. ✅ Browser initializes (check logs for "Browser initialized via Playwright" or "Chrome driver initialized")
2. ✅ URLs are discovered (check `discovered` count > 0)
3. ✅ Transcripts are scraped (check `added` count > 0)
4. ✅ New transcripts appear in UI (Dec 19+)
5. ✅ Transcripts have correct format (normalized `full_dialogue`)

