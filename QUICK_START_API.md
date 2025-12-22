# Quick Start: API Server

## Start the API Server

### Option 1: Use the start script (recommended)
```bash
./start_api.sh
```

### Option 2: Start manually
```bash
python3 api_server.py
```

The server will start on **http://localhost:5001**

## Verify It's Working

1. **Health Check**: Visit http://localhost:5001/api/health
   - Should show database info and transcript count

2. **Test API**: Visit http://localhost:5001/api/transcripts
   - Should return JSON with transcripts

3. **Open Frontend**: Open `analytics_ui.html` in your browser
   - Should load transcripts automatically

## Troubleshooting

### "Database not found" error
- **Cause**: The database file doesn't exist
- **Fix**: Run the scraper to populate it:
  ```bash
  python3 rollcall_sync.py
  ```

### "Loading transcripts..." stuck
- **Cause**: API server not running or wrong port
- **Fix**: 
  1. Check server is running: `lsof -i :5001`
  2. Restart server: `./start_api.sh`
  3. Check browser console (F12) for errors

### "API request timed out"
- **Cause**: Database query taking too long (1000+ transcripts with full text)
- **Fix**: Already optimized in latest version with:
  - Compression enabled
  - Better error handling
  - 30-second timeout

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check with DB info |
| `GET /api/transcripts` | All transcripts WITH full text (large, ~10-30MB) |
| `GET /api/transcripts/metadata` | All transcripts WITHOUT full text (lightweight) |
| `GET /api/transcripts/<id>` | Single transcript by ID |
| `POST /api/scraper/refresh` | Trigger scraper to sync new transcripts |
| `GET /api/scraper/status` | Check scraper status |

## Requirements

```bash
pip install flask flask-cors flask-compress
```

Or use requirements.txt if available:
```bash
pip install -r requirements.txt
```

## Performance Tips

1. **Use compression**: Flask-compress is now enabled (reduces response size by ~70%)
2. **Cache responses**: API sets cache headers (5 minute cache)
3. **Lightweight endpoint**: Use `/api/transcripts/metadata` if you don't need full text immediately


