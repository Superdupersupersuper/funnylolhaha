# Quick Start Guide - Mention Market Tool

## ✅ YOUR WEBSITE IS LIVE!

Visit: **http://localhost:5174**

---

## Current Status

### 📊 Data
- **1,907 transcripts** from Donald Trump
- **1.9 million words** analyzed
- Speech types: Tweets, Press Releases, Speeches, Executive Orders, etc.
- Date range: 2016-present

### 🖥️ Servers Running
- **Frontend**: http://localhost:5174
- **Backend API**: http://localhost:3000

---

## How to Use Your Website

### 1. Open in Browser
Visit http://localhost:5174 in your browser

### 2. Explore Features

**Dashboard Tab**
- See overall statistics
- View speech type breakdown
- Check active filters

**Transcripts Tab**
- Browse all 1,907 transcripts
- Click on any transcript to read full text
- Use pagination to explore more

**Word Frequency Tab**
- See most common words across all transcripts
- Choose top 25, 50, 100, or 200 words
- Toggle common word filtering
- Filter by date range and speech type

**Word Trends Tab**
- Search for any word (e.g., "immigration", "china", "economy")
- See mentions across speeches over time
- Track word frequency patterns
- Filter by date and speech type

### 3. Try These Searches

**Interesting Words to Track:**
- "immigration"
- "china"
- "economy"
- "wall"
- "trade"
- "jobs"
- "america"
- "great"
- "fake"
- "news"

**Date Filtering:**
- Campaign period: 2016-01-01 to 2016-11-08
- First year: 2017-01-20 to 2018-01-20
- Full presidency: 2017-01-20 to 2021-01-20

**Speech Types:**
- Rally speeches
- Press releases
- Tweets
- Executive orders
- Statements

---

## How to Stop the Servers

When you're done:

1. Find the terminal/command windows running the servers
2. Press `Ctrl+C` in each window to stop

Or run:
```bash
# Kill all node processes
pkill -f "node backend/server.js"
pkill -f "npm run dev"
```

---

## How to Start the Servers Again

When you want to use the website later:

```bash
# Terminal 1 - Start backend
cd "/Users/alexandermiron/Desktop/Mention Market Tool"
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
node backend/server.js

# Terminal 2 - Start frontend (in a new terminal window)
cd "/Users/alexandermiron/Desktop/Mention Market Tool/frontend"
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
npm run dev
```

Then visit http://localhost:5174

---

## Troubleshooting

### Port Already in Use

If you see "EADDRINUSE" error:

```bash
# Kill processes on ports
lsof -ti:3000 | xargs kill -9
lsof -ti:5173 | xargs kill -9
lsof -ti:5174 | xargs kill -9
```

### Database Not Found

If you see database errors:

```bash
# Copy latest database
cp "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python/data/transcripts.db" "/Users/alexandermiron/Desktop/Mention Market Tool/data/transcripts.db"
```

### Frontend Can't Connect to Backend

Make sure both servers are running:
- Backend should show: "Server running on http://localhost:3000"
- Frontend should show: "Local: http://localhost:5174/"

---

## Update Database with New Transcripts

The scraper may still be running and collecting more transcripts. To update your website with new data:

1. **Check scraper status**:
   ```bash
   cd "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python"
   python3 view_data.py
   ```

2. **Copy updated database**:
   ```bash
   cp "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python/data/transcripts.db" "/Users/alexandermiron/Desktop/Mention Market Tool/data/transcripts.db"
   ```

3. **Restart backend server** (Ctrl+C then start again)

4. **Refresh browser** - New data will appear!

---

## Next Steps

### To Deploy to the Internet
See `DEPLOYMENT_GUIDE.md` for instructions on making this a real website

### To Analyze Data in Python
```bash
cd "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python"

# Query database
sqlite3 data/transcripts.db
```

Example queries:
```sql
-- Find all mentions of "immigration"
SELECT title, date, speech_type
FROM transcripts
WHERE full_text LIKE '%immigration%'
ORDER BY date;

-- Count speeches by type
SELECT speech_type, COUNT(*) as count
FROM transcripts
GROUP BY speech_type
ORDER BY count DESC;

-- Most common words containing "amer"
SELECT word, frequency
FROM word_frequencies
WHERE word LIKE '%amer%'
ORDER BY frequency DESC
LIMIT 20;
```

---

## Files Overview

```
Mention Market Tool/
├── frontend/              # React website (http://localhost:5174)
├── backend/              # API server (http://localhost:3000)
├── data/
│   └── transcripts.db   # Your 1,907 transcripts
├── scraper_python/       # Python scraper (may still be running)
│   └── data/
│       └── transcripts.db  # Latest data (copy from here)
├── QUICK_START.md        # This file
├── DEPLOYMENT_GUIDE.md   # How to deploy to internet
└── PROJECT_STATUS.md     # Project overview
```

---

## Enjoy Your Mention Market Tool! 🎉

You now have a fully functional website for analyzing Trump transcripts!
