#!/usr/bin/env python3
"""
Data Verification Script
Checks database integrity and identifies missing/incomplete transcripts

Usage:
    python3 verify_data.py

Exit codes:
    0 - All checks passed
    1 - Found issues (empty transcripts, duplicates, etc.)
"""

import sqlite3
import sys
from datetime import datetime
from typing import Dict, List, Tuple

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

def check_empty_transcripts(conn: sqlite3.Connection) -> Tuple[bool, List[Dict]]:
    """
    Check for transcripts with missing content (word_count = 0 or empty full_dialogue)
    
    Returns:
        (passed, list of problematic transcripts)
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, date, title, word_count, url
        FROM transcripts
        WHERE word_count = 0 OR full_dialogue = '' OR full_dialogue IS NULL
        ORDER BY date DESC
    """)
    
    empty_transcripts = []
    for row in cursor.fetchall():
        empty_transcripts.append({
            'id': row[0],
            'date': row[1],
            'title': row[2],
            'word_count': row[3],
            'url': row[4]
        })
    
    if empty_transcripts:
        print_error(f"Found {len(empty_transcripts)} transcript(s) with missing content:")
        for t in empty_transcripts[:10]:  # Show first 10
            print(f"  - ID {t['id']}: {t['date']} - {t['title'][:60]}")
            print(f"    word_count={t['word_count']}, URL: {t['url']}")
        if len(empty_transcripts) > 10:
            print(f"  ... and {len(empty_transcripts) - 10} more")
        return False, empty_transcripts
    else:
        print_success("No empty transcripts found")
        return True, []

def check_duplicate_urls(conn: sqlite3.Connection) -> Tuple[bool, List[str]]:
    """
    Check for duplicate URLs in the database
    
    Returns:
        (passed, list of duplicate URLs)
    """
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT url, COUNT(*) as count
        FROM transcripts
        GROUP BY url
        HAVING COUNT(*) > 1
        ORDER BY count DESC
    """)
    
    duplicates = []
    for row in cursor.fetchall():
        duplicates.append(f"{row[0]} (appears {row[1]} times)")
    
    if duplicates:
        print_error(f"Found {len(duplicates)} duplicate URL(s):")
        for dup in duplicates[:10]:
            print(f"  - {dup}")
        if len(duplicates) > 10:
            print(f"  ... and {len(duplicates) - 10} more")
        return False, duplicates
    else:
        print_success("No duplicate URLs found")
        return True, []

def check_date_range(conn: sqlite3.Connection) -> Tuple[bool, Dict]:
    """
    Check date range coverage and identify any anomalies
    
    Returns:
        (passed, date_info)
    """
    cursor = conn.cursor()
    
    # Get date range
    cursor.execute("""
        SELECT 
            MIN(date) as min_date,
            MAX(date) as max_date,
            COUNT(*) as total_count,
            COUNT(DISTINCT date) as unique_dates
        FROM transcripts
        WHERE date LIKE '____-__-__'  -- Valid YYYY-MM-DD format
    """)
    
    row = cursor.fetchone()
    date_info = {
        'min_date': row[0],
        'max_date': row[1],
        'total_count': row[2],
        'unique_dates': row[3]
    }
    
    # Check for invalid dates
    cursor.execute("""
        SELECT id, date, title
        FROM transcripts
        WHERE date NOT LIKE '____-__-__' OR date IS NULL
        LIMIT 10
    """)
    
    invalid_dates = cursor.fetchall()
    
    if invalid_dates:
        print_warning(f"Found {len(invalid_dates)} transcript(s) with invalid dates:")
        for row in invalid_dates:
            print(f"  - ID {row[0]}: date='{row[1]}', title={row[2][:50]}")
        date_info['has_invalid_dates'] = True
    else:
        date_info['has_invalid_dates'] = False
    
    print_success(f"Date range: {date_info['min_date']} to {date_info['max_date']}")
    print(f"  Total transcripts: {date_info['total_count']}")
    print(f"  Unique dates: {date_info['unique_dates']}")
    
    return not date_info['has_invalid_dates'], date_info

def check_database_stats(conn: sqlite3.Connection) -> Dict:
    """Get overall database statistics"""
    cursor = conn.cursor()
    
    stats = {}
    
    # Total transcripts
    cursor.execute("SELECT COUNT(*) FROM transcripts")
    stats['total_transcripts'] = cursor.fetchone()[0]
    
    # Total words
    cursor.execute("SELECT SUM(word_count) FROM transcripts WHERE word_count > 0")
    stats['total_words'] = cursor.fetchone()[0] or 0
    
    # Average words per transcript
    cursor.execute("SELECT AVG(word_count) FROM transcripts WHERE word_count > 0")
    stats['avg_words'] = cursor.fetchone()[0] or 0
    
    # Speech types distribution
    cursor.execute("""
        SELECT speech_type, COUNT(*) as count
        FROM transcripts
        GROUP BY speech_type
        ORDER BY count DESC
    """)
    stats['speech_types'] = cursor.fetchall()
    
    return stats

def run_verification() -> bool:
    """
    Run all verification checks
    
    Returns:
        True if all checks passed, False otherwise
    """
    print_header("TRANSCRIPT DATABASE VERIFICATION")
    print(f"Database: {DB_PATH}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.Error as e:
        print_error(f"Failed to connect to database: {e}")
        return False
    
    all_passed = True
    
    # Check 1: Empty transcripts (CRITICAL)
    print_header("CHECK 1: Empty Transcripts")
    passed, empty_list = check_empty_transcripts(conn)
    all_passed = all_passed and passed
    
    # Check 2: Duplicate URLs
    print_header("CHECK 2: Duplicate URLs")
    passed, dup_list = check_duplicate_urls(conn)
    all_passed = all_passed and passed
    
    # Check 3: Date range
    print_header("CHECK 3: Date Range & Validity")
    passed, date_info = check_date_range(conn)
    all_passed = all_passed and passed
    
    # Statistics
    print_header("DATABASE STATISTICS")
    stats = check_database_stats(conn)
    print(f"Total transcripts: {stats['total_transcripts']}")
    print(f"Total words: {stats['total_words']:,}")
    print(f"Average words per transcript: {stats['avg_words']:.0f}")
    print("\nSpeech types:")
    for speech_type, count in stats['speech_types'][:10]:
        print(f"  - {speech_type}: {count}")
    
    # Final summary
    print_header("VERIFICATION SUMMARY")
    
    if all_passed:
        print_success("ALL CHECKS PASSED ✓")
        print("\nDatabase is healthy:")
        print("  • No empty transcripts")
        print("  • No duplicate URLs")
        print("  • Valid date ranges")
    else:
        print_error("VERIFICATION FAILED ✗")
        print("\nIssues found:")
        if empty_list:
            print(f"  • {len(empty_list)} empty transcript(s) need scraping")
        if dup_list:
            print(f"  • {len(dup_list)} duplicate URL(s) need cleanup")
        if date_info.get('has_invalid_dates'):
            print("  • Some transcripts have invalid dates")
    
    conn.close()
    return all_passed

if __name__ == '__main__':
    success = run_verification()
    sys.exit(0 if success else 1)
