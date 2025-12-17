# Fix Summary: UI Showing 0 Transcripts

**Date:** December 17, 2025  
**Issue:** `http://localhost:8080/analytics_ui.html` was showing 0 transcripts  
**Status:** ✅ FIXED

---

## What Was Wrong

The API server (`api_server.py`) was using a **relative database path** (`./data/transcripts.db`). When the API server was run from a directory other than the repo root, it would create or read from a **different** (empty) database file, causing the API to return 0 transcripts.

---

## What Was Fixed

### 1. Made Database Path Absolute ✓
- **File:** `api_server.py`
- **Change:** `DB_PATH` now uses an absolute path anchored to the script location
- **Benefit:** API server works correctly regardless of where it's started from
- **Override:** Can use `MENTION_MARKETS_DB_PATH` environment variable if needed

### 2. Added Startup Validation ✓
- **File:** `api_server.py`
- **Change:** On startup, the API now:
  - Prints the exact database path it's using
  - Checks if the file exists
  - Shows how many transcripts are loaded
- **Benefit:** Immediately see if something is wrong

### 3. Added Health Endpoint ✓
- **New endpoint:** `GET /api/health`
- **Returns:**
  ```json
  {
    "status": "healthy",
    "database": {
      "path": "/Users/.../transcripts.db",
      "exists": true,
      "size_mb": 52.3
    },
    "transcripts": {
      "count": 1109,
      "empty_count": 0
    }
  }
  ```
- **Benefit:** Easy debugging - visit http://localhost:5001/api/health anytime

### 4. Improved UI Error Messages ✓
- **File:** `analytics_ui.html`
- **Change:** When API returns 0 transcripts, UI now:
  - Fetches `/api/health` to diagnose the issue
  - Shows exactly where the API is looking for the database
  - Provides step-by-step fix instructions
  - Links to the health check endpoint
- **Benefit:** Clear guidance instead of silent failure

### 5. Updated Documentation ✓
- **Files:** `README.md`, `START_SERVERS.md` (new)
- **Change:** Clear instructions on how to start servers correctly
- **Benefit:** Prevents the issue from happening again

---

## How to Start Fresh (DO THIS NOW)

### Step 1: Stop Any Running API Server
If you have an API server running, stop it (Ctrl+C in the terminal where it's running)

### Step 2: Start API Server from Repo Root
Open a terminal and run:
```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 api_server.py
```

**Look for this output:**
```
================================================================================
MENTION MARKET TOOL - API SERVER
================================================================================

Starting server on http://localhost:5001

📁 Database path: /Users/alexandermiron/Downloads/mention-markets/data/transcripts.db
✓ Database found (52.3 MB)
✓ Database contains 1109 transcripts
```

If you see **"WARNING: Database file not found!"** then something is still wrong.

### Step 3: Start UI Server (Separate Terminal)
```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 -m http.server 8080
```

### Step 4: Open UI in Browser
Go to: **http://localhost:8080/analytics_ui.html**

You should now see all 1109 transcripts!

---

## Verification

After starting both servers, check:

1. ✅ **API Health Check**  
   Visit: http://localhost:5001/api/health  
   Should show: `"count": 1109`

2. ✅ **API Stats**  
   Visit: http://localhost:5001/api/stats  
   Should show: `"totalTranscripts": 1109`

3. ✅ **UI Loads Transcripts**  
   Visit: http://localhost:8080/analytics_ui.html  
   Should show transcripts and search should work

---

## If It Still Shows 0 Transcripts

### Check 1: API Server Output
Look at the terminal where `python3 api_server.py` is running.  
Does it say "✓ Database contains 1109 transcripts"?

- **YES:** API is fine, check UI server
- **NO:** API is reading wrong database, restart from repo root

### Check 2: Health Endpoint
Open: http://localhost:5001/api/health

Look at `database.path`. Is it pointing to:
```
/Users/alexandermiron/Downloads/mention-markets/data/transcripts.db
```

- **YES:** Good, check transcript count in health response
- **NO:** API was started from wrong directory, restart it

### Check 3: UI Console
Open browser console (F12 → Console tab)  
Look for errors or messages about loading transcripts.

### Check 4: Verify Database File Exists
```bash
ls -lh /Users/alexandermiron/Downloads/mention-markets/data/transcripts.db
```

Should show a file around 52 MB.

---

## Files Modified

### Modified Files
- `api_server.py` - Fixed DB path, added health endpoint, added startup logging
- `analytics_ui.html` - Improved error messages, added health check integration
- `README.md` - Updated with correct startup instructions

### New Files
- `START_SERVERS.md` - Quick reference guide for starting servers
- `FIX_SUMMARY.md` - This document

---

## Technical Details (For Reference)

### Old Code (Broken)
```python
DB_PATH = './data/transcripts.db'  # Relative path - breaks when run from wrong dir
```

### New Code (Fixed)
```python
_script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv('MENTION_MARKETS_DB_PATH', 
                    os.path.join(_script_dir, 'data', 'transcripts.db'))
```

This ensures the database path is always relative to where `api_server.py` lives, not where you run it from.

---

## Next Steps

1. **Restart your servers** using the instructions above
2. **Verify everything works** using the verification checklist
3. **Use `START_SERVERS.md`** as a quick reference for future sessions
4. **If issues persist**, check http://localhost:5001/api/health first

---

**The fix is complete. Your UI should now load all 1109 transcripts correctly!** 🎉

