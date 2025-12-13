-- Transcripts table to store all speech data
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
);

-- Word frequency table for pre-computed analysis
CREATE TABLE IF NOT EXISTS word_frequencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER NOT NULL,
    word TEXT NOT NULL,
    frequency INTEGER NOT NULL,
    FOREIGN KEY (transcript_id) REFERENCES transcripts(id) ON DELETE CASCADE
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_transcripts_date ON transcripts(date);
CREATE INDEX IF NOT EXISTS idx_transcripts_speech_type ON transcripts(speech_type);
CREATE INDEX IF NOT EXISTS idx_transcripts_date_type ON transcripts(date, speech_type);
CREATE INDEX IF NOT EXISTS idx_word_frequencies_transcript ON word_frequencies(transcript_id);
CREATE INDEX IF NOT EXISTS idx_word_frequencies_word ON word_frequencies(word);

-- Metadata table for tracking scraping progress
CREATE TABLE IF NOT EXISTS scrape_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_scrape_date TIMESTAMP,
    total_transcripts_scraped INTEGER DEFAULT 0,
    status TEXT,
    notes TEXT
);
