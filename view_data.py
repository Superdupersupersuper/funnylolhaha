#!/usr/bin/env python3
"""
Script to view and analyze the scraped transcript data
"""
import sqlite3
from datetime import datetime

DB_PATH = './data/transcripts.db'

def get_stats():
    """Get database statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Total transcripts
    cursor.execute("SELECT COUNT(*) FROM transcripts")
    total = cursor.fetchone()[0]

    # Date range
    cursor.execute("SELECT MIN(date), MAX(date) FROM transcripts WHERE date != ''")
    date_range = cursor.fetchone()

    # Speech types
    cursor.execute("""
        SELECT speech_type, COUNT(*) as count
        FROM transcripts
        GROUP BY speech_type
        ORDER BY count DESC
    """)
    speech_types = cursor.fetchall()

    # Total words
    cursor.execute("SELECT SUM(word_count) FROM transcripts")
    total_words = cursor.fetchone()[0] or 0

    # Recent transcripts
    cursor.execute("""
        SELECT title, date, speech_type, word_count
        FROM transcripts
        ORDER BY id DESC
        LIMIT 10
    """)
    recent = cursor.fetchall()

    conn.close()

    return {
        'total': total,
        'date_range': date_range,
        'speech_types': speech_types,
        'total_words': total_words,
        'recent': recent
    }

def main():
    print("="*80)
    print("TRUMP TRANSCRIPT DATABASE - STATISTICS")
    print("="*80)

    stats = get_stats()

    print(f"\n📊 OVERVIEW")
    print(f"  Total Transcripts: {stats['total']:,}")
    print(f"  Total Words: {stats['total_words']:,}")
    if stats['date_range'][0] and stats['date_range'][1]:
        print(f"  Date Range: {stats['date_range'][0]} to {stats['date_range'][1]}")

    print(f"\n📑 SPEECH TYPES")
    for speech_type, count in stats['speech_types']:
        percentage = (count / stats['total']) * 100
        print(f"  {speech_type:30} {count:4} ({percentage:5.1f}%)")

    print(f"\n📝 RECENT TRANSCRIPTS")
    for i, (title, date, stype, words) in enumerate(stats['recent'], 1):
        print(f"  {i:2}. [{date:15}] {title[:50]:50} ({words:,} words)")

    print(f"\n{'='*80}")

if __name__ == '__main__':
    main()
