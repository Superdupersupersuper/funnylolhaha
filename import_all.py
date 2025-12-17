#!/usr/bin/env python3
"""
Mention Markets - Import All Transcripts
Fetches all transcripts from the scraped URLs and imports them into the database.

USAGE:
    python3 import_data.py --init   # First, initialize the database
    python3 import_all.py           # Then run this to import all transcripts
"""

import sys
import os
import json
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run:")
    print("  pip3 install requests beautifulsoup4 lxml")
    sys.exit(1)

from database import init_database, insert_transcript, get_database_stats

URLS_FILE = Path(__file__).parent / "data" / "all_transcript_urls.json"
PROGRESS_FILE = Path(__file__).parent / "data" / "import_progress.json"
DEBUG_DIR = Path(__file__).parent / "data" / "debug"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def load_urls():
    """Load URLs from the JSON file."""
    if not URLS_FILE.exists():
        print(f"ERROR: URLs file not found: {URLS_FILE}")
        print()
        print("You need to run the scraper first:")
        print("  python3 scrape_browser.py")
        return []
    
    with open(URLS_FILE) as f:
        data = json.load(f)
    
    if "urls" in data:
        return data["urls"]
    elif "by_event_type" in data:
        urls = []
        for event_type, info in data["by_event_type"].items():
            for t in info.get("transcripts", []):
                if t.get("url"):
                    urls.append(t["url"])
        return urls
    
    return []


def load_progress():
    """Load import progress."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "failed": [], "no_segments": []}


def save_progress(progress):
    """Save import progress."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def fetch_transcript(url):
    """Fetch transcript HTML from URL."""
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def parse_transcript_method1(soup, page_text, url):
    """Method 1: Parse using ## Speaker pattern from plain text."""
    segments = []
    
    # Pattern: ## SpeakerName\n00:00:00-00:00:00 (X sec)\n<signal>\n<text>
    segment_pattern = r'##\s+([^\n]+)\n(\d{2}:\d{2}:\d{2})-(\d{2}:\d{2}:\d{2})\s*\([^)]*\)\s*\n(?:No StressLens|No Signal[^\n]*|Weak[^\n]*|Medium[^\n]*|Strong[^\n]*)\n([\s\S]*?)(?=##\s+[A-Z]|\Z)'
    
    matches = re.findall(segment_pattern, page_text)
    
    for match in matches:
        speaker = match[0].strip()
        start_time = match[1]
        end_time = match[2]
        text_block = match[3]
        
        if speaker.lower() in ['note', 'topics', 'entities', 'moderation', 'speakers', 'stresslens', 'full transcript']:
            continue
        
        text_lines = []
        for line in text_block.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith(('Sentiment', 'Loughran', 'Harvard', 'Moderation', 'OpenAI', 
                               'Readability', 'Flesch', 'Topics', 'Topic:', 'Gunning',
                               'Coleman', 'SMOG', 'Automated', 'Dale-Chall', 'VADER', 'Sprache')):
                break
            if re.match(r'^[\d.E-]+$', line) or re.match(r'^\d+(\.\d+)?$', line):
                continue
            if re.match(r'^(Very |Somewhat |Slightly |Leans )?(Positive|Negative|Neutral)$', line):
                continue
            text_lines.append(line)
        
        text = ' '.join(text_lines).strip()
        
        if text and len(text) > 3:
            segments.append({
                'speaker': speaker,
                'start_time': start_time,
                'end_time': end_time,
                'duration_seconds': 0,
                'text': text
            })
    
    return segments


def parse_transcript_method2(soup, page_text, url):
    """Method 2: Parse using h2 tags directly from HTML."""
    segments = []
    
    # Find all h2 elements
    h2_tags = soup.find_all('h2')
    
    for h2 in h2_tags:
        speaker = h2.get_text(strip=True)
        
        # Skip non-speaker headers
        if not speaker or speaker.lower() in ['note', 'topics', 'entities', 'moderation', 
                                               'speakers', 'stresslens', 'full transcript',
                                               'readability', 'sentiment']:
            continue
        
        # Get following siblings until next h2
        text_parts = []
        current = h2.find_next_sibling()
        
        while current and current.name != 'h2':
            if current.name in ['p', 'div']:
                text = current.get_text(strip=True)
                if text and len(text) > 5:
                    # Skip metadata
                    if not any(kw in text.lower() for kw in ['sentiment', 'moderation', 'readability', 
                                                              'flesch', 'loughran', 'harvard', 'vader',
                                                              'gunning', 'coleman', 'smog', 'dale-chall']):
                        # Skip timestamps and scores
                        if not re.match(r'^\d{2}:\d{2}:\d{2}', text) and not re.match(r'^[\d.]+$', text):
                            text_parts.append(text)
            current = current.find_next_sibling()
        
        if text_parts:
            combined = ' '.join(text_parts[:3])  # Take first few paragraphs
            if len(combined) > 10:
                segments.append({
                    'speaker': speaker,
                    'start_time': '',
                    'end_time': '',
                    'duration_seconds': 0,
                    'text': combined
                })
    
    return segments


def parse_transcript_method3(soup, page_text, url):
    """Method 3: Look for speaker names followed by colons or in bold."""
    segments = []
    
    # Common speaker patterns
    speaker_pattern = r'\b(Donald Trump|Dasha Burns|Reporter|Press|Journalist|[A-Z][a-z]+ [A-Z][a-z]+):\s*([^\n]+)'
    
    matches = re.findall(speaker_pattern, page_text)
    
    for speaker, text in matches:
        if text and len(text) > 10:
            segments.append({
                'speaker': speaker.strip(),
                'start_time': '',
                'end_time': '',
                'duration_seconds': 0,
                'text': text.strip()
            })
    
    return segments


def parse_transcript_method4(soup, page_text, url):
    """Method 4: Split by timestamp patterns."""
    segments = []
    
    # Split by timestamp pattern
    parts = re.split(r'(\d{2}:\d{2}:\d{2}-\d{2}:\d{2}:\d{2})', page_text)
    
    current_speaker = "Unknown"
    
    for i, part in enumerate(parts):
        # Check if previous part might be a speaker name
        if i > 0 and re.match(r'\d{2}:\d{2}:\d{2}', part):
            # Look back for speaker
            prev = parts[i-1].strip().split('\n')
            for line in reversed(prev[-5:]):
                line = line.strip()
                if line and len(line) < 50 and not re.search(r'\d{2}:\d{2}', line):
                    if not any(kw in line.lower() for kw in ['sentiment', 'score', 'moderation']):
                        current_speaker = line
                        break
        
        # Check if this part contains text after timestamp
        if i + 1 < len(parts):
            text = parts[i + 1].strip()
            lines = text.split('\n')
            clean_lines = []
            for line in lines[:10]:
                line = line.strip()
                if line.startswith(('Sentiment', 'Moderation', 'Readability')):
                    break
                if line and len(line) > 5:
                    clean_lines.append(line)
            
            if clean_lines:
                segments.append({
                    'speaker': current_speaker,
                    'start_time': part.split('-')[0] if '-' in part else '',
                    'end_time': '',
                    'duration_seconds': 0,
                    'text': ' '.join(clean_lines[:3])
                })
    
    return segments


def parse_transcript(html, url, debug=False):
    """Parse Factbase transcript HTML into structured data using multiple methods."""
    soup = BeautifulSoup(html, 'lxml')
    
    # Get title
    title_elem = soup.find('h1')
    if not title_elem:
        if debug:
            print("  DEBUG: No h1 found")
        return None
    
    full_title = title_elem.get_text(strip=True)
    
    # Parse event type
    event_type = "Unknown"
    title = full_title
    if ':' in full_title:
        parts = full_title.split(':', 1)
        event_type = parts[0].strip()
        title = parts[1].strip() if len(parts) > 1 else full_title
    
    # Extract date
    event_date = ""
    date_match = re.search(r'-\s*(\w+\s+\d{1,2},?\s*\d{4})\s*$', full_title)
    if date_match:
        date_str = date_match.group(1)
        for fmt in ['%B %d, %Y', '%B %d %Y']:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                event_date = dt.strftime('%Y-%m-%d')
                break
            except ValueError:
                continue
    
    # Extract location
    location = ""
    loc_match = re.search(r'\s+(?:in|at)\s+([^-]+?)(?:\s+-|\s*$)', full_title, re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).strip()
    
    # Get page text
    page_text = soup.get_text()
    
    # Try multiple parsing methods
    segments = None
    method_used = None
    
    # Method 1: ## pattern (most reliable for Factbase)
    segments = parse_transcript_method1(soup, page_text, url)
    if segments:
        method_used = "method1_hash"
    
    # Method 2: h2 tags
    if not segments:
        segments = parse_transcript_method2(soup, page_text, url)
        if segments:
            method_used = "method2_h2"
    
    # Method 3: Speaker: pattern
    if not segments:
        segments = parse_transcript_method3(soup, page_text, url)
        if segments:
            method_used = "method3_colon"
    
    # Method 4: Timestamp splitting
    if not segments:
        segments = parse_transcript_method4(soup, page_text, url)
        if segments:
            method_used = "method4_timestamp"
    
    if debug:
        print(f"  DEBUG: Method used: {method_used}, segments: {len(segments) if segments else 0}")
    
    if not segments:
        return None
    
    # Determine primary speaker
    speaker_words = {}
    for seg in segments:
        words = len(seg['text'].split())
        speaker_words[seg['speaker']] = speaker_words.get(seg['speaker'], 0) + words
    
    primary_speaker = max(speaker_words.keys(), key=lambda s: speaker_words[s]) if speaker_words else 'Unknown'
    
    # Generate ID
    id_match = re.search(r'/transcript/([^/]+)/?$', url)
    transcript_id = id_match.group(1) if id_match else hashlib.md5(url.encode()).hexdigest()[:16]
    
    return {
        'id': transcript_id,
        'url': url,
        'title': title,
        'primary_speaker': primary_speaker,
        'event_type': event_type,
        'event_date': event_date,
        'location': location,
        'segments': segments,
        'method': method_used
    }


def import_single(url, debug=False):
    """Import a single transcript."""
    try:
        html = fetch_transcript(url)
        
        # Save debug HTML if requested
        if debug:
            DEBUG_DIR.mkdir(exist_ok=True)
            slug = url.split("/transcript/")[-1][:50].replace("/", "_")
            with open(DEBUG_DIR / f"{slug}.html", "w") as f:
                f.write(html)
        
        data = parse_transcript(html, url, debug=debug)
        
        if not data or not data['segments']:
            return False, "No segments found"
        
        insert_transcript(
            transcript_id=data['id'],
            url=data['url'],
            title=data['title'],
            primary_speaker=data['primary_speaker'],
            event_type=data['event_type'],
            event_date=data['event_date'],
            location=data['location'],
            segments=data['segments'],
            topics=[],
            entities=[],
            raw_html=html
        )
        
        return True, f"{len(data['segments'])} segs ({data.get('method', '?')})"
        
    except requests.exceptions.HTTPError as e:
        return False, f"HTTP {e.response.status_code}"
    except Exception as e:
        return False, str(e)[:50]


def debug_single(url):
    """Debug a single URL and show what's happening."""
    print(f"Debugging: {url}")
    print()
    
    try:
        html = fetch_transcript(url)
        print(f"Fetched {len(html)} bytes")
        
        # Save HTML
        DEBUG_DIR.mkdir(exist_ok=True)
        with open(DEBUG_DIR / "debug_page.html", "w") as f:
            f.write(html)
        print(f"Saved to {DEBUG_DIR}/debug_page.html")
        
        soup = BeautifulSoup(html, 'lxml')
        page_text = soup.get_text()
        
        with open(DEBUG_DIR / "debug_text.txt", "w") as f:
            f.write(page_text)
        print(f"Saved text to {DEBUG_DIR}/debug_text.txt")
        
        print()
        print("=" * 50)
        print("H1 TITLE:")
        h1 = soup.find('h1')
        print(h1.get_text() if h1 else "NOT FOUND")
        
        print()
        print("=" * 50)
        print("H2 TAGS (first 10):")
        for h2 in soup.find_all('h2')[:10]:
            print(f"  - {h2.get_text()[:60]}")
        
        print()
        print("=" * 50)
        print("TIMESTAMP PATTERNS (first 10):")
        times = re.findall(r'\d{2}:\d{2}:\d{2}', page_text)[:10]
        print(times)
        
        print()
        print("=" * 50)
        print("## PATTERNS (first 10):")
        hashes = re.findall(r'##\s+[^\n]+', page_text)[:10]
        for h in hashes:
            print(f"  {h[:60]}")
        
        print()
        print("=" * 50)
        print("TRYING PARSE METHODS:")
        
        segments1 = parse_transcript_method1(soup, page_text, url)
        print(f"  Method 1 (## pattern): {len(segments1)} segments")
        
        segments2 = parse_transcript_method2(soup, page_text, url)
        print(f"  Method 2 (h2 tags): {len(segments2)} segments")
        
        segments3 = parse_transcript_method3(soup, page_text, url)
        print(f"  Method 3 (speaker:): {len(segments3)} segments")
        
        segments4 = parse_transcript_method4(soup, page_text, url)
        print(f"  Method 4 (timestamps): {len(segments4)} segments")
        
        # Show sample segments
        for name, segs in [("Method1", segments1), ("Method2", segments2)]:
            if segs:
                print()
                print(f"Sample from {name}:")
                for s in segs[:3]:
                    print(f"  [{s['speaker']}]: {s['text'][:80]}...")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("=" * 70)
    print("MENTION MARKETS - TRANSCRIPT IMPORTER")
    print("=" * 70)
    print()
    
    # Check for debug mode
    if len(sys.argv) > 1:
        if sys.argv[1] == "--debug" and len(sys.argv) > 2:
            debug_single(sys.argv[2])
            return
        elif sys.argv[1] == "--debug-first":
            urls = load_urls()
            if urls:
                debug_single(urls[0])
            return
        elif sys.argv[1] == "--help":
            print("Usage:")
            print("  python3 import_all.py                  # Import all transcripts")
            print("  python3 import_all.py --debug URL      # Debug a specific URL")
            print("  python3 import_all.py --debug-first    # Debug first URL in list")
            print("  python3 import_all.py --reset          # Reset progress and start over")
            return
        elif sys.argv[1] == "--reset":
            if PROGRESS_FILE.exists():
                PROGRESS_FILE.unlink()
                print("Progress reset.")
            return
    
    # Check database
    db_path = Path(__file__).parent / "data" / "transcripts.db"
    if not db_path.exists():
        print("Database not found. Initializing...")
        init_database()
    
    # Load URLs
    urls = load_urls()
    if not urls:
        print("No URLs to import!")
        return
    
    print(f"Found {len(urls)} transcript URLs")
    
    # Load progress
    progress = load_progress()
    completed = set(progress.get("completed", []))
    failed = set(progress.get("failed", []))
    no_segments = set(progress.get("no_segments", []))
    
    pending = [u for u in urls if u not in completed and u not in no_segments]
    
    print(f"Already completed: {len(completed)}")
    print(f"No segments (skipped): {len(no_segments)}")
    print(f"Pending: {len(pending)}")
    print()
    
    if not pending:
        print("All URLs already processed!")
        stats = get_database_stats()
        print(f"Database has {stats['total_transcripts']} transcripts")
        return
    
    print("Starting import (1.5s delay between requests)...")
    print("Press Ctrl+C to stop and resume later")
    print()
    print("TIP: If many fail, run: python3 import_all.py --debug-first")
    print()
    
    success = 0
    errors = 0
    no_seg_count = 0
    
    try:
        for i, url in enumerate(pending, 1):
            slug = url.split("/transcript/")[-1][:40]
            print(f"[{i}/{len(pending)}] {slug}...", end=" ", flush=True)
            
            # Debug first few if having issues
            debug = (i <= 3 and len(completed) == 0)
            
            ok, msg = import_single(url, debug=debug)
            
            if ok:
                completed.add(url)
                success += 1
                print(f"✓ {msg}")
            elif "No segments" in msg:
                no_segments.add(url)
                no_seg_count += 1
                print(f"⊘ {msg}")
            else:
                failed.add(url)
                errors += 1
                print(f"✗ {msg}")
            
            # Save progress every 10
            if i % 10 == 0:
                save_progress({
                    "completed": list(completed), 
                    "failed": list(failed),
                    "no_segments": list(no_segments)
                })
            
            time.sleep(1.5)
    
    except KeyboardInterrupt:
        print("\n\nStopped by user. Progress saved.")
    
    # Final save
    save_progress({
        "completed": list(completed), 
        "failed": list(failed),
        "no_segments": list(no_segments)
    })
    
    print()
    print("=" * 70)
    print(f"DONE: {success} imported, {no_seg_count} no segments, {errors} errors")
    print(f"Total completed: {len(completed)}/{len(urls)}")
    print("=" * 70)
    
    if no_seg_count > success:
        print()
        print("WARNING: Many transcripts had no segments!")
        print("Debug with: python3 import_all.py --debug-first")
        print("Check data/debug/ folder for saved HTML")
    
    # Stats
    try:
        stats = get_database_stats()
        print()
        print("DATABASE:")
        print(f"  Transcripts: {stats['total_transcripts']}")
        print(f"  Segments: {stats['total_segments']}")
        print(f"  Words: {stats['total_words']:,}")
    except:
        pass


if __name__ == "__main__":
    main()
