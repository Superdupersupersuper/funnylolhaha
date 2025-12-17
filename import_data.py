#!/usr/bin/env python3
"""
Mention Markets - Data Import Script
Fetches transcripts from Factbase and imports them into the database.

Usage:
    python import_data.py                    # Import all known transcripts
    python import_data.py --url <url>        # Import a specific URL
    python import_data.py --list             # List all known transcript URLs
"""

import sys
import os
import json
import re
import argparse
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from database import init_database, insert_transcript, get_database_stats
from scraper import KNOWN_TRANSCRIPT_URLS, parse_transcript_from_html

# Check if we have requests for web fetching
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def fetch_transcript_html(url: str) -> str:
    """Fetch HTML from a transcript URL."""
    if not HAS_REQUESTS:
        raise RuntimeError("requests library required. Install with: pip install requests")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_factbase_html(html: str, url: str) -> dict:
    """
    Parse Factbase HTML into transcript data.
    This is a more robust parser specifically for Factbase pages.
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title
    title_elem = soup.find('h1')
    title = title_elem.get_text(strip=True) if title_elem else 'Unknown Transcript'
    
    # Parse title for metadata
    event_type = 'Unknown'
    location = ''
    event_date = ''
    
    if ':' in title:
        event_type = title.split(':')[0].strip()
    
    # Extract date from title (e.g., "January 19, 2025")
    date_match = re.search(r'-\s*(\w+\s+\d+,?\s*\d{4})\s*$', title)
    if date_match:
        date_str = date_match.group(1)
        for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y']:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                event_date = dt.strftime('%Y-%m-%d')
                break
            except ValueError:
                continue
    
    # Extract location
    location_match = re.search(r'\s+in\s+([^-]+?)(?:\s+-|\s*$)', title)
    if location_match:
        location = location_match.group(1).strip()
    else:
        location_match = re.search(r'\s+at\s+([^-]+?)(?:\s+-|\s*$)', title)
        if location_match:
            location = location_match.group(1).strip()
    
    # Extract segments
    segments = []
    current_speaker = None
    current_time = None
    current_text_parts = []
    
    # Find all h2 elements (speaker headers) and following content
    for elem in soup.find_all(['h2', 'p']):
        if elem.name == 'h2':
            # Save previous segment
            if current_speaker and current_text_parts:
                text = ' '.join(current_text_parts).strip()
                # Filter out metadata text
                if text and not any(x in text.lower() for x in ['sentiment', 'topics', 'moderation', 'flesch', 'readability']):
                    segments.append({
                        'speaker': current_speaker,
                        'start_time': current_time or '',
                        'end_time': '',
                        'duration_seconds': 0,
                        'text': text
                    })
            
            # Parse new speaker
            header_text = elem.get_text(strip=True)
            
            # Extract speaker name (first line of header)
            lines = header_text.split('\n')
            current_speaker = lines[0].strip()
            
            # Check if it's a timestamp header like "00:00:00-00:00:27 (27 sec)"
            time_match = re.search(r'^(\d{2}:\d{2}:\d{2})', current_speaker)
            if time_match and current_speaker.startswith(time_match.group(1)):
                # This is a timestamp, not a speaker - skip
                continue
            
            # Extract timestamp
            time_match = re.search(r'(\d{2}:\d{2}:\d{2})', header_text)
            current_time = time_match.group(1) if time_match else None
            
            current_text_parts = []
            
        elif elem.name == 'p' and current_speaker:
            text = elem.get_text(strip=True)
            # Filter out metadata
            if text and len(text) > 10:
                if not any(x in text.lower() for x in ['sentiment', 'topics', 'moderation', 'flesch', 'readability', 'loughran', 'harvard', 'vader', 'gunning', 'coleman', 'automated']):
                    current_text_parts.append(text)
    
    # Don't forget last segment
    if current_speaker and current_text_parts:
        text = ' '.join(current_text_parts).strip()
        if text and not any(x in text.lower() for x in ['sentiment', 'topics', 'moderation']):
            segments.append({
                'speaker': current_speaker,
                'start_time': current_time or '',
                'end_time': '',
                'duration_seconds': 0,
                'text': text
            })
    
    # Determine primary speaker (most segments)
    speaker_counts = {}
    for seg in segments:
        speaker_counts[seg['speaker']] = speaker_counts.get(seg['speaker'], 0) + 1
    
    primary_speaker = max(speaker_counts.keys(), key=lambda s: speaker_counts[s]) if speaker_counts else 'Unknown'
    
    # Generate ID from URL
    id_match = re.search(r'/transcript/([^/]+)/?$', url)
    transcript_id = id_match.group(1) if id_match else url.split('/')[-2]
    
    return {
        'id': transcript_id,
        'url': url,
        'title': title.replace(event_type + ': ', '') if event_type != 'Unknown' else title,
        'primary_speaker': primary_speaker,
        'event_type': event_type,
        'event_date': event_date,
        'location': location,
        'segments': segments,
        'topics': [],
        'entities': []
    }


def import_transcript(url: str, html: str = None) -> bool:
    """Import a single transcript from URL or HTML."""
    try:
        if not html:
            print(f"Fetching: {url}")
            html = fetch_transcript_html(url)
        
        print(f"Parsing transcript...")
        data = parse_factbase_html(html, url)
        
        if not data['segments']:
            print(f"  Warning: No segments found")
            return False
        
        print(f"  Title: {data['title']}")
        print(f"  Speaker: {data['primary_speaker']}")
        print(f"  Date: {data['event_date']}")
        print(f"  Segments: {len(data['segments'])}")
        
        # Insert into database
        insert_transcript(
            transcript_id=data['id'],
            url=data['url'],
            title=data['title'],
            primary_speaker=data['primary_speaker'],
            event_type=data['event_type'],
            event_date=data['event_date'],
            location=data['location'],
            segments=data['segments'],
            topics=data.get('topics'),
            entities=data.get('entities'),
            raw_html=html
        )
        
        print(f"  ✓ Imported successfully")
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def import_all_known():
    """Import all known transcript URLs."""
    print(f"\n{'='*60}")
    print("MENTION MARKETS - TRANSCRIPT IMPORT")
    print(f"{'='*60}\n")
    
    # Initialize database
    init_database()
    
    total = len(KNOWN_TRANSCRIPT_URLS)
    success = 0
    failed = 0
    
    print(f"Found {total} known transcript URLs\n")
    
    for i, url in enumerate(KNOWN_TRANSCRIPT_URLS, 1):
        print(f"\n[{i}/{total}] {url[:80]}...")
        
        try:
            if import_transcript(url):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            failed += 1
        
        # Rate limiting
        import time
        time.sleep(1.5)
    
    print(f"\n{'='*60}")
    print(f"IMPORT COMPLETE")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print(f"{'='*60}\n")
    
    # Show stats
    stats = get_database_stats()
    print("DATABASE STATS:")
    print(f"  Total Transcripts: {stats['total_transcripts']}")
    print(f"  Total Segments: {stats['total_segments']}")
    print(f"  Total Words: {stats['total_words']:,}")
    print(f"  Date Range: {stats['date_range']['start']} to {stats['date_range']['end']}")


def main():
    parser = argparse.ArgumentParser(description='Import transcripts into Mention Markets')
    parser.add_argument('--url', help='Import a specific URL')
    parser.add_argument('--list', action='store_true', help='List all known URLs')
    parser.add_argument('--stats', action='store_true', help='Show database statistics')
    parser.add_argument('--init', action='store_true', help='Initialize database only')
    
    args = parser.parse_args()
    
    if args.list:
        print("Known Transcript URLs:")
        for url in KNOWN_TRANSCRIPT_URLS:
            print(f"  {url}")
        return
    
    if args.stats:
        init_database()
        stats = get_database_stats()
        print("\nDATABASE STATISTICS:")
        print(f"  Total Transcripts: {stats['total_transcripts']}")
        print(f"  Total Segments: {stats['total_segments']}")
        print(f"  Total Speakers: {stats['total_speakers']}")
        print(f"  Total Words: {stats['total_words']:,}")
        if stats['date_range']['start']:
            print(f"  Date Range: {stats['date_range']['start']} to {stats['date_range']['end']}")
        print(f"  Pending Scrapes: {stats['pending_scrapes']}")
        return
    
    if args.init:
        init_database()
        print("Database initialized.")
        return
    
    if args.url:
        init_database()
        import_transcript(args.url)
        return
    
    # Default: import all known
    import_all_known()


if __name__ == '__main__':
    main()
