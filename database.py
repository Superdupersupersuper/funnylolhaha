import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Tuple

class Database:
    def __init__(self, db_path='./data/transcripts.db'):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = None
        self.cursor = None

    def connect(self):
        """Connect to the database"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        print(f"Connected to database: {self.db_path}")

    def initialize(self):
        """Create database tables"""
        self.connect()

        # Create transcripts table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                date DATE NOT NULL,
                speech_type TEXT NOT NULL,
                location TEXT,
                url TEXT UNIQUE NOT NULL,
                full_text TEXT NOT NULL,
                word_count INTEGER,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create word frequencies table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS word_frequencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                frequency INTEGER NOT NULL,
                FOREIGN KEY (transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE
            )
        ''')

        # Create indexes
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_transcripts_date ON transcripts(date)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_transcripts_speech_type ON transcripts(speech_type)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_transcripts_date_type ON transcripts(date, speech_type)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_word_frequencies_transcript ON word_frequencies(transcript_id)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_word_frequencies_word ON word_frequencies(word)')

        # Create metadata table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS scrape_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_scrape_date TIMESTAMP,
                total_transcripts_scraped INTEGER DEFAULT 0,
                status TEXT,
                notes TEXT
            )
        ''')

        self.conn.commit()
        print("Database schema initialized successfully")

    def insert_transcript(self, title: str, date: str, speech_type: str, location: str,
                         url: str, full_text: str, word_count: int) -> int:
        """Insert a transcript and return its ID"""
        try:
            self.cursor.execute('''
                INSERT INTO transcripts (title, date, speech_type, location, url, full_text, word_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (title, date, speech_type, location, url, full_text, word_count))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            # URL already exists
            return None

    def insert_word_frequencies(self, transcript_id: int, word_freqs: Dict[str, int]):
        """Insert word frequencies for a transcript"""
        data = [(transcript_id, word, freq) for word, freq in word_freqs.items()]
        self.cursor.executemany('''
            INSERT INTO word_frequencies (transcript_id, word, frequency)
            VALUES (?, ?, ?)
        ''', data)
        self.conn.commit()

    def url_exists(self, url: str) -> bool:
        """Check if a URL already exists in the database"""
        self.cursor.execute('SELECT id FROM transcripts WHERE url = ?', (url,))
        return self.cursor.fetchone() is not None

    def get_stats(self) -> Dict:
        """Get database statistics"""
        self.cursor.execute('SELECT COUNT(*) FROM transcripts')
        total = self.cursor.fetchone()[0]

        self.cursor.execute('SELECT MIN(date), MAX(date) FROM transcripts')
        date_range = self.cursor.fetchone()

        return {
            'total_transcripts': total,
            'date_range': date_range
        }

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("Database connection closed")
