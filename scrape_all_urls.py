#!/usr/bin/env python3
"""
Mention Markets - Complete Factbase URL Scraper

This script hits the Factbase JSON API to discover ALL transcript URLs.
It paginates through every page and categorizes by event type.

RUN THIS LOCALLY - it needs unrestricted internet access to factba.se

Usage:
    python3 scrape_all_urls.py

Output:
    data/all_transcript_urls.json - Complete URL list organized by event type

API discovered from: https://go-colly.org/docs/examples/factbase/
The endpoint is: https://factba.se/json/json-transcript.php?q=&f=&dt=&p=PAGE
- q = search query
- f = filter (event type)
- dt = date filter  
- p = page number (starts at 1)

Returns JSON like: {"data": [{"slug": "...", "date": "...", "title": "..."}, ...]}
"""

import requests
import json
import time
import re
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Output files
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "all_transcript_urls.json"
RAW_OUTPUT_FILE = OUTPUT_DIR / "raw_api_responses.json"

# Factbase API endpoint (discovered from Colly scraper example)
# Parameters: q=search, f=filter, dt=date, p=page
API_BASE = "https://factba.se/json/json-transcript.php"

# Alternative endpoints to try if main one fails
API_ALTERNATIVES = [
    "https://factba.se/json/json-transcript.php",
    "https://api.factba.se/transcript/list",
    "https://factba.se/api/transcripts",
]

# Roll Call URL format
ROLLCALL_BASE = "https://rollcall.com/factbase/trump/transcript/"
FACTBASE_BASE = "https://factba.se/transcript/"

# Event type categories based on the website filters
EVENT_TYPES = [
    "Interview",
    "Press Briefing", 
    "Press Gaggle",
    "Remarks",
    "Speech",
    "Vlog"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://factba.se/transcripts',
    'Origin': 'https://factba.se',
}


def test_api_connectivity():
    """Test if we can reach the Factbase API."""
    print("Testing API connectivity...")
    
    url = "https://factba.se/json/json-transcript.php?q=&f=&dt=&p=1"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        print(f"  Status code: {response.status_code}")
        print(f"  Response length: {len(response.text)} bytes")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if 'data' in data:
                    print(f"  ✓ API is working! Found {len(data['data'])} transcripts on page 1")
                    return True
                else:
                    print(f"  ✗ Unexpected response format: {list(data.keys())}")
                    return False
            except:
                print(f"  ✗ Response is not valid JSON")
                print(f"  First 500 chars: {response.text[:500]}")
                return False
        else:
            print(f"  ✗ HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  ✗ Connection error: {e}")
        return False


def fetch_page(page: int, query: str = "", filter_type: str = "", date: str = "") -> dict:
    """Fetch a single page from the Factbase API."""
    
    # Build URL explicitly to ensure we hit factba.se not rollcall
    url = f"https://factba.se/json/json-transcript.php?q={query}&f={filter_type}&dt={date}&p={page}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"    HTTP Error {e.response.status_code}: {url}")
        return {'data': []}
    except requests.exceptions.JSONDecodeError:
        print(f"    Warning: Invalid JSON on page {page}")
        return {'data': []}
    except Exception as e:
        print(f"    Error on page {page}: {e}")
        return {'data': []}


def categorize_by_event_type(slug: str, title: str = "") -> str:
    """Determine event type from slug or title."""
    slug_lower = slug.lower()
    title_lower = title.lower() if title else ""
    combined = slug_lower + " " + title_lower
    
    # Check in order of specificity
    if 'press-gaggle' in combined or 'gaggle' in combined:
        return 'Press Gaggle'
    elif 'press-briefing' in combined or 'briefing' in combined:
        return 'Press Briefing'
    elif 'press-conference' in combined:
        return 'Press Briefing'  # Group with briefings
    elif 'interview' in combined:
        return 'Interview'
    elif 'vlog' in combined:
        return 'Vlog'
    elif 'speech' in combined or 'address' in combined or 'rally' in combined:
        return 'Speech'
    elif 'remarks' in combined or 'statement' in combined or 'bilat' in combined:
        return 'Remarks'
    else:
        return 'Remarks'  # Default


def fetch_all_transcripts():
    """Fetch ALL transcripts from the API by paginating through all pages."""
    print("=" * 70)
    print("FACTBASE COMPLETE URL SCRAPER")
    print("=" * 70)
    print()
    
    all_transcripts = []
    raw_responses = []
    
    page = 1
    empty_pages = 0
    max_empty = 3  # Stop after 3 consecutive empty pages
    
    print("Fetching all transcript metadata from API...")
    print("(This will take a few minutes - be patient)")
    print()
    
    while empty_pages < max_empty:
        print(f"  Page {page}...", end=" ", flush=True)
        
        data = fetch_page(page)
        raw_responses.append({'page': page, 'data': data})
        
        if not data.get('data') or len(data['data']) == 0:
            print("empty")
            empty_pages += 1
        else:
            results = data['data']
            print(f"{len(results)} transcripts")
            all_transcripts.extend(results)
            empty_pages = 0  # Reset counter
        
        page += 1
        time.sleep(0.5)  # Be nice to their server
        
        # Safety limit
        if page > 500:
            print("\n  Reached page limit (500)")
            break
    
    print()
    print(f"Total transcripts discovered: {len(all_transcripts)}")
    
    # Save raw responses for debugging
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(RAW_OUTPUT_FILE, 'w') as f:
        json.dump(raw_responses, f, indent=2)
    print(f"Raw API responses saved to: {RAW_OUTPUT_FILE}")
    
    return all_transcripts


def process_transcripts(transcripts: list) -> dict:
    """Process transcripts and organize by event type."""
    print()
    print("Processing and categorizing transcripts...")
    
    by_type = defaultdict(list)
    all_urls = []
    
    for t in transcripts:
        slug = t.get('slug', '')
        date = t.get('date', '')
        title = t.get('title', '')
        
        if not slug:
            continue
        
        # Build URLs (both factba.se and rollcall.com formats)
        factbase_url = FACTBASE_BASE + slug
        rollcall_url = ROLLCALL_BASE + slug + "/"
        
        # Categorize
        event_type = categorize_by_event_type(slug, title)
        
        entry = {
            'slug': slug,
            'date': date,
            'title': title,
            'event_type': event_type,
            'factbase_url': factbase_url,
            'rollcall_url': rollcall_url
        }
        
        by_type[event_type].append(entry)
        all_urls.append(rollcall_url)
    
    # Print summary
    print()
    print("=" * 70)
    print("RESULTS BY EVENT TYPE")
    print("=" * 70)
    
    for event_type in EVENT_TYPES:
        count = len(by_type.get(event_type, []))
        print(f"  {event_type}: {count} transcripts")
    
    other_count = sum(len(v) for k, v in by_type.items() if k not in EVENT_TYPES)
    if other_count:
        print(f"  Other: {other_count} transcripts")
    
    print()
    print(f"TOTAL: {len(all_urls)} transcripts")
    
    return {
        'by_type': dict(by_type),
        'all_urls': all_urls
    }


def save_results(results: dict):
    """Save the final results to JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    output = {
        'scraped_at': datetime.now().isoformat(),
        'total_count': len(results['all_urls']),
        'by_event_type': {
            event_type: {
                'count': len(results['by_type'].get(event_type, [])),
                'transcripts': results['by_type'].get(event_type, [])
            }
            for event_type in EVENT_TYPES
        },
        'urls': results['all_urls']
    }
    
    # Add any types not in our predefined list
    for event_type, transcripts in results['by_type'].items():
        if event_type not in EVENT_TYPES:
            output['by_event_type'][event_type] = {
                'count': len(transcripts),
                'transcripts': transcripts
            }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    
    print()
    print("=" * 70)
    print(f"SAVED: {OUTPUT_FILE}")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Run: python3 import_all.py")
    print("     This will fetch and parse all transcripts into the database")
    print()


def main():
    # First test connectivity
    if not test_api_connectivity():
        print()
        print("=" * 70)
        print("API CONNECTION FAILED")
        print("=" * 70)
        print()
        print("The Factbase API at factba.se may have changed.")
        print("Try opening this URL in your browser to check:")
        print("  https://factba.se/json/json-transcript.php?q=&f=&dt=&p=1")
        print()
        print("If it shows JSON data, the API works but something else is wrong.")
        print("If it shows an error, the API endpoint may have moved.")
        return
    
    # Step 1: Fetch all transcripts from API
    transcripts = fetch_all_transcripts()
    
    if not transcripts:
        print("No transcripts found! The API may have changed.")
        print("Try checking https://factba.se/transcripts manually")
        return
    
    # Step 2: Process and categorize
    results = process_transcripts(transcripts)
    
    # Step 3: Save results
    save_results(results)


if __name__ == '__main__':
    main()
