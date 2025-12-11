# Trump Transcript Scraper - Python Edition

This is a Python-based web scraper that collects Donald Trump speech transcripts, tweets, press releases, and other documents from the American Presidency Project.

## What's Been Accomplished

✅ **Successfully built a working scraper** that has found **5,000+ Trump documents** from 2016-present
✅ **Created SQLite database** with full-text search and word frequency analysis
✅ **Currently scraping data** - the scraper is running in the background collecting transcripts
✅ **110+ transcripts already collected** with 40,000+ words analyzed

## Database Location

The SQLite database is located at:
```
/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python/data/transcripts.db
```

## Files

- `database.py` - Database connection and schema management
- `text_analysis.py` - Word frequency and text analysis utilities
- `comprehensive_scraper.py` - Main scraper (CURRENTLY RUNNING)
- `view_data.py` - View database statistics
- `requirements.txt` - Python dependencies

## Usage

### View Current Statistics

```bash
cd "/Users/alexandermiron/Desktop/Mention Market Tool/scraper_python"
python3 view_data.py
```

### Check Scraper Progress

The scraper is currently running in the background. To check its progress:

```bash
# Check database count
sqlite3 data/transcripts.db "SELECT COUNT(*) FROM transcripts;"

# View log (if available)
tail -f scrape_full.log

# Check if still running
ps aux | grep comprehensive_scraper
```

### Query the Database

```bash
# Connect to database
sqlite3 data/transcripts.db

# Example queries:
SELECT title, date, speech_type FROM transcripts LIMIT 10;
SELECT speech_type, COUNT(*) FROM transcripts GROUP BY speech_type;
SELECT * FROM transcripts WHERE date LIKE '2016%';
```

## Data Structure

### transcripts table
- `id` - Primary key
- `title` - Document title
- `date` - Date of speech/document
- `speech_type` - Type (Speech, Tweet Collection, Press Release, etc.)
- `location` - Where it occurred
- `url` - Source URL
- `full_text` - Complete transcript text
- `word_count` - Total word count
- `scraped_at` - When it was scraped

### word_frequencies table
- `id` - Primary key
- `transcript_id` - Links to transcripts table
- `word` - The word
- `frequency` - How many times it appears

## Data Source

All data is scraped from:
**American Presidency Project** (https://www.presidency.ucsb.edu)

This is a comprehensive academic archive maintained by UC Santa Barbara that contains:
- Presidential speeches and remarks
- Press releases and statements
- Executive orders and proclamations
- Twitter/social media posts
- Interviews
- And more

The scraper is configured to get all Trump documents from January 1, 2016 onwards.

## What the Scraper Does

1. **Discovers documents**: Pagrinates through search results (found 5,000+ documents)
2. **Extracts content**: Scrapes each document page for title, date, type, and full text
3. **Analyzes text**: Counts words and calculates word frequencies
4. **Stores in database**: Saves everything to SQLite for fast querying
5. **Avoids duplicates**: Checks URLs to prevent re-scraping

## Current Progress

As of the last check:
- **110 transcripts** collected
- **40,316 words** analyzed
- **Date range**: 2016-01-04 to February 2016
- **Still running**: Scraper is actively collecting more data

The scraper has a 2-second delay between requests to be respectful to the server.

## Next Steps (Using the Data)

Once the scraper completes, you can:

1. **Use the existing React frontend** (in ../frontend/) to visualize the data
2. **Run the Node.js backend** (in ../backend/) to create an API
3. **Query the database directly** using SQL
4. **Export to CSV** for analysis in Excel/Google Sheets
5. **Build custom analysis** using Python

## Note on Data Completeness

The American Presidency Project is an excellent source because it includes:
- Official White House documents
- Campaign materials
- Social media (Twitter/Truth Social)
- Interviews and press conferences
- Executive actions

This gives you a comprehensive view of Trump's communications from 2016 onwards, which is perfect for mention markets analysis.

## Scraper is Running

**The scraper is currently running in the background and will continue to collect transcripts.**

It found 5,000 documents and is working through them. The process may take several hours to complete all documents, but you already have a working database with data you can start analyzing!
