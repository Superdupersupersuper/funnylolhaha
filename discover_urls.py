#!/usr/bin/env python3
"""
Mention Markets - Comprehensive Transcript URL Discovery
This script discovers ALL transcript URLs from Factbase/Roll Call
by searching through years 2017-2025.

Run this to build a complete list of URLs, then use import_data.py to fetch them.
"""

import requests
import time
import json
import re
from pathlib import Path
from datetime import datetime

# Output file for discovered URLs
OUTPUT_FILE = Path(__file__).parent / "data" / "all_transcript_urls.json"

# Headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

# Google search to find URLs (we'll use DuckDuckGo HTML version which doesn't need API)
def search_duckduckgo(query: str, max_results: int = 30) -> list:
    """Search DuckDuckGo and extract URLs."""
    urls = []
    
    # DuckDuckGo HTML search
    search_url = f"https://html.duckduckgo.com/html/?q={query}"
    
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=30)
        
        # Extract URLs from results
        pattern = r'https://rollcall\.com/factbase/trump/transcript/[^"\'>\s]+'
        found = re.findall(pattern, response.text)
        urls.extend(found)
        
    except Exception as e:
        print(f"Search error: {e}")
    
    return list(set(urls))


def discover_urls_by_year(year: int) -> list:
    """Discover transcript URLs for a specific year."""
    urls = []
    
    # Search queries for this year
    queries = [
        f'site:rollcall.com/factbase/trump/transcript {year}',
        f'site:rollcall.com "donald trump" transcript {year}',
    ]
    
    # Also search by month
    months = ['january', 'february', 'march', 'april', 'may', 'june',
              'july', 'august', 'september', 'october', 'november', 'december']
    
    for month in months:
        queries.append(f'site:rollcall.com/factbase/trump/transcript {month} {year}')
    
    for query in queries:
        print(f"  Searching: {query[:60]}...")
        found = search_duckduckgo(query)
        urls.extend(found)
        time.sleep(2)  # Rate limiting
    
    return list(set(urls))


def discover_urls_by_type() -> list:
    """Discover transcript URLs by event type."""
    urls = []
    
    event_types = [
        'rally', 'speech', 'press conference', 'interview',
        'remarks', 'address', 'briefing', 'debate'
    ]
    
    for event_type in event_types:
        print(f"  Searching event type: {event_type}")
        query = f'site:rollcall.com/factbase/trump/transcript {event_type}'
        found = search_duckduckgo(query)
        urls.extend(found)
        time.sleep(2)
    
    return list(set(urls))


def crawl_transcript_page_for_links(url: str) -> list:
    """Crawl a transcript page to find links to other transcripts."""
    urls = []
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        pattern = r'https://rollcall\.com/factbase/trump/transcript/[^"\'>\s]+'
        found = re.findall(pattern, response.text)
        urls.extend(found)
    except Exception as e:
        print(f"Crawl error for {url}: {e}")
    
    return list(set(urls))


def main():
    print("=" * 60)
    print("MENTION MARKETS - TRANSCRIPT URL DISCOVERY")
    print("=" * 60)
    print()
    
    all_urls = set()
    
    # Load existing URLs if available
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            data = json.load(f)
            all_urls = set(data.get('urls', []))
            print(f"Loaded {len(all_urls)} existing URLs")
    
    # Discover by year (2017-2025)
    print("\n[1/3] Discovering URLs by year...")
    for year in range(2017, 2026):
        print(f"\nYear {year}:")
        urls = discover_urls_by_year(year)
        before = len(all_urls)
        all_urls.update(urls)
        print(f"  Found {len(urls)} URLs, {len(all_urls) - before} new")
    
    # Discover by event type
    print("\n[2/3] Discovering URLs by event type...")
    urls = discover_urls_by_type()
    before = len(all_urls)
    all_urls.update(urls)
    print(f"Found {len(urls)} URLs, {len(all_urls) - before} new")
    
    # Crawl known pages for more links
    print("\n[3/3] Crawling known pages for additional links...")
    urls_to_crawl = list(all_urls)[:50]  # Crawl first 50
    for i, url in enumerate(urls_to_crawl):
        if i % 10 == 0:
            print(f"  Crawling page {i+1}/{len(urls_to_crawl)}...")
        found = crawl_transcript_page_for_links(url)
        all_urls.update(found)
        time.sleep(1)
    
    # Save results
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    urls_list = sorted(list(all_urls))
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump({
            'discovered_at': datetime.now().isoformat(),
            'total_count': len(urls_list),
            'urls': urls_list
        }, f, indent=2)
    
    print()
    print("=" * 60)
    print(f"DISCOVERY COMPLETE")
    print(f"  Total URLs found: {len(urls_list)}")
    print(f"  Saved to: {OUTPUT_FILE}")
    print("=" * 60)
    print()
    print("Next step: Run the import script to fetch all transcripts:")
    print("  python3 import_all.py")


# KNOWN URLS - Comprehensive list compiled from searches
# This is a starting point - the discovery script will find more
KNOWN_URLS = [
    # 2017
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-washington-dc-january-20-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-uss-gerald-ford-march-2-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-rally-harrisburg-pa-april-29-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-interview-nbc-lester-holt-may-11-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-veterans-act-charlottesville-august-12-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-infrastructure-charlottesville-august-15-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-united-nations-general-assembly-september-19-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-luther-strange-rally-huntsville-alabama-september-22-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-interview-sean-hannity-october-11-2017/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-make-america-great-again-pensacola-december-8-2017/",
    
    # 2018
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-march-for-life-january-19-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-national-prayer-breakfast-february-8-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-interview-sean-hannity-fox-june-12-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-duluth-minnesota-june-20-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-make-america-great-again-rally-great-falls-montana-july-5-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-vladimir-putin-helsinki-july-16-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-us-steel-illinois-july-26-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-un-general-assembly-september-25-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-maga-rally-houston-tx-october-22-2018/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-future-farmers-america-indianapolis-october-27-2018/",
    
    # 2019
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-state-of-the-union-february-5-2019/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-cpac-march-2-2019/",
    
    # 2020
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-state-of-the-union-february-4-2020/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-cpac-february-29-2020/",
    
    # 2024
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-campaign-rally-new-york-madison-square-garden-october-27-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-campaign-rally-reading-pennsylvania-november-4-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-campaign-rally-allentown-pennsylvania-october-29-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-phoenix-december-22-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-charlotte-north-carolina-july-24-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-las-vegas-june-9-2024/",
    
    # 2025
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-washington-january-19-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-commencement-address-west-point-usma-may-24-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-january-28-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-january-31-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-february-12-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-march-5-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-april-28-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-briefing-karoline-leavitt-the-white-house-june-2-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-june-11-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-july-7-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-august-12-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-august-28-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-jd-vance-economy-la-crosse-wisconsin-august-28-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-interview-jd-vance-lara-trump-fox-news-september-6-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-charlie-kirk-podcast-guest-host-september-15-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-tax-spending-cuts-howell-michigan-september-17-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-charlie-kirk-memorial-glendale-arizona-september-21-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-80th-united-nations-general-assembly-september-23-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-department-of-defense-leaders-quantico-september-30-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-space-force-relocation-alabama-september-2-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-interview-jd-vance-bartiromo-fox-sunday-morning-futures-october-12-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-anniversary-usmc-california-october-18-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-turning-point-usa-oxford-mississippi-october-30-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-usmc-ball-november-8-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-bilat-mohammed-bin-salman-saudi-arabia-november-18-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-thanksgiving-troops-kentucky-november-26-2025/",
]


if __name__ == '__main__':
    # First, save known URLs
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Saving {len(KNOWN_URLS)} known URLs...")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump({
            'discovered_at': datetime.now().isoformat(),
            'total_count': len(KNOWN_URLS),
            'urls': sorted(list(set(KNOWN_URLS)))
        }, f, indent=2)
    
    print(f"Saved to {OUTPUT_FILE}")
    print()
    print("To discover more URLs automatically, uncomment and run main()")
    print("Or manually add URLs to the KNOWN_URLS list")
    print()
    print("To import all transcripts, run:")
    print("  python3 import_all.py")
    
    # Uncomment to run full discovery (takes a while)
    # main()
