# Mention Market Tool - Usage Guide

## Quick Start (Local Development)

### 1. Start the API Server

```bash
cd "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python"
./start_server.sh
```

Or manually:
```bash
python3 api_server.py
```

The server will start on **http://localhost:5000**

### 2. Open the Web Interface

Open this file in your browser:
```
file:///Users/alexandermiron/Desktop/Mention Market Tool/scraper_python/index.html
```

Or just double-click `index.html` in Finder.

### 3. Refresh Transcripts

Click the **"🔄 Refresh Transcripts"** button in the web interface to:
- Check for new transcripts
- Download any missing transcripts from 2016 to present
- Update word frequency analysis
- Get the latest speeches, tweets, and documents

The scraper runs in the background and you can see progress in the interface.

## What You Get

### Current Database Stats
- **2,330+ transcripts** already collected
- **Years covered**: 2016-2017 (with more being added)
- **Types**: Speeches, Tweets, Press Releases, Statements, Executive Orders, etc.

### Auto-Refresh Feature
The scraper intelligently:
- Skips transcripts you already have
- Only downloads new content
- Runs in background (won't freeze your computer)
- Updates database automatically
- Can be run anytime to check for new transcripts

## API Endpoints

All endpoints available at `http://localhost:5000/api/`

### Get Statistics
```
GET /api/stats
```
Returns total transcripts, words, date range, speech types, and year distribution.

### List Transcripts
```
GET /api/transcripts?startDate=2016-01-01&endDate=2024-12-31&speechType=Speech&search=economy
```
Parameters:
- `startDate` - Filter by start date
- `endDate` - Filter by end date
- `speechType` - Filter by type (Speech, Tweet Collection, etc.)
- `search` - Search in title and full text
- `limit` - Number of results (default: 100)
- `offset` - Pagination offset

### Get Single Transcript
```
GET /api/transcripts/123
```

### Word Frequency Analysis
```
GET /api/analysis/word-frequency?startDate=2016-01-01&endDate=2016-12-31&topN=50
```
Parameters:
- `startDate`, `endDate`, `speechType` - Filter transcripts
- `topN` - Number of top words to return (default: 50)
- `excludeCommon` - Exclude common words (default: true)

### Trigger Scraper Refresh
```
POST /api/scraper/refresh
```
Starts the scraper in background to collect new transcripts.

### Check Scraper Status
```
GET /api/scraper/status
```
Returns current scraper status and progress.

## Direct Database Access

### Using Python

```python
import sqlite3

conn = sqlite3.connect('./data/transcripts.db')
cursor = conn.cursor()

# Get all speeches from 2016
cursor.execute("""
    SELECT title, date, word_count
    FROM transcripts
    WHERE date LIKE '2016%' AND speech_type = 'Speech'
    ORDER BY date
""")

for row in cursor.fetchall():
    print(row)

conn.close()
```

### Using SQL CLI

```bash
sqlite3 data/transcripts.db

# Example queries
SELECT COUNT(*) FROM transcripts;
SELECT speech_type, COUNT(*) FROM transcripts GROUP BY speech_type;
SELECT * FROM transcripts WHERE full_text LIKE '%immigration%' LIMIT 10;
SELECT word, SUM(frequency) as total FROM word_frequencies GROUP BY word ORDER BY total DESC LIMIT 20;
```

## Mention Markets Analysis Examples

### Track Specific Words Over Time

```python
import sqlite3
import matplotlib.pyplot as plt
from collections import defaultdict

conn = sqlite3.connect('./data/transcripts.db')
cursor = conn.cursor()

# Track "china" mentions by month
cursor.execute("""
    SELECT
        SUBSTR(date, 1, 7) as month,
        SUM(CASE WHEN full_text LIKE '%china%' OR full_text LIKE '%China%' THEN 1 ELSE 0 END) as mentions
    FROM transcripts
    WHERE date LIKE '____-__-__'
    GROUP BY month
    ORDER BY month
""")

data = cursor.fetchall()
months = [row[0] for row in data]
mentions = [row[1] for row in data]

plt.plot(months, mentions)
plt.title('Mentions of "China" Over Time')
plt.xticks(rotation=45)
plt.show()
```

### Compare Word Usage Between Years

```sql
-- Compare 2016 vs 2017 word usage
SELECT
    word,
    SUM(CASE WHEN SUBSTR(date, 1, 4) = '2016' THEN frequency ELSE 0 END) as freq_2016,
    SUM(CASE WHEN SUBSTR(date, 1, 4) = '2017' THEN frequency ELSE 0 END) as freq_2017
FROM word_frequencies wf
JOIN transcripts t ON wf.transcript_id = t.id
WHERE date LIKE '____-__-__'
GROUP BY word
HAVING freq_2016 > 100 AND freq_2017 > 100
ORDER BY ABS(freq_2017 - freq_2016) DESC
LIMIT 50;
```

### Find Speeches Mentioning Multiple Keywords

```sql
-- Find speeches mentioning both "immigration" and "border"
SELECT title, date, speech_type, word_count
FROM transcripts
WHERE full_text LIKE '%immigration%'
  AND full_text LIKE '%border%'
  AND speech_type = 'Speech'
ORDER BY date DESC;
```

## Exporting Data

### Export to CSV

```python
import sqlite3
import csv

conn = sqlite3.connect('./data/transcripts.db')
cursor = conn.cursor()

cursor.execute("SELECT title, date, speech_type, word_count, url FROM transcripts ORDER BY date")

with open('transcripts_export.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['Title', 'Date', 'Type', 'Word Count', 'URL'])
    writer.writerows(cursor.fetchall())

print("Exported to transcripts_export.csv")
```

### Export Word Frequencies

```python
import sqlite3
import json

conn = sqlite3.connect('./data/transcripts.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT word, SUM(frequency) as total_freq
    FROM word_frequencies
    GROUP BY word
    ORDER BY total_freq DESC
    LIMIT 1000
""")

words = [{'word': row[0], 'frequency': row[1]} for row in cursor.fetchall()]

with open('word_frequencies.json', 'w') as f:
    json.dump(words, f, indent=2)

print("Exported to word_frequencies.json")
```

## Troubleshooting

### API Server Won't Start

1. Check if port 5000 is in use:
```bash
lsof -i :5000
```

2. Kill any process using port 5000:
```bash
kill -9 <PID>
```

3. Try a different port:
Edit `api_server.py` and change:
```python
app.run(host='0.0.0.0', port=5001, debug=True)
```

### Web Interface Not Loading Stats

1. Make sure API server is running
2. Check browser console for errors (F12)
3. Verify API URL in `index.html` matches server port
4. Try: `curl http://localhost:5000/api/stats`

### Scraper Not Finding New Transcripts

The American Presidency Project updates periodically. If no new transcripts are found:
- This is normal - it means you have everything
- Check back in a few days for new speeches
- The database already has 2,330+ transcripts

### Database Locked Error

If you get "database is locked":
1. Close any SQLite browser apps
2. Stop any running scrapers
3. Restart the API server

## Tips for Mention Markets

1. **Track Multiple Keywords**: Create a list of important terms (company names, policy topics, countries)

2. **Time-Based Analysis**: Compare mention frequencies before/after major events

3. **Context Matters**: Use speech_type to separate rally speeches from official remarks

4. **Combine Metrics**: Look at both raw mentions and mention density (mentions/word_count)

5. **Phrase Analysis**: Search for multi-word phrases like "fake news" or "border wall"

## Moving to Production

When ready to deploy:

1. **Use a Production Server**: Replace Flask development server with Gunicorn or uWSGI

2. **Add Authentication**: Protect scraper endpoints

3. **Set Up Cron Jobs**: Auto-refresh daily
```bash
0 2 * * * cd /path/to/scraper && python3 full_scraper.py
```

4. **Add Rate Limiting**: Protect API from abuse

5. **Database Backups**: Regular backups of transcripts.db

6. **Use Environment Variables**: For configuration

## Need Help?

- Check logs: `tail -f full_scrape.log`
- View database: `python3 view_data.py`
- Test API: `curl http://localhost:5000/api/stats`

The scraper is designed to be resilient and can be run as often as needed to stay up-to-date!
