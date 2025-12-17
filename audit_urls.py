#!/usr/bin/env python3
"""
URL Audit Script
Compares canonical URL list against database to identify missing or empty transcripts

Usage:
    python3 audit_urls.py [--source missing_urls.txt]

Exit codes:
    0 - All URLs accounted for and have content
    1 - Found missing URLs or empty transcripts
"""

import sqlite3
import sys
import argparse
from typing import Set, Dict, List, Tuple

DB_PATH = 'data/transcripts.db'

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.END}\n")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def normalize_url(url: str) -> str:
    """
    Normalize URL for comparison (remove trailing slashes, etc.)
    """
    url = url.strip()
    if url.endswith('/'):
        url = url[:-1]
    return url

def load_canonical_urls(source_file: str) -> Set[str]:
    """
    Load canonical URL list from file
    
    Supports:
    - missing_urls.txt format: "ID|URL"
    - Plain text file with one URL per line
    """
    urls = set()
    
    try:
        with open(source_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Handle "ID|URL" format
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        url = parts[1]
                    else:
                        continue
                else:
                    url = line
                
                urls.add(normalize_url(url))
        
        print(f"Loaded {len(urls)} URLs from {source_file}")
        return urls
    
    except FileNotFoundError:
        print_error(f"File not found: {source_file}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Error reading {source_file}: {e}")
        sys.exit(1)

def get_db_urls(conn: sqlite3.Connection) -> Dict[str, Dict]:
    """
    Get all URLs from database with their metadata
    
    Returns:
        Dict mapping normalized URL to {id, word_count, title, date}
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, url, word_count, title, date
        FROM transcripts
    """)
    
    db_urls = {}
    for row in cursor.fetchall():
        url = normalize_url(row[1])
        db_urls[url] = {
            'id': row[0],
            'word_count': row[2],
            'title': row[3],
            'date': row[4]
        }
    
    return db_urls

def audit_urls(canonical_urls: Set[str], db_urls: Dict[str, Dict]) -> Tuple[bool, Dict]:
    """
    Compare canonical URLs against database
    
    Returns:
        (all_good, report_dict)
    """
    report = {
        'missing_from_db': [],
        'empty_in_db': [],
        'present_and_complete': [],
        'extra_in_db': []
    }
    
    # Check each canonical URL
    for url in canonical_urls:
        if url not in db_urls:
            report['missing_from_db'].append(url)
        else:
            db_entry = db_urls[url]
            if db_entry['word_count'] == 0:
                report['empty_in_db'].append({
                    'url': url,
                    'id': db_entry['id'],
                    'title': db_entry['title'],
                    'date': db_entry['date']
                })
            else:
                report['present_and_complete'].append(url)
    
    # Check for URLs in DB but not in canonical list
    for url in db_urls:
        if url not in canonical_urls:
            report['extra_in_db'].append({
                'url': url,
                'id': db_urls[url]['id'],
                'title': db_urls[url]['title'],
                'word_count': db_urls[url]['word_count']
            })
    
    all_good = (
        len(report['missing_from_db']) == 0 and
        len(report['empty_in_db']) == 0
    )
    
    return all_good, report

def print_report(report: Dict):
    """Print audit report"""
    
    # Missing from DB
    if report['missing_from_db']:
        print_header(f"MISSING FROM DATABASE ({len(report['missing_from_db'])})")
        print_error(f"These URLs are in the canonical list but NOT in the database:")
        for url in report['missing_from_db'][:20]:
            print(f"  - {url}")
        if len(report['missing_from_db']) > 20:
            print(f"  ... and {len(report['missing_from_db']) - 20} more")
    
    # Empty in DB
    if report['empty_in_db']:
        print_header(f"EMPTY IN DATABASE ({len(report['empty_in_db'])})")
        print_error(f"These URLs are in DB but have word_count = 0:")
        for entry in report['empty_in_db'][:20]:
            print(f"  - ID {entry['id']}: {entry['date']} - {entry['title'][:50]}")
            print(f"    {entry['url']}")
        if len(report['empty_in_db']) > 20:
            print(f"  ... and {len(report['empty_in_db']) - 20} more")
    
    # Present and complete
    if report['present_and_complete']:
        print_header(f"PRESENT AND COMPLETE ({len(report['present_and_complete'])})")
        print_success(f"These URLs are in DB with content")
    
    # Extra in DB (informational only)
    if report['extra_in_db']:
        print_header(f"EXTRA IN DATABASE ({len(report['extra_in_db'])})")
        print_warning(f"These URLs are in DB but NOT in canonical list:")
        print("(This is OK if the canonical list is incomplete)")
        for entry in report['extra_in_db'][:10]:
            print(f"  - ID {entry['id']}: {entry['title'][:50]} ({entry['word_count']} words)")
        if len(report['extra_in_db']) > 10:
            print(f"  ... and {len(report['extra_in_db']) - 10} more")

def run_audit(source_file: str) -> bool:
    """
    Run URL audit
    
    Returns:
        True if all URLs are accounted for and have content
    """
    print_header("URL AUDIT")
    print(f"Canonical source: {source_file}")
    print(f"Database: {DB_PATH}")
    
    # Load canonical URLs
    canonical_urls = load_canonical_urls(source_file)
    
    # Connect to database
    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.Error as e:
        print_error(f"Failed to connect to database: {e}")
        return False
    
    # Get DB URLs
    db_urls = get_db_urls(conn)
    print(f"Found {len(db_urls)} URLs in database")
    
    # Run audit
    all_good, report = audit_urls(canonical_urls, db_urls)
    
    # Print report
    print_report(report)
    
    # Summary
    print_header("AUDIT SUMMARY")
    
    if all_good:
        print_success("ALL CANONICAL URLs ACCOUNTED FOR ✓")
        print(f"\n  • {len(report['present_and_complete'])} URLs present with content")
        print(f"  • 0 URLs missing from DB")
        print(f"  • 0 URLs empty in DB")
        if report['extra_in_db']:
            print(f"\n  ℹ {len(report['extra_in_db'])} extra URLs in DB (not in canonical list)")
    else:
        print_error("AUDIT FAILED ✗")
        print("\nIssues found:")
        if report['missing_from_db']:
            print(f"  • {len(report['missing_from_db'])} URL(s) missing from database")
        if report['empty_in_db']:
            print(f"  • {len(report['empty_in_db'])} URL(s) in DB but empty (need scraping)")
    
    conn.close()
    return all_good

def main():
    parser = argparse.ArgumentParser(description='Audit transcript URLs against database')
    parser.add_argument(
        '--source',
        default='missing_urls.txt',
        help='Source file with canonical URLs (default: missing_urls.txt)'
    )
    
    args = parser.parse_args()
    
    success = run_audit(args.source)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
