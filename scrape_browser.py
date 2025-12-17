#!/usr/bin/env python3
"""
Mention Markets - Browser-Based URL Scraper
Gets ALL transcript URLs from 2016 to present.

SETUP:
    pip3 install playwright
    playwright install chromium

USAGE:
    python3 scrape_browser.py
"""

import json
import time
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run:")
    print("  pip3 install playwright")
    print("  playwright install chromium")
    exit(1)

OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "all_transcript_urls.json"
TRANSCRIPTS_URL = "https://rollcall.com/factbase/trump/transcripts/"

EVENT_TYPES = ["Interview", "Press Briefing", "Press Gaggle", "Remarks", "Speech", "Vlog"]
CUTOFF_YEAR = 2016


def extract_year_from_url(url):
    """Extract year from URL."""
    match = re.search(r'-(\d{4})/?$', url)
    if match:
        return int(match.group(1))
    return None


def categorize_url(url):
    """Determine event type from URL slug."""
    slug = url.lower()
    if "press-gaggle" in slug or "gaggle" in slug:
        return "Press Gaggle"
    elif "press-briefing" in slug or "briefing" in slug or "press-conference" in slug:
        return "Press Briefing"
    elif "interview" in slug:
        return "Interview"
    elif "vlog" in slug:
        return "Vlog"
    elif any(x in slug for x in ["speech", "address", "rally", "convention"]):
        return "Speech"
    elif any(x in slug for x in ["remarks", "statement", "bilat", "meeting"]):
        return "Remarks"
    return "Other"


def main():
    print("=" * 70)
    print("SCRAPING ALL TRANSCRIPTS (2016 to present)")
    print("=" * 70)
    print()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("Loading page...")
        page.goto(TRANSCRIPTS_URL, timeout=120000)
        time.sleep(8)
        
        print("Scrolling to load all transcripts...")
        print("(This will take several minutes - don't close the browser)")
        print()
        
        last_count = 0
        no_change = 0
        scroll_num = 0
        
        while no_change < 10:  # Stop after 10 scrolls with no new content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.8)
            
            links = page.query_selector_all("a[href*='/factbase/trump/transcript/']")
            count = len(links)
            scroll_num += 1
            
            if count == last_count:
                no_change += 1
            else:
                no_change = 0
                if scroll_num % 20 == 0:
                    print(f"  {count} transcripts loaded...")
            
            last_count = count
        
        print(f"\nExtracting {last_count} URLs...")
        
        links = page.query_selector_all("a[href*='/factbase/trump/transcript/']")
        
        all_urls = []
        seen = set()
        
        for link in links:
            href = link.get_attribute("href")
            if href and href not in seen:
                if href.startswith("/"):
                    href = "https://rollcall.com" + href
                seen.add(href)
                all_urls.append(href)
        
        browser.close()
    
    print(f"Found {len(all_urls)} unique URLs")
    
    # Filter to 2016+
    filtered = []
    for url in all_urls:
        year = extract_year_from_url(url)
        if year is None or year >= CUTOFF_YEAR:
            filtered.append(url)
    
    print(f"After filtering to 2016+: {len(filtered)} URLs")
    
    # Organize by event type
    by_type = defaultdict(list)
    for url in filtered:
        event_type = categorize_url(url)
        slug = url.split("/transcript/")[-1].rstrip("/")
        year = extract_year_from_url(url)
        
        by_type[event_type].append({
            "slug": slug,
            "url": url,
            "event_type": event_type,
            "year": year
        })
    
    # Print summary
    print()
    print("BY EVENT TYPE:")
    for et in EVENT_TYPES + ["Other"]:
        if by_type.get(et):
            print(f"  {et}: {len(by_type[et])}")
    
    # Year breakdown
    print()
    print("BY YEAR:")
    year_counts = defaultdict(int)
    for url in filtered:
        year = extract_year_from_url(url)
        year_counts[year or "Unknown"] += 1
    for year in sorted([y for y in year_counts.keys() if isinstance(y, int)]):
        print(f"  {year}: {year_counts[year]}")
    if "Unknown" in year_counts:
        print(f"  Unknown: {year_counts['Unknown']}")
    
    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    output = {
        "scraped_at": datetime.now().isoformat(),
        "cutoff_year": CUTOFF_YEAR,
        "total_count": len(filtered),
        "by_event_type": {
            et: {"count": len(by_type.get(et, [])), "transcripts": by_type.get(et, [])}
            for et in EVENT_TYPES + ["Other"] if by_type.get(et)
        },
        "urls": filtered
    }
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    print()
    print(f"Saved to: {OUTPUT_FILE}")
    print()
    print("NEXT: Run these commands:")
    print("  python3 import_data.py --init")
    print("  python3 import_all.py")


if __name__ == "__main__":
    main()
