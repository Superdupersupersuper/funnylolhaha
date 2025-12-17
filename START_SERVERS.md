# How to Start the Local Development Environment

## Quick Start (Two Terminal Windows)

### Terminal 1: API Server
```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 api_server.py
```

**What to look for:**
- Should say "✓ Database found (XX MB)"
- Should say "✓ Database contains 1109 transcripts"
- If it says "WARNING: Database file not found!" then the path is wrong

### Terminal 2: UI Server
```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 -m http.server 8080
```

### Open Your Browser
Go to: **http://localhost:8080/analytics_ui.html**

---

## If You See "0 Transcripts" or Errors

### Step 1: Check API Health
Open in browser: http://localhost:5001/api/health

This will show you:
- Where the API is looking for the database
- Whether the database file exists
- How many transcripts are in it

### Step 2: Verify Database Path
The database should be at:
```
/Users/alexandermiron/Downloads/mention-markets/data/transcripts.db
```

If the API is looking somewhere else, you started it from the wrong directory!

### Step 3: Restart API from Correct Location
1. Stop the API server (Ctrl+C)
2. Make sure you're in the right directory:
   ```bash
   cd /Users/alexandermiron/Downloads/mention-markets
   pwd  # Should show: /Users/alexandermiron/Downloads/mention-markets
   ```
3. Start it again:
   ```bash
   python3 api_server.py
   ```

---

## Verification Checklist

After starting both servers:

- [ ] API server console shows: "✓ Database contains 1109 transcripts"
- [ ] http://localhost:5001/api/health shows `"count": 1109`
- [ ] http://localhost:5001/api/stats shows `"totalTranscripts": 1109`
- [ ] http://localhost:8080/analytics_ui.html loads transcripts

---

## Common Issues

### Issue: "Cannot connect to API"
**Solution:** Make sure the API server is running in Terminal 1

### Issue: "0 transcripts available"
**Solution:** 
1. Check http://localhost:5001/api/health
2. Look at API server console for database path
3. Restart API from repo root directory

### Issue: Port 5001 already in use
**Solution:**
```bash
# Find what's using port 5001
lsof -i :5001

# Kill it (replace PID with the number shown)
kill PID
```

### Issue: Port 8080 already in use
**Solution:** Use a different port:
```bash
python3 -m http.server 8888
# Then visit http://localhost:8888/analytics_ui.html
```

---

## Environment Variable Override

If you need to use a different database location:
```bash
export MENTION_MARKETS_DB_PATH="/path/to/your/transcripts.db"
python3 api_server.py
```

