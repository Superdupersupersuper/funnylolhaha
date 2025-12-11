# 🎬 DEMO - How to Use Your Mention Market Tool

## Right Now - You Can Start Using It!

### ✅ What You Have:
- **2,357 transcripts**
- **2.3 MILLION words** analyzed
- **2016-2017** complete (2018-2024 being added)
- **10 document types** (speeches, tweets, press releases, etc.)
- **Full-text search** ready
- **Word frequency analysis** pre-computed

---

## 🚀 Method 1: Web Interface (Easiest)

### Step 1: Start the Server

Open Terminal and run:
```bash
cd "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python"
./start_server.sh
```

You'll see:
```
===============================================================================
MENTION MARKET TOOL - SERVER STARTUP
===============================================================================

Starting API server on http://localhost:5000

📊 Open in your browser:
   file:///Users/alexandermiron/Desktop/Mention Market Tool/scraper_python/index.html
```

### Step 2: Open the Interface

Double-click `index.html` in Finder, or paste this in your browser:
```
file:///Users/alexandermiron/Desktop/Mention Market Tool/scraper_python/index.html
```

### Step 3: Use It!

You'll see:
- 📊 **Statistics dashboard** - total transcripts, words, date range
- 📈 **Year distribution chart** - visual breakdown by year
- 🔄 **Refresh button** - click to get new transcripts

**Click "🔄 Refresh Transcripts"** and watch it work!

---

## 🔍 Method 2: Direct Database Queries

### Query 1: Find All Mentions of "China"

```bash
cd "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python"
sqlite3 data/transcripts.db
```

Then run:
```sql
SELECT title, date, speech_type
FROM transcripts
WHERE full_text LIKE '%China%'
ORDER BY date
LIMIT 10;
```

### Query 2: Top 20 Most Common Words

```sql
SELECT word, SUM(frequency) as total
FROM word_frequencies
GROUP BY word
ORDER BY total DESC
LIMIT 20;
```

### Query 3: Count by Speech Type

```sql
SELECT speech_type, COUNT(*) as count
FROM transcripts
GROUP BY speech_type
ORDER BY count DESC;
```

### Query 4: Speeches by Month

```sql
SELECT
  SUBSTR(date, 1, 7) as month,
  COUNT(*) as speeches
FROM transcripts
WHERE speech_type = 'Speech'
  AND date LIKE '____-__-__'
GROUP BY month
ORDER BY month;
```

---

## 📊 Method 3: Python API

### Example 1: Get Statistics

```python
import requests

response = requests.get('http://localhost:5000/api/stats')
data = response.json()

print(f"Total Transcripts: {data['totalTranscripts']}")
print(f"Total Words: {data['totalWords']}")
print(f"Date Range: {data['dateRange']['minDate']} to {data['dateRange']['maxDate']}")
```

### Example 2: Search Transcripts

```python
import requests

# Search for "immigration" in 2016
response = requests.get('http://localhost:5000/api/transcripts', params={
    'startDate': '2016-01-01',
    'endDate': '2016-12-31',
    'search': 'immigration',
    'limit': 10
})

transcripts = response.json()['transcripts']

for t in transcripts:
    print(f"{t['date']}: {t['title']}")
```

### Example 3: Word Frequency Analysis

```python
import requests

response = requests.get('http://localhost:5000/api/analysis/word-frequency', params={
    'startDate': '2016-01-01',
    'endDate': '2016-12-31',
    'topN': 20,
    'excludeCommon': 'true'
})

data = response.json()

print(f"Analyzed {data['transcriptCount']} transcripts with {data['totalWords']} words\n")
print("Top 20 words:")
for word in data['words']:
    print(f"  {word['word']}: {word['frequency']}")
```

### Example 4: Trigger Auto-Refresh

```python
import requests

# Start the scraper
response = requests.post('http://localhost:5000/api/scraper/refresh')
print(response.json())

# Check status
import time
while True:
    status = requests.get('http://localhost:5000/api/scraper/status').json()
    print(f"Status: {status['progress']}")

    if not status['running']:
        print("Done!")
        break

    time.sleep(5)
```

---

## 📈 Method 4: Mention Markets Analysis

### Track "Economy" Mentions Over Time

```python
import sqlite3
import matplotlib.pyplot as plt

conn = sqlite3.connect('data/transcripts.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT
        SUBSTR(date, 1, 7) as month,
        COUNT(*) as mentions
    FROM transcripts
    WHERE (full_text LIKE '%economy%' OR full_text LIKE '%Economy%')
      AND date LIKE '____-__-__'
    GROUP BY month
    ORDER BY month
""")

data = cursor.fetchall()
months = [row[0] for row in data]
mentions = [row[1] for row in data]

plt.figure(figsize=(12, 6))
plt.plot(months, mentions, marker='o')
plt.title('Mentions of "Economy" Over Time')
plt.xlabel('Month')
plt.ylabel('Number of Mentions')
plt.xticks(rotation=45)
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('economy_mentions.png')
print("Saved to economy_mentions.png")
```

### Compare Keywords

```python
import sqlite3

conn = sqlite3.connect('data/transcripts.db')
cursor = conn.cursor()

keywords = ['china', 'mexico', 'russia', 'iran']

print("Keyword Comparison:")
print("-" * 40)

for keyword in keywords:
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM transcripts
        WHERE LOWER(full_text) LIKE ?
    """, (f'%{keyword}%',))

    count = cursor.fetchone()[0]
    print(f"{keyword.capitalize():15} {count:5} mentions")
```

### Find Co-Mentions

```python
import sqlite3

conn = sqlite3.connect('data/transcripts.db')
cursor = conn.cursor()

# Find speeches that mention both "trade" and "china"
cursor.execute("""
    SELECT title, date, word_count
    FROM transcripts
    WHERE LOWER(full_text) LIKE '%trade%'
      AND LOWER(full_text) LIKE '%china%'
      AND speech_type = 'Speech'
    ORDER BY date
""")

print("Speeches mentioning both 'trade' and 'china':")
print("-" * 60)

for title, date, words in cursor.fetchall():
    print(f"{date}: {title[:50]}... ({words} words)")
```

---

## 🎯 Real-World Use Cases

### 1. Stock Market Analysis
Track mentions of company names and correlate with stock performance.

### 2. Policy Tracking
Monitor when specific policies are discussed and their frequency over time.

### 3. International Relations
Track mentions of foreign countries to gauge diplomatic focus.

### 4. Campaign vs Presidency
Compare rhetoric between campaign speeches and official presidential remarks.

### 5. Event Impact
Measure how major events affect speech topics and frequency.

---

## 💾 Exporting Data

### Export to CSV

```bash
sqlite3 -header -csv data/transcripts.db \
  "SELECT title, date, speech_type, word_count, url FROM transcripts ORDER BY date;" \
  > transcripts.csv

echo "Exported to transcripts.csv"
```

### Export Top Words to JSON

```python
import sqlite3
import json

conn = sqlite3.connect('data/transcripts.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT word, SUM(frequency) as total
    FROM word_frequencies
    GROUP BY word
    ORDER BY total DESC
    LIMIT 500
""")

words = [{'word': row[0], 'frequency': row[1]} for row in cursor.fetchall()]

with open('top_words.json', 'w') as f:
    json.dump(words, f, indent=2)

print("Exported to top_words.json")
```

---

## 🔄 Auto-Refresh Demo

### Watch It Update in Real-Time

1. Open the web interface (`index.html`)
2. Note the current transcript count
3. Click "🔄 Refresh Transcripts"
4. Watch the progress message update
5. See new transcripts added
6. Statistics update automatically

The scraper:
- ✅ Checks for new transcripts
- ✅ Skips what you already have
- ✅ Downloads only new content
- ✅ Analyzes word frequencies
- ✅ Updates database
- ✅ Reports results

---

## 🎮 Try It Now!

### Quick Test:

```bash
cd "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python"

# Start server
./start_server.sh &

# Wait 3 seconds
sleep 3

# Test API
curl http://localhost:5000/api/stats | python3 -m json.tool

# Open interface
open index.html
```

Then try:
1. Click refresh button
2. Watch it work
3. See stats update
4. Query the database

---

## 📖 More Info

- **Full documentation**: Read `USAGE_GUIDE.md`
- **Technical details**: Read `README.md`
- **Project status**: Read `FINAL_STATUS.md`

---

## 🆘 Need Help?

**View current stats:**
```bash
python3 view_data.py
```

**Check if server is running:**
```bash
curl http://localhost:5000/api/stats
```

**Check database size:**
```bash
sqlite3 data/transcripts.db "SELECT COUNT(*) FROM transcripts;"
```

**View logs:**
```bash
tail -f full_scrape.log
```

---

## 🎉 You're Ready!

Your mention markets tool is **fully operational** with:
- ✅ 2,357 transcripts (2.3M words)
- ✅ Auto-refresh capability
- ✅ Web interface
- ✅ Python API
- ✅ Direct SQL access
- ✅ Word frequency analysis

**Start using it now while the scraper completes the remaining years!**
