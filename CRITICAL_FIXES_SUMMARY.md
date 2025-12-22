# Critical Fixes - No Transcripts & Sync Timeout

## Issues Fixed

### 1. ✅ **No Transcripts Showing** (CRITICAL)
**Problem**: Database didn't exist on Render, causing API to fail silently

**Solution**:
- Added `init_database_if_needed()` function that auto-creates database schema if missing
- Database now initializes automatically on first API call
- Uses correct schema matching `rollcall_sync.py` expectations

**Files Changed**:
- `api_server.py` - Added database initialization function

### 2. ✅ **API Timeout** (CRITICAL)
**Problem**: Frontend timed out after 30 seconds loading full transcript data

**Solution**:
- Frontend now uses `/api/transcripts/metadata` endpoint first (fast, no full text)
- Falls back to full endpoint if metadata fails
- Increased timeout to 60 seconds for full data
- Background loading of full data after metadata loads

**Files Changed**:
- `index.html` - Updated `loadStaticData()` function
- `analytics_ui.html` - Updated `loadStaticData()` function

### 3. ✅ **Sync Timeout**
**Problem**: Sync operations timing out after 5 minutes

**Solution**:
- Increased Gunicorn timeout to 10 minutes (600 seconds)
- Increased frontend sync timeout to 10 minutes
- Better error messages when timeout occurs

**Files Changed**:
- `gunicorn_config.py` - Increased timeout to 600 seconds
- `index.html` - Increased sync timeout to 600000ms
- `analytics_ui.html` - Increased sync timeout to 600000ms

## Database Schema

The auto-initialized database uses this schema (matching `rollcall_sync.py`):

```sql
CREATE TABLE transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    date DATE NOT NULL,
    speech_type TEXT NOT NULL,
    location TEXT,
    url TEXT UNIQUE NOT NULL,
    word_count INTEGER,
    trump_word_count INTEGER,
    speech_duration_seconds INTEGER,
    full_dialogue TEXT,
    speakers_json TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Deployment Steps

1. **Commit and push changes**:
```bash
git add .
git commit -m "Fix: Auto-create database, use metadata endpoint, increase timeouts"
git push origin main
```

2. **Wait for Render to deploy** (2-5 minutes)

3. **Verify fixes**:
   - Visit https://funnylolhaha.onrender.com/
   - Should see "No Transcripts Available" message (not error)
   - Database will be auto-created
   - Click "Sync Transcripts" to populate

4. **After sync completes**:
   - Transcripts should appear
   - Full text loads in background
   - No more timeout errors

## Expected Behavior

### Before Fix:
- ❌ "API request timed out after 30 seconds"
- ❌ "Database not found" error
- ❌ 0 transcripts showing

### After Fix:
- ✅ Database auto-creates on first API call
- ✅ Metadata loads quickly (< 10 seconds)
- ✅ Full data loads in background
- ✅ Sync has 10-minute timeout
- ✅ Proper error messages if database is empty

## Testing

1. **Check database initialization**:
   - Visit `/api/health` endpoint
   - Should show database exists and transcript count

2. **Test metadata endpoint**:
   - Visit `/api/transcripts/metadata`
   - Should return quickly with transcript list (no full text)

3. **Test full endpoint**:
   - Visit `/api/transcripts`
   - Should return full transcript data (may take longer)

4. **Test sync**:
   - Click "Sync Transcripts" button
   - Should show progress messages
   - Should complete within 10 minutes

## Troubleshooting

### If still seeing 0 transcripts:
1. Check `/api/health` - verify database exists
2. Check Render logs for database initialization messages
3. Manually trigger sync via button

### If sync still times out:
1. Check Render logs for Chrome driver errors
2. Verify `selenium` is installed (check build logs)
3. May need to use alternative scraping method if Chrome unavailable

### If metadata endpoint fails:
- Falls back to full endpoint automatically
- Check browser console for errors
- Verify API server is running

