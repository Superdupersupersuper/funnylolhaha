"""
Mention Markets - Database Schema and Models
SQLite database for storing political transcripts
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DATABASE_PATH = Path(__file__).parent.parent / "data" / "transcripts.db"

def init_database():
    """Initialize the SQLite database with all required tables."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Main transcripts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id TEXT PRIMARY KEY,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            primary_speaker TEXT NOT NULL,
            event_type TEXT,
            event_date DATE,
            location TEXT,
            total_words INTEGER DEFAULT 0,
            total_duration_seconds INTEGER DEFAULT 0,
            topics TEXT,  -- JSON array
            entities TEXT,  -- JSON array
            raw_html TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Speakers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS speakers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT,
            headshot_url TEXT,
            total_transcripts INTEGER DEFAULT 0,
            total_segments INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Transcript segments (individual speech segments)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcript_id TEXT NOT NULL,
            speaker_id INTEGER NOT NULL,
            speaker_name TEXT NOT NULL,
            segment_index INTEGER NOT NULL,
            start_time TEXT,
            end_time TEXT,
            duration_seconds INTEGER,
            text TEXT NOT NULL,
            word_count INTEGER DEFAULT 0,
            sentiment_vader REAL,
            sentiment_label TEXT,
            topics TEXT,  -- JSON array
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transcript_id) REFERENCES transcripts(id),
            FOREIGN KEY (speaker_id) REFERENCES speakers(id)
        )
    """)
    
    # Full-text search index on segments
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
            text,
            speaker_name,
            content='segments',
            content_rowid='id'
        )
    """)
    
    # Triggers to keep FTS index in sync
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
            INSERT INTO segments_fts(rowid, text, speaker_name) 
            VALUES (new.id, new.text, new.speaker_name);
        END
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
            INSERT INTO segments_fts(segments_fts, rowid, text, speaker_name) 
            VALUES('delete', old.id, old.text, old.speaker_name);
        END
    """)
    
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
            INSERT INTO segments_fts(segments_fts, rowid, text, speaker_name) 
            VALUES('delete', old.id, old.text, old.speaker_name);
            INSERT INTO segments_fts(rowid, text, speaker_name) 
            VALUES (new.id, new.text, new.speaker_name);
        END
    """)
    
    # Scrape queue for tracking URLs to fetch
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
            priority INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            last_attempt TIMESTAMP,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_date ON transcripts(event_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_speaker ON transcripts(primary_speaker)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_type ON transcripts(event_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_segments_transcript ON segments(transcript_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_segments_speaker ON segments(speaker_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_segments_speaker_name ON segments(speaker_name)")
    
    conn.commit()
    conn.close()
    
    print(f"Database initialized at {DATABASE_PATH}")


class Database:
    """Database connection manager."""
    
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        
    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self.conn.cursor()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        self.conn.close()


def get_or_create_speaker(cursor, name: str, headshot_url: str = None) -> int:
    """Get existing speaker or create new one. Returns speaker ID."""
    cursor.execute("SELECT id FROM speakers WHERE name = ?", (name,))
    row = cursor.fetchone()
    
    if row:
        return row[0]
    
    cursor.execute(
        "INSERT INTO speakers (name, headshot_url) VALUES (?, ?)",
        (name, headshot_url)
    )
    return cursor.lastrowid


def insert_transcript(
    transcript_id: str,
    url: str,
    title: str,
    primary_speaker: str,
    event_type: str,
    event_date: str,
    location: str,
    segments: List[Dict],
    topics: List[str] = None,
    entities: List[str] = None,
    raw_html: str = None
):
    """Insert a complete transcript with all segments."""
    
    with Database() as cursor:
        # Calculate totals
        total_words = sum(s.get('word_count', len(s['text'].split())) for s in segments)
        total_duration = sum(s.get('duration_seconds', 0) for s in segments)
        
        # Insert main transcript
        cursor.execute("""
            INSERT OR REPLACE INTO transcripts 
            (id, url, title, primary_speaker, event_type, event_date, location, 
             total_words, total_duration_seconds, topics, entities, raw_html, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            transcript_id, url, title, primary_speaker, event_type, event_date, location,
            total_words, total_duration, 
            json.dumps(topics) if topics else None,
            json.dumps(entities) if entities else None,
            raw_html
        ))
        
        # Delete existing segments for this transcript (for updates)
        cursor.execute("DELETE FROM segments WHERE transcript_id = ?", (transcript_id,))
        
        # Insert segments
        for idx, seg in enumerate(segments):
            speaker_id = get_or_create_speaker(cursor, seg['speaker'], seg.get('headshot_url'))
            
            cursor.execute("""
                INSERT INTO segments 
                (transcript_id, speaker_id, speaker_name, segment_index, start_time, end_time,
                 duration_seconds, text, word_count, sentiment_vader, sentiment_label, topics)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transcript_id, speaker_id, seg['speaker'], idx,
                seg.get('start_time'), seg.get('end_time'), seg.get('duration_seconds'),
                seg['text'], len(seg['text'].split()),
                seg.get('sentiment_vader'), seg.get('sentiment_label'),
                json.dumps(seg.get('topics')) if seg.get('topics') else None
            ))
        
        # Update speaker stats
        cursor.execute("""
            UPDATE speakers SET 
                total_segments = (SELECT COUNT(*) FROM segments WHERE speaker_id = speakers.id),
                total_transcripts = (SELECT COUNT(DISTINCT transcript_id) FROM segments WHERE speaker_id = speakers.id)
        """)
        
    return transcript_id


def search_segments(
    query: str,
    speaker: str = None,
    event_type: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict]:
    """Full-text search across all segments with filters."""
    
    with Database() as cursor:
        # Build the query
        sql = """
            SELECT 
                s.id, s.transcript_id, s.speaker_name, s.segment_index,
                s.start_time, s.text, s.word_count, s.sentiment_label,
                t.title, t.event_type, t.event_date, t.location, t.primary_speaker,
                highlight(segments_fts, 0, '<mark>', '</mark>') as highlighted_text
            FROM segments_fts 
            JOIN segments s ON segments_fts.rowid = s.id
            JOIN transcripts t ON s.transcript_id = t.id
            WHERE segments_fts MATCH ?
        """
        params = [query]
        
        if speaker and speaker != 'all':
            sql += " AND s.speaker_name = ?"
            params.append(speaker)
        
        if event_type and event_type != 'all':
            sql += " AND t.event_type = ?"
            params.append(event_type)
        
        if start_date:
            sql += " AND t.event_date >= ?"
            params.append(start_date)
        
        if end_date:
            sql += " AND t.event_date <= ?"
            params.append(end_date)
        
        sql += " ORDER BY t.event_date DESC, s.segment_index ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(sql, params)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'segment_id': row['id'],
                'transcript_id': row['transcript_id'],
                'speaker': row['speaker_name'],
                'segment_index': row['segment_index'],
                'time': row['start_time'],
                'text': row['text'],
                'highlighted_text': row['highlighted_text'],
                'word_count': row['word_count'],
                'sentiment': row['sentiment_label'],
                'transcript_title': row['title'],
                'event_type': row['event_type'],
                'event_date': row['event_date'],
                'location': row['location'],
                'primary_speaker': row['primary_speaker']
            })
        
        return results


def get_all_transcripts(
    speaker: str = None,
    event_type: str = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict]:
    """Get all transcripts with optional filters."""
    
    with Database() as cursor:
        sql = "SELECT * FROM transcripts WHERE 1=1"
        params = []
        
        if speaker and speaker != 'all':
            sql += " AND primary_speaker = ?"
            params.append(speaker)
        
        if event_type and event_type != 'all':
            sql += " AND event_type = ?"
            params.append(event_type)
        
        sql += " ORDER BY event_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(sql, params)
        
        return [dict(row) for row in cursor.fetchall()]


def get_transcript_with_segments(transcript_id: str) -> Optional[Dict]:
    """Get a single transcript with all its segments."""
    
    with Database() as cursor:
        cursor.execute("SELECT * FROM transcripts WHERE id = ?", (transcript_id,))
        transcript = cursor.fetchone()
        
        if not transcript:
            return None
        
        result = dict(transcript)
        
        cursor.execute("""
            SELECT * FROM segments 
            WHERE transcript_id = ? 
            ORDER BY segment_index
        """, (transcript_id,))
        
        result['segments'] = [dict(row) for row in cursor.fetchall()]
        
        return result


def get_all_speakers() -> List[Dict]:
    """Get all speakers with their stats."""
    
    with Database() as cursor:
        cursor.execute("""
            SELECT name, headshot_url, total_transcripts, total_segments 
            FROM speakers 
            ORDER BY total_segments DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_all_event_types() -> List[str]:
    """Get all unique event types."""
    
    with Database() as cursor:
        cursor.execute("SELECT DISTINCT event_type FROM transcripts WHERE event_type IS NOT NULL ORDER BY event_type")
        return [row[0] for row in cursor.fetchall()]


def get_mention_analytics(query: str) -> Dict:
    """Get analytics for a search term."""
    
    with Database() as cursor:
        # Total mentions
        cursor.execute("""
            SELECT COUNT(*) FROM segments_fts WHERE segments_fts MATCH ?
        """, (query,))
        total = cursor.fetchone()[0]
        
        # By speaker
        cursor.execute("""
            SELECT s.speaker_name, COUNT(*) as count
            FROM segments_fts 
            JOIN segments s ON segments_fts.rowid = s.id
            WHERE segments_fts MATCH ?
            GROUP BY s.speaker_name
            ORDER BY count DESC
        """, (query,))
        by_speaker = {row[0]: row[1] for row in cursor.fetchall()}
        
        # By event type
        cursor.execute("""
            SELECT t.event_type, COUNT(*) as count
            FROM segments_fts 
            JOIN segments s ON segments_fts.rowid = s.id
            JOIN transcripts t ON s.transcript_id = t.id
            WHERE segments_fts MATCH ?
            GROUP BY t.event_type
            ORDER BY count DESC
        """, (query,))
        by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        # By month
        cursor.execute("""
            SELECT strftime('%Y-%m', t.event_date) as month, COUNT(*) as count
            FROM segments_fts 
            JOIN segments s ON segments_fts.rowid = s.id
            JOIN transcripts t ON s.transcript_id = t.id
            WHERE segments_fts MATCH ?
            GROUP BY month
            ORDER BY month
        """, (query,))
        by_month = {row[0]: row[1] for row in cursor.fetchall()}
        
        return {
            'total_mentions': total,
            'by_speaker': by_speaker,
            'by_event_type': by_type,
            'by_month': by_month
        }


def add_to_scrape_queue(urls: List[str], priority: int = 0):
    """Add URLs to the scrape queue."""
    
    with Database() as cursor:
        for url in urls:
            cursor.execute("""
                INSERT OR IGNORE INTO scrape_queue (url, priority)
                VALUES (?, ?)
            """, (url, priority))


def get_pending_urls(limit: int = 10) -> List[str]:
    """Get pending URLs from the scrape queue."""
    
    with Database() as cursor:
        cursor.execute("""
            SELECT url FROM scrape_queue 
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
        """, (limit,))
        return [row[0] for row in cursor.fetchall()]


def update_scrape_status(url: str, status: str, error: str = None):
    """Update the status of a URL in the scrape queue."""
    
    with Database() as cursor:
        cursor.execute("""
            UPDATE scrape_queue 
            SET status = ?, last_attempt = CURRENT_TIMESTAMP, 
                attempts = attempts + 1, error_message = ?
            WHERE url = ?
        """, (status, error, url))


def get_database_stats() -> Dict:
    """Get statistics about the database."""
    
    with Database() as cursor:
        stats = {}
        
        cursor.execute("SELECT COUNT(*) FROM transcripts")
        stats['total_transcripts'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM segments")
        stats['total_segments'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM speakers")
        stats['total_speakers'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(total_words) FROM transcripts")
        stats['total_words'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT MIN(event_date), MAX(event_date) FROM transcripts")
        row = cursor.fetchone()
        stats['date_range'] = {'start': row[0], 'end': row[1]}
        
        cursor.execute("SELECT COUNT(*) FROM scrape_queue WHERE status = 'pending'")
        stats['pending_scrapes'] = cursor.fetchone()[0]
        
        return stats


if __name__ == "__main__":
    init_database()
    print("Database initialized successfully!")
    print(f"Location: {DATABASE_PATH}")
