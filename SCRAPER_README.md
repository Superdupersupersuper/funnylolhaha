# Scraper Issues & Solutions Log

## Current Scraper Problem

The `rollcall_scraper_robust.py` scraper is **encountering "No Transcript" pages and giving up**.

### What's Happening:
1. Scraper collects URLs from RollCall search page ✅
2. Finds 1109 transcript URLs ✅
3. Starts scraping each URL one by one
4. When it hits a page, it looks for dialogue using CSS selectors
5. **PROBLEM:** If it doesn't find content immediately, it retries 2-3 times then marks it as failed
6. **RESULT:** 78 transcripts saved with empty content (word_count = 0)

### Why This Is Wrong:
- Pages marked "No Transcript" in the title DO have transcripts
- Example: Pennsylvania rally (Dec 9, 2025) - title says "No Transcript" but page has full content
- The scraper needs to try HARDER with more CSS selectors

---

## Solution: Better Selector Strategy

### Current selectors (only tries 3):
1. `div.transcript-content`
2. `div.transcript-text`
3. `article`

### Need to add (try 10+ selectors):
```python
selectors = [
    'div.transcript-content',
    'div.transcript-text',
    'article',
    'div[class*="transcript"]',
    'main',
    'section',
    'body'  # Last resort
]
```

See AI_HANDOFF.md for complete fix script template.
