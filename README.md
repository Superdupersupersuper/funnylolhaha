# Mention Markets

**Transcript Intelligence System for Political Speeches**

A searchable database of political speech transcripts from Factbase/Roll Call with full-text search, analytics, and a retro-styled terminal interface.

## Features

- 🔍 **Full-text search** across all transcript segments
- 📊 **Analytics** - Track mention frequency by speaker, event type, and time
- 🎯 **Filters** - Filter by speaker, event type, and date range
- 📝 **Transcript viewer** - Read full transcripts with speaker highlighting
- 🖥️ **Retro terminal UI** - Clean, monospace, data-focused design

## Speakers Tracked

- **Donald Trump** - Rallies, speeches, remarks
- **JD Vance** - Speeches, interviews, appearances
- **Karoline Leavitt** - White House press briefings
- (Expandable to Biden, Harris, and others)

## Current Workflow (Active Scripts)

**Primary entrypoints** (root directory):
- `api_server.py` - Main API server (port 5001)
- `rollcall_scraper_robust.py` - Production scraper with retry logic
- `analytics_ui.html` - Main frontend UI

**Legacy scripts** (for reference only):
- `backend/server.py` - Old API server (port 5000) - not actively used
- `backend/scraper.py` - Old scraper - replaced by rollcall_scraper_robust.py

## Quick Start

### 1. Install dependencies

```bash
pip install flask flask-cors selenium beautifulsoup4 lxml
```

### 2. Start the API server

**IMPORTANT:** Always run from the repo root directory!

```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 api_server.py
```

The server will:
- Start on **http://localhost:5001**
- Display the database path it's using
- Show how many transcripts are loaded

### 3. Serve the UI (in a separate terminal)

```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 -m http.server 8080
```

Then open **http://localhost:8080/analytics_ui.html** in your browser.

**Troubleshooting:** If you see "0 transcripts":
1. Check the API server console output for the database path
2. Visit http://localhost:5001/api/health to see DB status
3. Make sure the API server was started from the repo root (not a subdirectory)

### 4. Run the scraper (when needed)

```bash
python3 rollcall_scraper_robust.py
```

The scraper:
- Collects all Trump transcript URLs from RollCall (Sept 2024 - present)
- Scrapes each transcript with retry logic
- Saves to `data/transcripts.db`
- Shows live progress at http://localhost:8080

## Project Structure

```
mention-markets/
├── api_server.py              # Main API server (port 5001) ← ACTIVE
├── rollcall_scraper_robust.py # Production scraper ← ACTIVE
├── analytics_ui.html          # Main frontend UI ← ACTIVE
├── data/
│   └── transcripts.db         # SQLite database (1109 transcripts)
├── backend/                   # Legacy scripts (reference only)
│   ├── database.py            # Old database module
│   ├── scraper.py             # Old scraper
│   └── server.py              # Old API server (port 5000)
├── frontend/
│   └── index.html             # Old UI (not actively used)
└── README.md
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search?q=term` | GET | Search transcripts |
| `/api/analytics?q=term` | GET | Get mention analytics |
| `/api/transcripts` | GET | List all transcripts |
| `/api/transcripts/:id` | GET | Get single transcript |
| `/api/speakers` | GET | List all speakers |
| `/api/event-types` | GET | List event types |
| `/api/import` | POST | Import transcript data |
| `/api/stats` | GET | Database statistics |

### Search Parameters

- `q` - Search query (required)
- `speaker` - Filter by speaker name
- `type` - Filter by event type
- `start_date` - Start date (YYYY-MM-DD)
- `end_date` - End date (YYYY-MM-DD)
- `limit` - Max results (default 100)
- `offset` - Pagination offset

## Database Schema

### transcripts
- Primary metadata (title, speaker, date, location, type)
- Aggregate stats (word count, duration)
- Topics and entities (JSON)

### segments
- Individual speech segments
- Speaker identification
- Timestamps
- Full-text search index (FTS5)

### speakers
- Speaker profiles
- Aggregate statistics

## Adding More Transcripts

### Method 1: Add URLs to scraper

Edit `backend/scraper.py` and add URLs to `KNOWN_TRANSCRIPT_URLS`:

```python
KNOWN_TRANSCRIPT_URLS = [
    "https://rollcall.com/factbase/trump/transcript/...",
    # Add more URLs here
]
```

Then run: `python import_data.py`

### Method 2: Import via API

```bash
curl -X POST http://localhost:5000/api/import \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my-transcript",
    "url": "https://example.com/transcript",
    "title": "My Transcript",
    "primary_speaker": "Speaker Name",
    "event_type": "Speech",
    "event_date": "2025-01-01",
    "location": "City, State",
    "segments": [
      {"speaker": "Speaker Name", "start_time": "00:00:00", "text": "Hello..."}
    ]
  }'
```

### Method 3: Bulk Import

```bash
curl -X POST http://localhost:5000/api/import/bulk \
  -H "Content-Type: application/json" \
  -d '[{...}, {...}]'
```

## Development

### Frontend Development

The frontend is a single HTML file with embedded CSS and JavaScript. Edit `frontend/index.html` directly.

To add more sample data, modify the `SAMPLE_TRANSCRIPTS` array in the JavaScript.

### Backend Development

```bash
cd backend
DEBUG=true python server.py
```

### Database

SQLite database at `data/transcripts.db`. View with any SQLite browser:

```bash
sqlite3 data/transcripts.db
.tables
.schema transcripts
SELECT * FROM transcripts LIMIT 5;
```

## Future Enhancements

- [ ] Real-time scraping with scheduled updates
- [ ] WebSocket for live search updates
- [ ] Export to CSV/JSON
- [ ] Comparison view (side-by-side transcripts)
- [ ] Named entity extraction
- [ ] Sentiment timeline visualization
- [ ] User accounts and saved searches
- [ ] Jerome Powell/Fed transcripts from FOMC

## Data Source

Transcripts are sourced from [Roll Call Factbase](https://rollcall.com/factbase), which provides comprehensive political speech transcripts with sentiment analysis, topic tagging, and speaker identification.

## License

MIT

---

Built for tracking what politicians say, when they say it, and how often.
