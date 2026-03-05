#!/usr/bin/env python3
"""
Python API server for the Mention Market Tool
Provides endpoints for querying data and triggering scraper updates.

Storage back-end is selected via the TRANSCRIPT_STORE env var:
  - "github"  → persists transcripts in a private GitHub repo (recommended for Render)
  - "sqlite"  → local SQLite file (default, for local dev)
"""
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import sqlite3
import json
import time
import threading
import os
import logging
import sys
import re

# Import backup utilities (only used in sqlite mode)
try:
    import backup_database
    HAS_BACKUP = True
except ImportError:
    HAS_BACKUP = False
    logging.warning("backup_database module not available - backups will be skipped")

try:
    import export_backup
    HAS_EXPORT = True
except ImportError:
    HAS_EXPORT = False
    logging.warning("export_backup module not available - JSON exports will be skipped")

# Import GitHub-backed store
try:
    from github_store import get_github_store
    HAS_GITHUB_STORE = True
except ImportError:
    HAS_GITHUB_STORE = False
    logging.warning("github_store module not available")

# Version info for deployment tracking
API_VERSION = "3.0.0"
DEPLOY_TIMESTAMP = "2026-02-16T00:00:00Z"

# ---------------------------------------------------------------------------
# Store selection  (set TRANSCRIPT_STORE=github on Render)
# ---------------------------------------------------------------------------
TRANSCRIPT_STORE = os.environ.get("TRANSCRIPT_STORE", "sqlite")  # "github" | "sqlite"

# Try to import flask_compress, but don't fail if not available
try:
    from flask_compress import Compress
    HAS_COMPRESS = True
except ImportError:
    HAS_COMPRESS = False
    logging.warning("flask-compress not available - responses will not be compressed")

# Configure logging to stdout for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Import our incremental sync module
try:
    from rollcall_sync import run_incremental_sync, SyncSummary
    HAS_SYNC = True
except ImportError:
    HAS_SYNC = False
    logging.warning("rollcall_sync module not available")

app = Flask(__name__)
CORS(app)  # Allow frontend to connect

# Add compression to reduce response size (gzip)
if HAS_COMPRESS:
    try:
        compress = Compress()
        compress.init_app(app)
        logging.info("✅ Flask compression enabled")
    except Exception as e:
        logging.warning(f"⚠️  Could not enable compression: {e}")

# Use absolute path to prevent working-directory issues
# Allow override via environment variable
_script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv('MENTION_MARKETS_DB_PATH', os.path.join(_script_dir, 'data', 'transcripts.db'))

# Enhanced scraper status with detailed counts
scraper_status = {
    'running': False, 
    'progress': '', 
    'last_run': None,
    'processed': 0,
    'total': 0,
    'added': 0,
    'updated': 0,
    'failed': 0,
    'discovered': 0
}

# ---------------------------------------------------------------------------
# In-memory transcript cache  (used when TRANSCRIPT_STORE == "github")
# ---------------------------------------------------------------------------
_cache = {
    'index': [],        # list of metadata dicts (no full_dialogue)
    'full': {},         # id (int) -> full transcript dict
    'loaded_at': 0,     # time.time() when cache was last populated
    'ttl': 300,         # seconds before we consider the cache stale
}
_cache_lock = threading.Lock()


def _use_github():
    """Return True when the GitHub-backed store should be used."""
    return TRANSCRIPT_STORE == "github" and HAS_GITHUB_STORE and get_github_store().enabled


def _warm_cache():
    """Load index + all transcripts from GitHub into the in-memory cache."""
    store = get_github_store()
    index, _sha = store.load_index()
    full_map = {}
    for meta in index:
        tid = meta.get("id")
        full = store.get_transcript(tid)
        if full:
            full_map[tid] = full
        else:
            full_map[tid] = meta  # fallback to metadata only
    with _cache_lock:
        _cache['index'] = index
        _cache['full'] = full_map
        _cache['loaded_at'] = time.time()
    logging.info(f"🔄 GitHub cache warmed: {len(index)} transcripts")


def _ensure_cache():
    """Make sure the cache is populated and not stale."""
    with _cache_lock:
        age = time.time() - _cache['loaded_at']
        stale = age > _cache['ttl'] or not _cache['index'] and _cache['loaded_at'] == 0
    if stale:
        _warm_cache()


def _get_cached_index():
    """Return the cached index list."""
    _ensure_cache()
    with _cache_lock:
        return list(_cache['index'])


def _get_cached_transcript(tid: int):
    """Return a full transcript dict from cache (or None)."""
    _ensure_cache()
    with _cache_lock:
        return _cache['full'].get(tid)


def _get_all_cached_transcripts():
    """Return all full transcript dicts from cache, sorted by date desc."""
    _ensure_cache()
    with _cache_lock:
        items = list(_cache['full'].values())
    items.sort(key=lambda t: t.get('date', ''), reverse=True)
    return items


def _invalidate_cache():
    """Force the next read to reload from GitHub."""
    with _cache_lock:
        _cache['loaded_at'] = 0


def _update_cache_after_write(tid: int, payload: dict):
    """Update the local cache immediately after a create/update."""
    meta = {k: v for k, v in payload.items() if k != 'full_dialogue'}
    with _cache_lock:
        # Update full map
        _cache['full'][tid] = payload
        # Update index (replace or append)
        _cache['index'] = [m for m in _cache['index'] if m.get('id') != tid]
        _cache['index'].append(meta)
        _cache['index'].sort(key=lambda m: m.get('date', ''), reverse=True)
        _cache['loaded_at'] = time.time()


def _remove_from_cache(tid: int):
    """Remove a transcript from the local cache after deletion."""
    with _cache_lock:
        _cache['full'].pop(tid, None)
        _cache['index'] = [m for m in _cache['index'] if m.get('id') != tid]
        _cache['loaded_at'] = time.time()


# ---------------------------------------------------------------------------
# Helper: build a standard transcript response dict from a stored payload
# ---------------------------------------------------------------------------

def _build_transcript_response(t, include_full_text=True):
    """
    Convert a stored transcript dict into the shape the frontend expects.
    Works identically for both GitHub and SQLite payloads.
    """
    title = clean_title(t.get('title', ''))
    speakers_raw = t.get('speakers', [])
    if isinstance(speakers_raw, str):
        try:
            speakers_raw = json.loads(speakers_raw)
        except Exception:
            speakers_raw = []
    speakers = normalize_speakers(speakers_raw) if speakers_raw else []

    full_dialogue = t.get('full_dialogue', '') or ''

    # Get Q&A analytics if available
    qa_analytics = t.get('qa_analytics')
    if isinstance(qa_analytics, str):
        try: qa_analytics = json.loads(qa_analytics)
        except: qa_analytics = None
    
    # Get topics if available
    topics = t.get('topics', [])
    if isinstance(topics, str):
        try: topics = json.loads(topics)
        except: topics = []
    
    result = {
        'id': t.get('id'),
        'title': title,
        'date': t.get('date', ''),
        'speech_type': t.get('speech_type', ''),
        'location': t.get('location', ''),
        'url': t.get('url', ''),
        'word_count': t.get('word_count', 0) or 0,
        'speakers': speakers,
        'primary_speaker': t.get('primary_speaker', ''),
        'has_q_and_a': t.get('has_q_and_a', False),
        'qa_analytics': qa_analytics,
        'topics': topics
    }

    if include_full_text:
        result['preview'] = full_dialogue
        result['full_dialogue'] = full_dialogue
        result['dialogue'] = parse_dialogue_to_segments(full_dialogue)
    else:
        result['preview'] = ''

    return result


def init_database_if_needed():
    """Initialize database schema if it doesn't exist"""
    db_existed = os.path.exists(DB_PATH)
    
    if not db_existed:
        # Create directory if needed
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        logging.info(f"📦 Initializing new database at: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create transcripts table with schema matching rollcall_sync.py
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                date DATE NOT NULL,
                speech_type TEXT NOT NULL,
                location TEXT,
                url TEXT UNIQUE NOT NULL,
                word_count INTEGER,
                trump_word_count INTEGER,
                speech_duration_seconds INTEGER,
                full_dialogue TEXT,
                speakers_json TEXT,
                primary_speaker TEXT DEFAULT '',
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create speech_types table for custom speech types
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS speech_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                speech_type TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON transcripts(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON transcripts(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_primary_speaker ON transcripts(primary_speaker)")
        
        conn.commit()
        conn.close()
        logging.info("✅ Database initialized successfully")
        
        # Auto-restore from latest backup if available
        _auto_restore_from_backup()
    else:
        # Migrate: add primary_speaker column if missing
        _migrate_add_primary_speaker()
        
        # Migrate: add speech_types table if missing
        _migrate_add_speech_types_table()
        
        # Migrate: add Q&A columns if missing
        _migrate_add_qa_columns()
        
        # Migrate: add topics column and table if missing
        _migrate_add_topics_column()
        
        # Check if database is empty and restore if needed
        _check_and_restore_if_empty()


def _migrate_add_primary_speaker():
    """Add primary_speaker column to existing databases that lack it."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(transcripts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'primary_speaker' not in columns:
            logging.info("📦 Migrating: adding primary_speaker column...")
            cursor.execute("ALTER TABLE transcripts ADD COLUMN primary_speaker TEXT DEFAULT ''")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_primary_speaker ON transcripts(primary_speaker)")
            conn.commit()
            logging.info("✅ primary_speaker column added")
        
        conn.close()
    except Exception as e:
        logging.error(f"Migration error: {e}")

def _migrate_add_speech_types_table():
    """Add speech_types table to existing databases that lack it."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if speech_types table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='speech_types'")
        if not cursor.fetchone():
            logging.info("📦 Migrating: adding speech_types table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS speech_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    speech_type TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            logging.info("✅ speech_types table added")
        
        conn.close()
    except Exception as e:
        logging.error(f"Migration error: {e}")

def _migrate_add_qa_columns():
    """Add has_q_and_a, qa_analytics, qa_data_auto, and qa_overrides columns to transcripts table
       and create the qa_labels table for AI training."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(transcripts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'has_q_and_a' not in columns:
            logging.info("📦 Migrating: adding has_q_and_a column...")
            cursor.execute("ALTER TABLE transcripts ADD COLUMN has_q_and_a INTEGER DEFAULT 0")
            conn.commit()
            logging.info("✅ has_q_and_a column added")
        
        if 'qa_analytics' not in columns:
            logging.info("📦 Migrating: adding qa_analytics column...")
            cursor.execute("ALTER TABLE transcripts ADD COLUMN qa_analytics TEXT")
            conn.commit()
            logging.info("✅ qa_analytics column added")

        if 'qa_data_auto' not in columns:
            logging.info("📦 Migrating: adding qa_data_auto column...")
            cursor.execute("ALTER TABLE transcripts ADD COLUMN qa_data_auto TEXT")
            conn.commit()
            logging.info("✅ qa_data_auto column added")

        if 'qa_overrides' not in columns:
            logging.info("📦 Migrating: adding qa_overrides column...")
            cursor.execute("ALTER TABLE transcripts ADD COLUMN qa_overrides TEXT")
            conn.commit()
            logging.info("✅ qa_overrides column added")

        # Create qa_labels table for AI training data
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='qa_labels'")
        if not cursor.fetchone():
            logging.info("📦 Creating qa_labels table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS qa_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transcript_id INTEGER NOT NULL,
                    question_speaker TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    response_speaker TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    is_qa INTEGER NOT NULL,
                    reasoning TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_qa_labels_transcript ON qa_labels(transcript_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_qa_labels_is_qa ON qa_labels(is_qa)")
            conn.commit()
            logging.info("✅ qa_labels table created")
        
        conn.close()
    except Exception as e:
        logging.error(f"Migration error: {e}")

def _migrate_add_topics_column():
    """Add topics column to transcripts table and create topics table"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Add topics column to transcripts
        cursor.execute("PRAGMA table_info(transcripts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'topics' not in columns:
            logging.info("📦 Migrating: adding topics column...")
            cursor.execute("ALTER TABLE transcripts ADD COLUMN topics TEXT")
            conn.commit()
            logging.info("✅ topics column added")
        
        # Create topics table for managing all unique topics
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='topics'")
        if not cursor.fetchone():
            logging.info("📦 Creating topics table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            logging.info("✅ topics table created")
        
        conn.close()
    except Exception as e:
        logging.error(f"Migration error: {e}")

def _auto_restore_from_backup():
    """Auto-restore transcripts from latest JSON backup if available"""
    if not HAS_EXPORT:
        logging.info("ℹ️ Export module not available - skipping auto-restore")
        return
    
    try:
        latest_backup = 'data/json_backups/transcripts_latest.json'
        if os.path.exists(latest_backup):
            logging.info(f"📦 Found backup file: {latest_backup}")
            logging.info("🔄 Auto-restoring transcripts from backup...")
            
            try:
                if export_backup.import_from_backup(latest_backup):
                    logging.info("✅ Transcripts restored from backup")
                else:
                    logging.warning("⚠️ Failed to restore from backup")
            except Exception as restore_error:
                logging.error(f"⚠️ Restore failed but continuing: {restore_error}")
        else:
            logging.info("ℹ️ No backup file found - starting with empty database")
    except Exception as e:
        logging.error(f"⚠️ Auto-restore error (continuing anyway): {e}")

def _check_and_restore_if_empty():
    """Check if database is empty and restore from backup if needed"""
    if not HAS_EXPORT:
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transcripts")
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            logging.info("⚠️ Database is empty - attempting to restore from backup...")
            _auto_restore_from_backup()
    except Exception as e:
        logging.error(f"Check and restore error: {e}")


def parse_dialogue_to_segments(full_dialogue_text):
    """Parse full_dialogue text into structured dialogue segments for the frontend"""
    if not full_dialogue_text:
        return []
    
    import re
    segments = []
    # Split by double newline to get individual segments
    blocks = full_dialogue_text.strip().split('\n\n')
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        # Try format 1: "Speaker Name\ntimestamp text"
        # e.g., "Donald Trump 00\n00:00-00:00:02 (2 sec) NO STRESSLENS Good morning."
        lines = block.split('\n', 1)
        if len(lines) == 2:
            speaker_line = lines[0].strip()
            content_line = lines[1].strip()
            
            # Extract speaker (remove trailing numbers like "00")
            speaker_match = re.match(r'^(.+?)\s+\d+$', speaker_line)
            speaker = speaker_match.group(1).strip() if speaker_match else speaker_line
            
            # Extract timestamp and text
            # Format: "00:00-00:00:02 (2 sec) NO STRESSLENS Good morning."
            timestamp_match = re.match(r'^([\d:]+(?:-[\d:]+)?)\s*(?:\([^)]*\))?\s*(?:NO STRESSLENS)?\s*(.+)$', content_line, re.DOTALL)
            if timestamp_match:
                timestamp = timestamp_match.group(1).strip()
                text = timestamp_match.group(2).strip()
                
                segments.append({
                    'speaker': speaker,
                    'timestamp': timestamp,
                    'text': text
                })
                continue
        
        # Try format 2: "Speaker Name (timestamp): text" (single line)
        match = re.match(r'^(.+?)\s*\(([0-9:]+)\):\s*(.+)$', block, re.DOTALL)
        if match:
            speaker = match.group(1).strip()
            timestamp = match.group(2).strip()
            text = match.group(3).strip()
            
            segments.append({
                'speaker': speaker,
                'timestamp': timestamp,
                'text': text
            })
    
    return segments

def normalize_speakers(speakers):
    """Normalize speaker names: collapse 'Speaker 1', 'Speaker 2', etc. into 'Unknown Speaker'."""
    normalized = []
    seen = set()
    for s in speakers:
        if re.match(r'^Speaker\s+\d+$', s, re.IGNORECASE):
            label = 'Unknown Speaker'
        else:
            label = s
        if label not in seen:
            normalized.append(label)
            seen.add(label)
    return normalized


def clean_title(title):
    """Remove 'otter ai' / 'otter.ai' / 'Transcribed by...' artifacts from titles."""
    if not title:
        return title
    title = re.sub(r'\s*[-–—]\s*Transcribed by\s+(?:https?://)?otter\.?ai\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*Transcribed by\s+(?:https?://)?otter\.?ai\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*otter\.?ai\s*$', '', title, flags=re.IGNORECASE)
    return title.strip()

def auto_export_backup():
    """Automatically export transcripts to JSON after any database change"""
    if not HAS_EXPORT:
        return
    
    try:
        # Run in background thread to not block the response
        import threading
        def _export():
            try:
                export_backup.export_all_transcripts()
                logging.info("✅ Auto-exported transcripts to JSON backup")
            except Exception as e:
                logging.error(f"❌ Auto-export failed: {e}")
        
        thread = threading.Thread(target=_export, daemon=True)
        thread.start()
    except Exception as e:
        logging.error(f"❌ Failed to start export thread: {e}")

def get_db():
    """Get database connection"""
    # Initialize database if it doesn't exist
    init_database_if_needed()
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

def run_scraper_async():
    """Run incremental sync in background"""
    global scraper_status
    
    if not HAS_SYNC:
        scraper_status['running'] = False
        scraper_status['progress'] = 'Error: Sync module not available'
        scraper_status['last_run'] = {'success': False, 'error': 'rollcall_sync module not found'}
        return
    
    scraper_status['running'] = True
    scraper_status['progress'] = 'Starting incremental sync...'
    scraper_status['processed'] = 0
    scraper_status['total'] = 0
    scraper_status['added'] = 0
    scraper_status['updated'] = 0
    scraper_status['failed'] = 0
    scraper_status['discovered'] = 0
    
    def progress_callback(message, counts):
        """Update scraper_status with progress"""
        global scraper_status
        scraper_status['progress'] = message
        # Update counts from callback
        if 'processed' in counts:
            scraper_status['processed'] = counts['processed']
        if 'total' in counts:
            scraper_status['total'] = counts['total']
        if 'added' in counts:
            scraper_status['added'] = counts['added']
        if 'updated' in counts:
            scraper_status['updated'] = counts['updated']
        if 'failed' in counts:
            scraper_status['failed'] = counts['failed']
        if 'discovered' in counts:
            scraper_status['discovered'] = counts['discovered']

    try:
        # Run incremental sync
        summary = run_incremental_sync(DB_PATH, progress_callback)
        
        # Update final status
        if summary.error:
            scraper_status['progress'] = f'Error: {summary.error}'
            scraper_status['last_run'] = {
                'success': False, 
                'error': summary.error,
                'date_range': f"{summary.start_date} to {summary.end_date}"
            }
        else:
            scraper_status['progress'] = f'Complete! Added: {summary.added}, Updated: {summary.updated}, Failed: {summary.failed}'
            scraper_status['added'] = summary.added
            scraper_status['updated'] = summary.updated
            scraper_status['failed'] = summary.failed
            scraper_status['last_run'] = {
                'success': True,
                'added': summary.added,
                'updated': summary.updated,
                'failed': summary.failed,
                'discovered': summary.total_discovered,
                'date_range': f"{summary.start_date} to {summary.end_date}"
            }
    
    except Exception as e:
        logging.error(f"Sync error: {e}", exc_info=True)
        scraper_status['progress'] = f'Error: {str(e)}'
        scraper_status['last_run'] = {'success': False, 'error': str(e)}
    
    finally:
        scraper_status['running'] = False

@app.route('/', methods=['GET'])
@app.route('/analytics_ui.html', methods=['GET'])
@app.route('/index.html', methods=['GET'])
def serve_frontend():
    """Serve the analytics UI"""
    try:
        # Serve analytics_ui.html from the same directory as this script
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analytics_ui.html')
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    except FileNotFoundError:
        return jsonify({
            'error': 'Frontend not found',
            'message': 'analytics_ui.html is missing. This is the API server.',
            'api_endpoints': ['/api/health', '/api/stats', '/api/transcripts']
        }), 404

@app.route('/analytics_ui_test.html', methods=['GET'])
@app.route('/test', methods=['GET'])
def serve_test_frontend():
    """Serve the test / preview UI (analytics_ui_test.html)"""
    try:
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analytics_ui_test.html')
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    except FileNotFoundError:
        return jsonify({
            'error': 'Test UI not found',
            'message': 'analytics_ui_test.html is missing. Run the test build first.'
        }), 404

@app.route('/admin', methods=['GET'])
def serve_admin():
    """Serve the admin UI"""
    try:
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin.html')
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    except FileNotFoundError:
        return jsonify({'error': 'Admin UI not found'}), 404

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint with store info"""
    health_data = {
        'status': 'healthy',
        'version': API_VERSION,
        'deploy_timestamp': DEPLOY_TIMESTAMP,
        'store': TRANSCRIPT_STORE,
        'transcripts': {
            'count': 0,
            'error': None
        }
    }

    if _use_github():
        try:
            index = _get_cached_index()
            health_data['transcripts']['count'] = len(index)
            if not index:
                health_data['status'] = 'warning'
                health_data['message'] = 'GitHub store is empty.'
        except Exception as e:
            health_data['status'] = 'error'
            health_data['transcripts']['error'] = str(e)
    else:
        db_exists = os.path.exists(DB_PATH)
        health_data['database'] = {
            'path': DB_PATH,
            'exists': db_exists,
            'size_mb': round(os.path.getsize(DB_PATH) / (1024 * 1024), 2) if db_exists else 0
        }
        if db_exists:
            try:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as count FROM transcripts")
                count = cursor.fetchone()['count']
                health_data['transcripts']['count'] = count
                conn.close()
                if count == 0:
                    health_data['status'] = 'warning'
                    health_data['message'] = 'Database is empty.'
            except Exception as e:
                health_data['status'] = 'error'
                health_data['transcripts']['error'] = str(e)
        else:
            health_data['status'] = 'warning'
            health_data['message'] = f'Database file not found at {DB_PATH}'

    return jsonify(health_data)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get database statistics"""
    if _use_github():
        index = _get_cached_index()
        total = len(index)
        total_words = sum(m.get('word_count', 0) or 0 for m in index)
        dates = [m['date'] for m in index if re.match(r'^\d{4}-\d{2}-\d{2}$', m.get('date', ''))]
        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None
        # Speech types
        st_counts = {}
        yr_counts = {}
        for m in index:
            st = m.get('speech_type', '')
            st_counts[st] = st_counts.get(st, 0) + 1
            d = m.get('date', '')
            if len(d) >= 4:
                yr = d[:4]
                yr_counts[yr] = yr_counts.get(yr, 0) + 1
        speech_types = [{'speech_type': k, 'count': v} for k, v in sorted(st_counts.items(), key=lambda x: -x[1])]
        years = [{'year': k, 'count': v} for k, v in sorted(yr_counts.items())]

        return jsonify({
            'totalTranscripts': total,
            'totalWords': total_words,
            'dateRange': {'minDate': min_date, 'maxDate': max_date},
            'speechTypes': speech_types,
            'yearDistribution': years
        })

    # --- SQLite path ---
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM transcripts")
    total = cursor.fetchone()['count']

    cursor.execute("SELECT SUM(word_count) as total FROM transcripts")
    total_words = cursor.fetchone()['total'] or 0

    cursor.execute("""
        SELECT
            MIN(CASE WHEN date LIKE '____-__-__' THEN date END) as min_date,
            MAX(CASE WHEN date LIKE '____-__-__' THEN date END) as max_date
        FROM transcripts
    """)
    date_range = cursor.fetchone()

    cursor.execute("""
        SELECT speech_type, COUNT(*) as count
        FROM transcripts GROUP BY speech_type ORDER BY count DESC
    """)
    speech_types = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT SUBSTR(date, 1, 4) as year, COUNT(*) as count
        FROM transcripts WHERE date LIKE '____-__-__'
        GROUP BY SUBSTR(date, 1, 4) ORDER BY year
    """)
    years = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        'totalTranscripts': total,
        'totalWords': total_words,
        'dateRange': {'minDate': date_range['min_date'], 'maxDate': date_range['max_date']},
        'speechTypes': speech_types,
        'yearDistribution': years
    })

@app.route('/api/transcripts/metadata', methods=['GET'])
def get_transcripts_metadata():
    """Get transcript metadata WITHOUT full text - lightweight endpoint"""
    try:
        if _use_github():
            all_t = _get_all_cached_transcripts()
            transcripts = [_build_transcript_response(t, include_full_text=False) for t in all_t]
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, date, speech_type, location, url,
                       word_count, speakers_json, primary_speaker
                FROM transcripts ORDER BY date DESC
            """)
            rows = cursor.fetchall()
            conn.close()

            transcripts = []
            for row in rows:
                speakers_raw = json.loads(row['speakers_json']) if row['speakers_json'] else []
                transcripts.append({
                    'id': row['id'],
                    'title': clean_title(row['title']),
                    'date': row['date'],
                    'speech_type': row['speech_type'],
                    'location': row['location'] or '',
                    'url': row['url'],
                    'word_count': row['word_count'] or 0,
                    'preview': '',
                    'speakers': normalize_speakers(speakers_raw),
                    'primary_speaker': row['primary_speaker'] or ''
                })

        logging.info(f"📤 Returning {len(transcripts)} metadata entries")
        response = jsonify(transcripts)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        logging.error(f"❌ Error in get_transcripts_metadata: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'transcripts': []}), 500

@app.route('/api/transcripts', methods=['GET'])
def get_transcripts():
    """Get ALL transcripts with FULL dialogue text"""
    try:
        if _use_github():
            all_t = _get_all_cached_transcripts()
            transcripts = [_build_transcript_response(t, include_full_text=True) for t in all_t]
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(transcripts)")
            columns = [col[1] for col in cursor.fetchall()]
            text_column = 'full_dialogue' if 'full_dialogue' in columns else 'full_text'

            cursor.execute(f"""
                SELECT id, title, date, speech_type, location, url, word_count,
                       {text_column} as preview, speakers_json, primary_speaker
                FROM transcripts ORDER BY date DESC
            """)
            rows = cursor.fetchall()
            conn.close()

            transcripts = []
            for row in rows:
                preview_text = row['preview'] or ''
                if isinstance(preview_text, bytes):
                    preview_text = preview_text.decode('utf-8', errors='ignore')
                dialogue_segments = parse_dialogue_to_segments(preview_text)
                speakers_raw = json.loads(row['speakers_json']) if row['speakers_json'] else []
                transcripts.append({
                    'id': row['id'],
                    'title': clean_title(row['title']),
                    'date': row['date'],
                    'speech_type': row['speech_type'],
                    'location': row['location'] or '',
                    'url': row['url'],
                    'word_count': row['word_count'] or 0,
                    'preview': preview_text,
                    'dialogue': dialogue_segments,
                    'speakers': normalize_speakers(speakers_raw),
                    'primary_speaker': row['primary_speaker'] or ''
                })

        logging.info(f"📤 Returning {len(transcripts)} transcripts")
        response = jsonify(transcripts)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        logging.error(f"❌ Error in get_transcripts: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'transcripts': []}), 500

@app.route('/api/transcripts/<int:id>', methods=['GET'])
def get_transcript(id):
    """Get single transcript"""
    if _use_github():
        t = _get_cached_transcript(id)
        if t:
            return jsonify(_build_transcript_response(t, include_full_text=True))
        return jsonify({'error': 'Not found'}), 404

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transcripts WHERE id = ?", (id,))
    transcript = cursor.fetchone()
    conn.close()

    if transcript:
        return jsonify(dict(transcript))
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/analysis/word-frequency', methods=['GET'])
def word_frequency():
    """Get word frequency analysis"""
    start_date = request.args.get('startDate', '')
    end_date = request.args.get('endDate', '')
    speech_type = request.args.get('speechType', '')
    top_n = int(request.args.get('topN', 50))
    exclude_common = request.args.get('excludeCommon', 'true') == 'true'

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT full_text FROM transcripts WHERE 1=1"
    params = []

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    if speech_type and speech_type != 'all':
        query += " AND speech_type = ?"
        params.append(speech_type)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return jsonify({'words': [], 'totalWords': 0, 'transcriptCount': 0})

    # Combine all text
    combined_text = ' '.join([row['full_text'] for row in rows])

    # Analyze
    frequencies = analyze_word_frequency(combined_text, exclude_common=exclude_common, max_words=top_n)
    words = [{'word': word, 'frequency': freq} for word, freq in frequencies.items()]

    return jsonify({
        'words': words,
        'totalWords': count_words(combined_text),
        'transcriptCount': len(rows)
    })

@app.route('/api/database/clean-december', methods=['POST'])
def clean_december_transcripts_api():
    """Clean December 2025 transcripts - remove metadata artifacts"""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from clean_december_transcripts import clean_december_transcripts as run_cleanup
        
        logging.info("🧹 Starting December 2025 transcript cleanup...")
        
        # Run cleanup on production database
        run_cleanup(DB_PATH, dry_run=False)
        
        logging.info("✅ December cleanup complete")
        
        return jsonify({
            'status': 'success',
            'message': 'December 2025 transcripts cleaned successfully'
        })
    except Exception as e:
        logging.error(f"❌ Cleanup error: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/scraper/refresh', methods=['POST', 'GET'])
def refresh_scraper():
    """Trigger scraper to get new transcripts (accepts both POST and GET for testing)"""
    global scraper_status

    if scraper_status['running']:
        return jsonify({
            'status': 'already_running',
            'message': 'Scraper is already running',
            'progress': scraper_status['progress']
        })

    # Start scraper in background thread
    thread = threading.Thread(target=run_scraper_async)
    thread.daemon = True
    thread.start()

    return jsonify({
        'status': 'started',
        'message': 'Scraper started in background'
    })

@app.route('/api/scraper/status', methods=['GET'])
def scraper_status_endpoint():
    """Get scraper status"""
    # Include last error details if available
    status = scraper_status.copy()
    if 'last_run' in status and status['last_run'] and 'error' in status['last_run']:
        status['last_error'] = status['last_run']['error']
    return jsonify(status)

@app.route('/api/speech-types', methods=['GET'])
def get_speech_types():
    """Get speech types, optionally filtered by primary speaker"""
    speaker = request.args.get('speaker', None)
    
    # Helper: case-insensitive fuzzy name match (word-based, same logic as frontend speakerMatchesPrimary)
    def _speaker_name_matches(stored, query):
        if not stored or not query:
            return False
        import re as _re
        def norm(s):
            return _re.sub(r'\s+', ' ', _re.sub(r'[^a-z\s]', '', s.lower())).strip()
        a_words = norm(stored).split()
        b_words = norm(query).split()
        if not a_words or not b_words:
            return False
        return (all(w in a_words for w in b_words) or all(w in b_words for w in a_words))

    if _use_github():
        index = _get_cached_index()
        counts = {}
        for m in index:
            # Filter by speaker if specified (case-insensitive fuzzy match)
            if speaker and not _speaker_name_matches(m.get('primary_speaker', ''), speaker):
                continue
            st = m.get('speech_type', '')
            if st:  # Only count non-empty speech types
                counts[st] = counts.get(st, 0) + 1
        
        # Get custom speech types from the database (even in GitHub mode)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT speech_type FROM speech_types ORDER BY speech_type')
        custom_types = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        # Add default types
        default_types = ['Remarks', 'Press Conference', 'Interview', 'Rally', 'Press Briefing', 'Other']
        existing_types = list(counts.keys())
        
        # Combine default types + custom types + existing types, maintaining order
        all_types = default_types + custom_types + [t for t in existing_types if t not in default_types and t not in custom_types]
        
        if speaker:
            # Filter to only types used by this speaker
            return jsonify({'speech_types': [t for t in all_types if t in existing_types]})
        
        return jsonify({'speech_types': all_types})

    conn = get_db()
    cursor = conn.cursor()
    
    # Get custom speech types from the speech_types table
    cursor.execute('SELECT speech_type FROM speech_types ORDER BY speech_type')
    custom_types = [row[0] for row in cursor.fetchall()]
    
    # Add default types
    default_types = ['Remarks', 'Press Conference', 'Interview', 'Rally', 'Press Briefing', 'Other']
    all_types = default_types + custom_types
    
    if speaker:
        # Filter to only speech types used by this specific speaker (case-insensitive)
        cursor.execute("""
            SELECT DISTINCT speech_type
            FROM transcripts
            WHERE LOWER(primary_speaker) = LOWER(?)
            ORDER BY speech_type
        """, (speaker,))
        used_types_exact = [row[0] for row in cursor.fetchall() if row[0]]
        
        # Also do fuzzy word-based match to catch e.g. "Zohran Mamdani" vs "Mamdani"
        if not used_types_exact:
            cursor.execute("SELECT DISTINCT primary_speaker, speech_type FROM transcripts WHERE speech_type IS NOT NULL AND speech_type != ''")
            rows = cursor.fetchall()
            used_types_exact = list({row[1] for row in rows if row[1] and _speaker_name_matches(row[0] or '', speaker)})
        
        conn.close()
        
        # Return only types that this speaker has used
        return jsonify({'speech_types': [t for t in all_types if t in used_types_exact]})
    
    conn.close()
    return jsonify({'speech_types': all_types})

@app.route('/api/speech-types', methods=['POST'])
def add_speech_type():
    """Add a new custom speech type"""
    try:
        data = request.get_json()
        speech_type = data.get('speech_type', '').strip()
        
        if not speech_type:
            return jsonify({'error': 'Speech type is required'}), 400
        
        # Default types cannot be added again
        default_types = ['Remarks', 'Press Conference', 'Interview', 'Rally', 'Press Briefing', 'Other']
        if speech_type in default_types:
            return jsonify({'error': 'This is already a default speech type'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if it already exists in custom types table
        cursor.execute('SELECT COUNT(*) FROM speech_types WHERE speech_type = ?', (speech_type,))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return jsonify({'error': 'Speech type already exists'}), 400
        
        # Insert new custom speech type
        cursor.execute('INSERT INTO speech_types (speech_type) VALUES (?)', (speech_type,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'speech_type': speech_type}), 201
    except Exception as e:
        logging.error(f'Error adding speech type: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/speech-types/<path:speech_type>', methods=['DELETE'])
def delete_speech_type(speech_type):
    """Delete a custom speech type"""
    try:
        # Default types cannot be deleted
        default_types = ['Remarks', 'Press Conference', 'Interview', 'Rally', 'Press Briefing', 'Other']
        if speech_type in default_types:
            return jsonify({'error': 'Cannot delete default speech types'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Delete from custom types
        cursor.execute('DELETE FROM speech_types WHERE speech_type = ?', (speech_type,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True}), 200
    except Exception as e:
        logging.error(f'Error deleting speech type: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/date-range', methods=['GET'])
def get_date_range():
    """Get min/max dates"""
    if _use_github():
        index = _get_cached_index()
        dates = [m['date'] for m in index if re.match(r'^\d{4}-\d{2}-\d{2}$', m.get('date', ''))]
        return jsonify({'minDate': min(dates) if dates else None, 'maxDate': max(dates) if dates else None})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            MIN(CASE WHEN date LIKE '____-__-__' THEN date END) as minDate,
            MAX(CASE WHEN date LIKE '____-__-__' THEN date END) as maxDate
        FROM transcripts
    """)
    result = dict(cursor.fetchone())
    conn.close()
    return jsonify(result)

# ===== TOPICS MANAGEMENT =====

@app.route('/api/topics', methods=['GET'])
def get_topics():
    """Get all topics (from database and GitHub transcripts)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get topics from topics table
        cursor.execute('SELECT topic FROM topics ORDER BY topic')
        db_topics = set(row[0] for row in cursor.fetchall())
        conn.close()
        
        # Also get topics from actual transcripts if using GitHub
        transcript_topics = set()
        if _use_github():
            index = _get_cached_index()
            for m in index:
                topics = m.get('topics', [])
                if isinstance(topics, str):
                    try: topics = json.loads(topics)
                    except: topics = []
                if isinstance(topics, list):
                    transcript_topics.update(topics)
        
        # Combine and sort
        all_topics = sorted(list(db_topics | transcript_topics))
        return jsonify({'topics': all_topics})
    except Exception as e:
        logging.error(f'Error getting topics: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/topics', methods=['POST'])
def add_topic():
    """Add a new topic"""
    try:
        data = request.json
        topic = data.get('topic', '').strip()
        
        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Add to topics table (ignore if already exists)
        cursor.execute('INSERT OR IGNORE INTO topics (topic) VALUES (?)', (topic,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'topic': topic}), 200
    except Exception as e:
        logging.error(f'Error adding topic: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/topics/<path:topic>', methods=['DELETE'])
def delete_topic(topic):
    """Delete a topic"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM topics WHERE topic = ?', (topic,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True}), 200
    except Exception as e:
        logging.error(f'Error deleting topic: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/parse', methods=['POST'])
def parse_transcript():
    """Parse Otter.ai transcript and return structured data with Q&A detection"""
    try:
        data = request.json
        text = data.get('text', '')
        detect_qa = data.get('detectQA', False)
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Parse the transcript using the same logic as the Next.js parser
        result = parse_otter_transcript(text, detect_qa)
        return jsonify(result)
    except Exception as e:
        logging.error(f"Parse error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/transcripts', methods=['POST'])
def create_transcript():
    """Create a new transcript"""
    try:
        logging.info("=== CREATE TRANSCRIPT REQUEST START ===")
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON body'}), 400

        # Required fields
        title = data.get('title')
        event_date = data.get('event_date')
        speech_type = data.get('speech_type')
        primary_speaker = data.get('primary_speaker')
        segments = data.get('segments', [])

        if not all([title, event_date, speech_type, primary_speaker]):
            return jsonify({'error': 'Missing required fields'}), 400
        if not segments:
            return jsonify({'error': 'No segments provided'}), 400

        # Additional speakers (metadata-only co-speakers; merged into speaker list)
        additional_speakers = data.get('additional_speakers', [])
        if isinstance(additional_speakers, str):
            try: additional_speakers = json.loads(additional_speakers)
            except: additional_speakers = []

        # Build full dialogue
        full_dialogue = '\n\n'.join([
            f"{seg['speaker']} ({format_seconds(seg['start_seconds'])}): {seg['text']}"
            for seg in segments
        ])
        word_count = sum(len(seg['text'].split()) for seg in segments)
        # Merge segment-derived speakers with any additional speakers specified by admin
        seg_speakers = list(set(seg['speaker'] for seg in segments))
        speakers = seg_speakers + [s for s in additional_speakers if s and s not in seg_speakers]
        cleaned_title = clean_title(title)
        normalized_speakers = normalize_speakers(speakers)
        url_slug = f'admin-upload-{event_date}-{title[:30].replace(" ", "-")}'
        total_seconds = data.get('total_seconds', 0)

        # Q&A data
        has_qa = data.get('has_q_and_a', False)
        qa_analytics = data.get('qa_analytics')
        
        # Topics data
        topics = data.get('topics', [])
        if isinstance(topics, str):
            try: topics = json.loads(topics)
            except: topics = []

        if _use_github():
            # --- GitHub path ---
            store = get_github_store()
            payload = {
                'title': cleaned_title,
                'date': event_date,
                'speech_type': speech_type,
                'location': '',
                'url': url_slug,
                'word_count': word_count,
                'speech_duration_seconds': total_seconds,
                'full_dialogue': full_dialogue,
                'speakers': normalized_speakers,
                'primary_speaker': primary_speaker,
                'has_q_and_a': has_qa,
                'qa_analytics': qa_analytics,
                'topics': topics,
            }
            transcript_id = store.create_transcript(payload)
            payload['id'] = transcript_id
            _update_cache_after_write(transcript_id, payload)
            logging.info(f"✅ Created transcript {transcript_id} in GitHub store")

        else:
            # --- SQLite path ---
            speakers_json_str = json.dumps(normalized_speakers)
            qa_analytics_str = json.dumps(qa_analytics) if qa_analytics else None
            topics_str = json.dumps(topics) if topics else None
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transcripts (
                    title, date, speech_type, location, url, word_count,
                    trump_word_count, speech_duration_seconds, full_dialogue, speakers_json,
                    primary_speaker, has_q_and_a, qa_analytics, topics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cleaned_title, event_date, speech_type, '', url_slug, word_count,
                0, total_seconds, full_dialogue, speakers_json_str, primary_speaker,
                1 if has_qa else 0, qa_analytics_str, topics_str
            ))
            transcript_id = cursor.lastrowid
            conn.commit()
            conn.close()
            logging.info(f"✅ Created transcript {transcript_id} in SQLite")
            auto_export_backup()

        return jsonify({'id': transcript_id, 'success': True}), 201

    except Exception as e:
        logging.error(f"❌ create_transcript error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/transcripts/by-speaker', methods=['GET'])
def get_transcripts_by_speaker():
    """Get all transcripts for database viewer"""
    try:
        if _use_github():
            all_t = _get_all_cached_transcripts()
            transcripts = [_build_transcript_response(t, include_full_text=False) for t in all_t]
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, date, speech_type, word_count, speakers_json, primary_speaker
                FROM transcripts ORDER BY date DESC
            """)
            rows = cursor.fetchall()
            conn.close()
            transcripts = []
            for row in rows:
                speakers_raw = json.loads(row['speakers_json']) if row['speakers_json'] else []
                transcripts.append({
                    'id': row['id'],
                    'title': clean_title(row['title']),
                    'date': row['date'],
                    'speech_type': row['speech_type'],
                    'word_count': row['word_count'] or 0,
                    'speakers': normalize_speakers(speakers_raw),
                    'primary_speaker': row['primary_speaker'] or ''
                })

        return jsonify({'transcripts': transcripts})

    except Exception as e:
        logging.error(f"Get transcripts by-speaker error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'transcripts': []}), 500

@app.route('/api/admin/transcripts/<int:transcript_id>', methods=['GET'])
def get_transcript_for_edit(transcript_id):
    """Get a single transcript for editing"""
    try:
        if _use_github():
            t = _get_cached_transcript(transcript_id)
            if not t:
                return jsonify({'error': 'Transcript not found'}), 404
            full_text = t.get('full_dialogue', '') or ''
            speakers = t.get('speakers', [])
            if isinstance(speakers, str):
                try: speakers = json.loads(speakers)
                except: speakers = []
            
            # Get Q&A analytics if available
            qa_analytics = t.get('qa_analytics')
            if isinstance(qa_analytics, str):
                try: qa_analytics = json.loads(qa_analytics)
                except: qa_analytics = None
            
            # Get topics if available
            topics = t.get('topics', [])
            if isinstance(topics, str):
                try: topics = json.loads(topics)
                except: topics = []
            
            return jsonify({
                'id': t.get('id'),
                'title': t.get('title', ''),
                'date': t.get('date', ''),
                'speech_type': t.get('speech_type', ''),
                'location': t.get('location', ''),
                'url': t.get('url', ''),
                'word_count': t.get('word_count', 0) or 0,
                'speech_duration_seconds': t.get('speech_duration_seconds', 0) or 0,
                'full_dialogue': full_text,
                'full_text': full_text,
                'speakers': speakers,
                'primary_speaker': t.get('primary_speaker', ''),
                'has_q_and_a': t.get('has_q_and_a', False),
                'qa_analytics': qa_analytics,
                'topics': topics
            })

        # SQLite path
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, date, speech_type, location, url, word_count,
                   speech_duration_seconds, full_dialogue, speakers_json, primary_speaker,
                   has_q_and_a, qa_analytics, topics
            FROM transcripts WHERE id = ?
        """, (transcript_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'error': 'Transcript not found'}), 404

        text_content = row['full_dialogue']
        if not text_content:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT full_text FROM transcripts WHERE id = ?", (transcript_id,))
            alt_row = cursor.fetchone()
            conn.close()
            if alt_row and 'full_text' in alt_row.keys():
                text_content = alt_row['full_text']

        speakers = json.loads(row['speakers_json']) if row['speakers_json'] else []
        qa_analytics = json.loads(row['qa_analytics']) if row['qa_analytics'] else None
        topics = json.loads(row['topics']) if row.get('topics') else []

        return jsonify({
            'id': row['id'],
            'title': row['title'],
            'date': row['date'],
            'speech_type': row['speech_type'],
            'location': row['location'] or '',
            'url': row['url'],
            'word_count': row['word_count'] or 0,
            'speech_duration_seconds': row['speech_duration_seconds'] or 0,
            'full_dialogue': text_content or '',
            'full_text': text_content or '',
            'speakers': speakers,
            'primary_speaker': row['primary_speaker'] or '',
            'has_q_and_a': row['has_q_and_a'] or 0,
            'qa_analytics': qa_analytics,
            'topics': topics
        })

    except Exception as e:
        logging.error(f"Get transcript error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/transcripts/<int:transcript_id>', methods=['PUT'])
def update_transcript(transcript_id):
    """Update a transcript"""
    try:
        data = request.json
        title = data.get('title')
        date = data.get('date')
        speech_type = data.get('speech_type')
        full_dialogue = data.get('full_dialogue', '')
        primary_speaker = data.get('primary_speaker', '')
        topics = data.get('topics', [])
        if isinstance(topics, str):
            try: topics = json.loads(topics)
            except: topics = []

        if not all([title, date, speech_type]):
            return jsonify({'error': 'Missing required fields'}), 400

        word_count = len(full_dialogue.split()) if full_dialogue else 0

        if _use_github():
            existing = _get_cached_transcript(transcript_id)
            if not existing:
                return jsonify({'error': 'Transcript not found'}), 404
            # Merge fields
            payload = dict(existing)
            payload.update({
                'title': title,
                'date': date,
                'speech_type': speech_type,
                'full_dialogue': full_dialogue,
                'word_count': word_count,
                'primary_speaker': primary_speaker or payload.get('primary_speaker', ''),
                'topics': topics,
            })
            store = get_github_store()
            store.update_transcript_in_store(transcript_id, payload)
            _update_cache_after_write(transcript_id, payload)
            logging.info(f"✅ Updated transcript {transcript_id} in GitHub store")
        else:
            topics_str = json.dumps(topics) if topics else None
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE transcripts
                SET title = ?, date = ?, speech_type = ?, full_dialogue = ?,
                    word_count = ?, primary_speaker = ?, topics = ?
                WHERE id = ?
            """, (title, date, speech_type, full_dialogue, word_count,
                  primary_speaker, topics_str, transcript_id))
            if cursor.rowcount == 0:
                conn.close()
                return jsonify({'error': 'Transcript not found'}), 404
            conn.commit()
            conn.close()
            logging.info(f"✅ Updated transcript {transcript_id} in SQLite")
            auto_export_backup()

        return jsonify({'success': True})

    except Exception as e:
        logging.error(f"Update transcript error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/transcripts/<int:transcript_id>', methods=['DELETE'])
def delete_transcript(transcript_id):
    """Delete a transcript"""
    try:
        if _use_github():
            store = get_github_store()
            store.delete_transcript_from_store(transcript_id)
            _remove_from_cache(transcript_id)
            logging.info(f"🗑️ Deleted transcript {transcript_id} from GitHub store")
        else:
            if HAS_BACKUP:
                backup_database.create_backup(reason=f'pre_delete_{transcript_id}')
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
            if cursor.rowcount == 0:
                conn.close()
                return jsonify({'error': 'Transcript not found'}), 404
            conn.commit()
            conn.close()
            logging.info(f"🗑️ Deleted transcript {transcript_id} from SQLite")
            auto_export_backup()

        return jsonify({'success': True})

    except Exception as e:
        logging.error(f"Delete transcript error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/backup', methods=['POST'])
def create_manual_backup():
    """Create a manual backup of the database"""
    try:
        if not HAS_BACKUP:
            return jsonify({'error': 'Backup module not available'}), 503
        
        reason = request.json.get('reason', 'manual') if request.json else 'manual'
        backup_path = backup_database.create_backup(reason=reason)
        
        if backup_path:
            return jsonify({
                'success': True,
                'backup_path': backup_path,
                'message': 'Backup created successfully'
            })
        else:
            return jsonify({'error': 'Backup failed'}), 500
            
    except Exception as e:
        logging.error(f"Manual backup error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/backups', methods=['GET'])
def list_backups():
    """List all available backups"""
    try:
        if not HAS_BACKUP:
            return jsonify({'error': 'Backup module not available'}), 503
        
        backups = backup_database.list_backups()
        return jsonify({'backups': backups})
        
    except Exception as e:
        logging.error(f"List backups error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/export', methods=['POST'])
def export_transcripts_json():
    """Export all transcripts to JSON backup"""
    try:
        if not HAS_EXPORT:
            return jsonify({'error': 'Export module not available'}), 503
        
        filepath = export_backup.export_all_transcripts()
        
        if filepath:
            return jsonify({
                'success': True,
                'filepath': filepath,
                'message': 'Transcripts exported successfully'
            })
        else:
            return jsonify({'error': 'Export failed'}), 500
            
    except Exception as e:
        logging.error(f"Export error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/import', methods=['POST'])
def import_transcripts_json():
    """Import transcripts from JSON backup"""
    try:
        if not HAS_EXPORT:
            return jsonify({'error': 'Import module not available'}), 503
        
        data = request.json or {}
        filepath = data.get('filepath', 'data/json_backups/transcripts_latest.json')
        
        if export_backup.import_from_backup(filepath):
            return jsonify({
                'success': True,
                'message': 'Transcripts imported successfully'
            })
        else:
            return jsonify({'error': 'Import failed'}), 500
            
    except Exception as e:
        logging.error(f"Import error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/download-backup', methods=['GET'])
def download_backup():
    """Download the latest JSON backup file"""
    try:
        latest_backup = 'data/json_backups/transcripts_latest.json'
        if os.path.exists(latest_backup):
            return send_file(
                latest_backup,
                mimetype='application/json',
                as_attachment=True,
                download_name='transcripts_backup.json'
            )
        else:
            return jsonify({'error': 'No backup file found'}), 404
    except Exception as e:
        logging.error(f"Download backup error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/fix-transcripts', methods=['POST'])
def fix_existing_transcripts_api():
    """Clean titles and normalize speaker names in existing transcripts"""
    try:
        fixed_count = 0
        changes = []

        def _normalize_primary(speaker):
            if not speaker:
                return speaker
            s = speaker.strip().lower()
            if 'mamdani' in s: return 'Mamdani'
            if 'hochul' in s: return 'Hochul'
            if 'trump' in s: return 'Trump'
            if 'vance' in s: return 'JD Vance'
            return speaker.strip()

        if _use_github():
            store = get_github_store()
            all_t = _get_all_cached_transcripts()
            for t in all_t:
                tid = t.get('id')
                old_title = t.get('title', '')
                old_speaker = t.get('primary_speaker', '')
                new_title = clean_title(old_title)
                new_speaker = _normalize_primary(old_speaker)
                if new_title != old_title or new_speaker != old_speaker:
                    t['title'] = new_title
                    t['primary_speaker'] = new_speaker
                    store.update_transcript_in_store(tid, t)
                    _update_cache_after_write(tid, t)
                    fixed_count += 1
                    change = {'id': tid}
                    if new_title != old_title:
                        change['title_old'] = old_title
                        change['title_new'] = new_title
                    if new_speaker != old_speaker:
                        change['speaker_old'] = old_speaker
                        change['speaker_new'] = new_speaker
                    changes.append(change)
        else:
            if HAS_BACKUP:
                backup_database.create_backup(reason='pre_fix_transcripts')
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, primary_speaker FROM transcripts")
            rows = cursor.fetchall()
            for row in rows:
                tid = row['id']
                old_title = row['title']
                old_speaker = row['primary_speaker']
                new_title = clean_title(old_title)
                new_speaker = _normalize_primary(old_speaker)
                if new_title != old_title or new_speaker != old_speaker:
                    cursor.execute(
                        "UPDATE transcripts SET title = ?, primary_speaker = ? WHERE id = ?",
                        (new_title, new_speaker, tid)
                    )
                    fixed_count += 1
                    change = {'id': tid}
                    if new_title != old_title:
                        change['title_old'] = old_title; change['title_new'] = new_title
                    if new_speaker != old_speaker:
                        change['speaker_old'] = old_speaker; change['speaker_new'] = new_speaker
                    changes.append(change)
            conn.commit()
            conn.close()

        logging.info(f"✅ Fixed {fixed_count} transcripts")
        return jsonify({'success': True, 'fixed_count': fixed_count, 'changes': changes,
                        'message': f'Fixed {fixed_count} transcripts'})

    except Exception as e:
        logging.error(f"Fix transcripts error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

def format_seconds(seconds):
    """Format seconds as M:SS or H:MM:SS"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def parse_otter_transcript(text, detect_qa=False):
    """Parse Otter.ai transcript format"""
    import re
    
    lines = text.split('\n')
    segments = []
    
    # Otter format: "Speaker Name  M:SS  " followed by text
    header_re = re.compile(r'^(.+?)\s{2,}(\d{1,2}:\d{2}(?::\d{2})?)\s*$')
    
    current_speaker = None
    current_start = None
    text_lines = []
    
    def flush_segment():
        if current_speaker and current_start is not None and text_lines:
            segment_text = ' '.join(text_lines).strip()
            if segment_text and not segment_text.startswith('Transcribed by'):
                segments.append({
                    'speaker': current_speaker,
                    'start_seconds': current_start,
                    'text': segment_text
                })
        text_lines.clear()
    
    for line in lines:
        trimmed = line.strip()
        if not trimmed or trimmed.startswith('Transcribed by'):
            continue
        
        match = header_re.match(line)
        if match:
            flush_segment()
            current_speaker = match.group(1).strip()
            time_str = match.group(2)
            # Convert time to seconds
            parts = list(map(int, time_str.split(':')))
            if len(parts) == 3:
                current_start = parts[0] * 3600 + parts[1] * 60 + parts[2]
            else:
                current_start = parts[0] * 60 + parts[1]
        elif trimmed:
            text_lines.append(trimmed)
    
    flush_segment()
    
    # Calculate stats
    speaker_stats = {}
    for seg in segments:
        if seg['speaker'] not in speaker_stats:
            speaker_stats[seg['speaker']] = {'words': 0, 'turns': 0}
        speaker_stats[seg['speaker']]['words'] += len(seg['text'].split())
        speaker_stats[seg['speaker']]['turns'] += 1
    
    # Suggest primary speaker
    primary = max(speaker_stats.items(), key=lambda x: x[1]['words'])[0] if speaker_stats else None
    
    # Q&A detection
    qa_analytics = None
    if detect_qa and primary:
        qa_analytics = detect_qa_patterns(segments, primary)
    
    return {
        'segments': segments,
        'segmentCount': len(segments),
        'totalSeconds': segments[-1]['start_seconds'] if segments else 0,
        'speakersDetected': list(speaker_stats.keys()),
        'suggestedPrimarySpeaker': primary,
        'qaAnalytics': qa_analytics
    }

def _is_likely_question(seg, primary_speaker):
    """
    Strict gating: a segment must have at least ONE strong syntactic question
    signal. This eliminates back-and-forth chatter (e.g. 'You can give me some',
    'There we go') that the old permissive scorer would flag as questions.

    Calibrated for press conferences / interviews where questions can be:
      - Long multi-part queries (reporters often ask 80-150 word questions)
      - Statements ending in '?' after context-setting
      - Indirect questions ('I wonder if...', "I'd like to know...")
      - Questions addressed to a subject by title ('Mr. Mayor, ...')
    """
    text = seg['text']
    text_lower = text.lower().strip()
    word_count = len(text.split())

    # Must be a non-primary speaker
    if primary_speaker and seg['speaker'] == primary_speaker:
        return False

    # Skip very long segments – even multi-part press conf questions rarely exceed 150 words
    if word_count > 150:
        return False

    # ── HARD GATE ──────────────────────────────────────────────────────────
    has_question_mark = '?' in text
    starts_with_interrogative = bool(re.match(
        r'^(what|how|why|when|where|who|which|is|are|do|does|did|have|has|had|will|would|can|could|shall|should|may|might)\b',
        text_lower
    ))
    # Covers: "can you tell us...", "I wonder what...", "I'd like to know...", etc.
    has_direct_question = bool(re.search(
        r'\b(can you|could you|would you|will you|do you|did you|have you|are you|is there|are there'
        r'|i wonder|i\'m wondering|i was wondering|i wanted to ask|i want to (ask|know)'
        r'|i\'d like to (ask|know)|can you (tell|comment|explain|clarify|address)'
        r'|what (is|are|was|were) your|what\'s your|what do you (think|believe|say|make)'
        r'|how do you (feel|respond|react|see)|what (are|were) the)\b',
        text_lower
    ))

    if not has_question_mark and not starts_with_interrogative and not has_direct_question:
        return False

    # ── ANTI-FALSE-POSITIVE FILTERS ────────────────────────────────────────
    is_narrative = bool(re.match(
        r'^(and (then|now|so|we|you|I|it|this|that|there)|there (we|you) go|look at (this|that)|we need|I need|put it|let(\'?s| us)|oh (look|and)|so (we|you|I)|just |maybe |we want|we can)',
        text_lower
    ))
    if is_narrative and not starts_with_interrogative and not has_direct_question:
        return False

    is_greeting = bool(re.search(
        r'\b(thank you|thanks|good (morning|afternoon|evening)|hello|hi\b|bye|goodbye|great question)\b',
        text_lower
    ))
    if is_greeting and not starts_with_interrogative and not has_direct_question and not has_question_mark:
        return False

    # ── REPORTER ADDRESS BONUS ─────────────────────────────────────────────
    # Reporters often address the subject by title before asking – reliable signal
    addresses_subject = bool(re.search(
        r'\b(mr\.|ms\.|mrs\.|mayor|commissioner|governor|president|secretary|senator|congressman|congresswoman|councilmember|chancellor|minister)\b',
        text_lower
    ))

    # ── CONFIDENCE SCORING ─────────────────────────────────────────────────
    score = 0
    if has_question_mark: score += 4
    if starts_with_interrogative: score += 3
    if has_direct_question: score += 3
    if addresses_subject: score += 2
    if word_count <= 80: score += 1
    if is_narrative: score -= 3
    if is_greeting and not has_question_mark: score -= 2

    return score >= 4


def detect_qa_patterns(segments, primary_speaker):
    """
    Detect Q&A pairs in transcript segments using strict question gating,
    merged primary-speaker responses, and response validation.
    """
    pairs = []

    for i, seg in enumerate(segments):
        if not _is_likely_question(seg, primary_speaker):
            continue

        # ── Merge consecutive primary-speaker response segments ────────────
        merged_text = ''
        merged_word_count = 0
        response_start = None
        last_response_idx = -1

        for j in range(i + 1, len(segments)):
            rseg = segments[j]
            if primary_speaker:
                if rseg['speaker'] != primary_speaker:
                    break
                if response_start is None:
                    response_start = rseg['start_seconds']
                merged_text += (' ' if merged_text else '') + rseg['text']
                merged_word_count += len(rseg['text'].split())
                last_response_idx = j
            else:
                # No primary speaker – take immediately next segment only
                if j == i + 1:
                    response_start = rseg['start_seconds']
                    merged_text = rseg['text']
                    merged_word_count = len(rseg['text'].split())
                    last_response_idx = j
                break

        # ── Validate response ──────────────────────────────────────────────
        if not merged_text or response_start is None:
            continue

        # Must be substantive
        if merged_word_count < 15:
            continue

        # Response should not itself be a question
        resp_lower = merged_text.lower().strip()
        if merged_text.strip().endswith('?') or re.match(
            r'^(what|how|why|when|where|who|which|is|are|do|does|did)\b', resp_lower
        ):
            continue

        # ── Duration ──────────────────────────────────────────────────────
        response_duration = None
        if last_response_idx >= 0 and last_response_idx + 1 < len(segments):
            response_duration = (
                segments[last_response_idx + 1]['start_seconds'] - response_start
            )
        elif last_response_idx >= 0:
            end_s = segments[last_response_idx].get('end_seconds')
            if end_s is not None:
                response_duration = end_s - response_start

        qa_key = f"{seg['speaker']}:{seg['start_seconds']}"
        resp_speaker = primary_speaker or (
            segments[last_response_idx]['speaker'] if last_response_idx >= 0 else ''
        )

        pairs.append({
            'qaKey': qa_key,
            'questionSpeaker': seg['speaker'],
            'questionText': seg['text'],
            'questionStart': seg['start_seconds'],
            'questionWordCount': len(seg['text'].split()),
            'responseSpeaker': resp_speaker,
            'responseText': merged_text,
            'responseStart': response_start,
            'responseWordCount': merged_word_count,
            'responseDurationSeconds': response_duration,
        })

    if not pairs:
        return {'questionCount': 0, 'avgResponseWords': 0, 'avgResponseSeconds': None, 'pairs': []}

    avg_words = round(sum(p['responseWordCount'] for p in pairs) / len(pairs))
    durations = [p['responseDurationSeconds'] for p in pairs if p['responseDurationSeconds'] is not None]
    avg_seconds = round(sum(durations) / len(durations), 1) if durations else None

    return {
        'questionCount': len(pairs),
        'avgResponseWords': avg_words,
        'avgResponseSeconds': avg_seconds,
        'pairs': pairs,
    }

@app.route('/api/store-status', methods=['GET'])
def store_status():
    """Debug endpoint showing current store configuration and cache state."""
    info = {
        'store': TRANSCRIPT_STORE,
        'env_TRANSCRIPT_STORE': os.environ.get('TRANSCRIPT_STORE', '<not set>'),
        'env_GITHUB_REPO': os.environ.get('GITHUB_REPO', '<not set>'),
        'env_GITHUB_TOKEN_set': bool(os.environ.get('GITHUB_TOKEN')),
        'github_store_available': HAS_GITHUB_STORE,
        'using_github': _use_github(),
    }
    if HAS_GITHUB_STORE:
        try:
            store = get_github_store()
            info['github_store_enabled'] = store.enabled
        except Exception as e:
            info['github_store_error'] = str(e)
    if _use_github():
        with _cache_lock:
            info['cache'] = {
                'index_count': len(_cache['index']),
                'full_count': len(_cache['full']),
                'loaded_at': _cache['loaded_at'],
                'age_seconds': round(time.time() - _cache['loaded_at'], 1) if _cache['loaded_at'] else None,
                'ttl': _cache['ttl'],
            }
    return jsonify(info)


# ---------------------------------------------------------------------------
# Q&A Training — labels + OpenAI classifier
# ---------------------------------------------------------------------------

@app.route('/api/qa-labels', methods=['GET'])
def get_qa_labels():
    """GET /api/qa-labels?transcript_id=...  or  ?stats=1"""
    stats = request.args.get('stats')
    if stats == '1':
        if _use_github():
            labels = _github_get_all_qa_labels()
            total_yes = sum(1 for l in labels if l.get('is_qa'))
            total_no  = sum(1 for l in labels if not l.get('is_qa'))
        else:
            conn = get_db()
            cur  = conn.cursor()
            cur.execute("SELECT COUNT(*) as n FROM qa_labels WHERE is_qa=1")
            total_yes = cur.fetchone()['n']
            cur.execute("SELECT COUNT(*) as n FROM qa_labels WHERE is_qa=0")
            total_no  = cur.fetchone()['n']
            conn.close()
        return jsonify({'totalYes': total_yes, 'totalNo': total_no,
                        'total': total_yes + total_no})

    transcript_id = request.args.get('transcript_id')
    if not transcript_id:
        return jsonify({'error': 'transcript_id is required'}), 400

    if _use_github():
        labels = [l for l in _github_get_all_qa_labels()
                  if str(l.get('transcript_id')) == str(transcript_id)]
    else:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""SELECT id, transcript_id, question_speaker, question_text,
                              response_speaker, response_text, is_qa, reasoning, created_at
                       FROM qa_labels WHERE transcript_id=? ORDER BY created_at ASC""",
                    (transcript_id,))
        rows = cur.fetchall()
        conn.close()
        labels = [dict(r) for r in rows]

    return jsonify(labels)


@app.route('/api/qa-labels', methods=['POST'])
def save_qa_label():
    """POST /api/qa-labels — upsert a human label for a Q&A candidate."""
    data = request.get_json(force=True)
    transcript_id  = data.get('transcript_id')
    q_speaker      = data.get('question_speaker', '')
    q_text         = data.get('question_text', '')
    r_speaker      = data.get('response_speaker', '')
    r_text         = data.get('response_text', '')
    is_qa          = data.get('is_qa')
    reasoning      = data.get('reasoning', '')

    if not transcript_id or not q_text or not r_text or is_qa is None:
        return jsonify({'error': 'transcript_id, question_text, response_text, is_qa are required'}), 400

    is_qa_int = 1 if is_qa else 0

    if _use_github():
        label_id = _github_upsert_qa_label(transcript_id, q_speaker, q_text,
                                           r_speaker, r_text, is_qa_int, reasoning)
        return jsonify({'id': label_id, 'is_qa': bool(is_qa)})

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT id FROM qa_labels WHERE transcript_id=? AND question_text=?",
                (transcript_id, q_text))
    existing = cur.fetchone()
    if existing:
        cur.execute("""UPDATE qa_labels SET is_qa=?, reasoning=?,
                       updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (is_qa_int, reasoning, existing['id']))
        label_id = existing['id']
    else:
        cur.execute("""INSERT INTO qa_labels
                       (transcript_id, question_speaker, question_text, response_speaker,
                        response_text, is_qa, reasoning)
                       VALUES (?,?,?,?,?,?,?)""",
                    (transcript_id, q_speaker, q_text, r_speaker, r_text, is_qa_int, reasoning))
        label_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': label_id, 'is_qa': bool(is_qa)})


def _github_get_all_qa_labels():
    """Load qa_labels list from GitHub store (stored as a single JSON file)."""
    if not _use_github():
        return []
    try:
        from github_store import _get_file, GITHUB_STORE_PREFIX
        data, _ = _get_file(f'{GITHUB_STORE_PREFIX}/qa_labels.json')
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _github_upsert_qa_label(transcript_id, q_speaker, q_text, r_speaker,
                             r_text, is_qa_int, reasoning):
    """Upsert a label into the GitHub-backed qa_labels.json file."""
    from github_store import _get_file, _put_file, GITHUB_STORE_PREFIX
    import datetime
    path   = f'{GITHUB_STORE_PREFIX}/qa_labels.json'
    labels, sha = _get_file(path)
    if labels is None:
        labels = []
    existing_idx = next(
        (i for i, l in enumerate(labels)
         if str(l.get('transcript_id')) == str(transcript_id)
            and l.get('question_text') == q_text),
        None
    )
    now = datetime.datetime.utcnow().isoformat()
    if existing_idx is not None:
        labels[existing_idx].update({'is_qa': is_qa_int, 'reasoning': reasoning, 'updated_at': now})
        label_id = labels[existing_idx]['id']
    else:
        label_id = int(time.time() * 1000)
        labels.append({
            'id': label_id, 'transcript_id': transcript_id,
            'question_speaker': q_speaker, 'question_text': q_text,
            'response_speaker': r_speaker, 'response_text': r_text,
            'is_qa': is_qa_int, 'reasoning': reasoning,
            'created_at': now, 'updated_at': now,
        })
    _put_file(path, labels, f'Update qa_labels ({len(labels)} entries)', sha=sha)
    return label_id


@app.route('/api/qa-classify', methods=['POST'])
def qa_classify():
    """POST /api/qa-classify — classify candidate exchanges via OpenAI few-shot prompt.
    Body: { candidates: [{qaKey, questionSpeaker, questionText, responseSpeaker, responseText}],
            primarySpeaker: str }
    Returns: { usedAI: bool, results: [{qaKey, isQA, confidence, reason}] }
    """
    try:
        import openai as _openai
    except ImportError:
        return jsonify({'usedAI': False, 'results': [],
                        'message': 'openai package not installed'}), 200

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return jsonify({'usedAI': False, 'results': [],
                        'message': 'OPENAI_API_KEY not set'}), 200

    data           = request.get_json(force=True)
    candidates     = data.get('candidates', [])
    primary_speaker = data.get('primarySpeaker', '')

    if not candidates:
        return jsonify({'usedAI': False, 'results': []}), 200

    MIN_LABELS = 10
    if _use_github():
        all_labels = _github_get_all_qa_labels()
        yes_labels = [l for l in all_labels if l.get('is_qa')][-12:]
        no_labels  = [l for l in all_labels if not l.get('is_qa')][-12:]
    else:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""SELECT question_speaker,question_text,response_speaker,response_text,
                              is_qa,reasoning FROM qa_labels WHERE is_qa=1
                       ORDER BY created_at DESC LIMIT 12""")
        yes_labels = [dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT question_speaker,question_text,response_speaker,response_text,
                              is_qa,reasoning FROM qa_labels WHERE is_qa=0
                       ORDER BY created_at DESC LIMIT 12""")
        no_labels  = [dict(r) for r in cur.fetchall()]
        conn.close()

    total_labels = len(yes_labels) + len(no_labels)
    if total_labels < MIN_LABELS:
        return jsonify({'usedAI': False, 'results': [],
                        'message': f'Need {MIN_LABELS} labels, have {total_labels}'}), 200

    def _interleave(a, b):
        out = []
        for i in range(max(len(a), len(b))):
            if i < len(a): out.append(a[i])
            if i < len(b): out.append(b[i])
        return out

    def _trunc(text, words=80):
        parts = text.split()
        return ' '.join(parts[:words]) + ('…' if len(parts) > words else '')

    examples = _interleave(yes_labels, no_labels)
    few_shot = '\n\n'.join(
        f"Example {i+1}:\n"
        f"  Question speaker: {ex.get('question_speaker','')}\n"
        f"  Question: \"{_trunc(ex.get('question_text',''))}\"\n"
        f"  Response speaker: {ex.get('response_speaker','')}\n"
        f"  Response: \"{_trunc(ex.get('response_text',''))}\"\n"
        f"  Label: {'YES — genuine Q&A' if ex.get('is_qa') else 'NO — not Q&A'}"
        + (f"\n  Reason: {ex['reasoning']}" if ex.get('reasoning') else '')
        for i, ex in enumerate(examples)
    )

    system_prompt = f"""You are an expert at identifying genuine Q&A exchanges in political press conferences, interviews, and public speeches.

PRIMARY SPEAKER being questioned: "{primary_speaker}"

WHAT COUNTS AS Q&A:
- A reporter or audience member asks a direct, substantive question about policy, events, or the primary speaker's actions/views
- The primary speaker gives a genuine answer (not just a transition or filler phrase)
- The question has clear interrogative intent — whether or not it ends with a question mark

WHAT DOES NOT COUNT AS Q&A:
- Conversational back-and-forth without a real question (e.g. "Thank you, great, okay")
- The moderator redirecting the floor or introducing someone
- The primary speaker summarising what another speaker said
- Short filler exchanges ("Yeah", "Right", "Exactly") even if followed by a real response
- A question asked to someone other than the primary speaker

LABELED EXAMPLES FROM HUMAN TRAINER:
{few_shot}

Return a JSON object with this exact shape:
{{"results": [{{"qaKey": "<exact qaKey>", "isQA": true|false, "confidence": 0.0-1.0, "reason": "<one sentence>"}}]}}"""

    user_lines = '\n\n'.join(
        f"Candidate {i+1}:\n"
        f"  qaKey: \"{c['qaKey']}\"\n"
        f"  Question speaker: {c.get('questionSpeaker','')}\n"
        f"  Question: \"{_trunc(c.get('questionText',''), 120)}\"\n"
        f"  Response speaker: {c.get('responseSpeaker','')}\n"
        f"  Response: \"{_trunc(c.get('responseText',''), 120)}\""
        for i, c in enumerate(candidates)
    )
    user_prompt = f"Classify each of the following {len(candidates)} candidate exchange(s):\n\n{user_lines}"

    try:
        client = _openai.OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model='gpt-4o-mini',
            temperature=0,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user',   'content': user_prompt},
            ]
        )
        raw     = completion.choices[0].message.content or '{}'
        parsed  = json.loads(raw)
        results = [
            {
                'qaKey':      r.get('qaKey', ''),
                'isQA':       bool(r.get('isQA', False)),
                'confidence': max(0.0, min(1.0, float(r.get('confidence', 0.5)))),
                'reason':     r.get('reason', ''),
            }
            for r in (parsed.get('results') or [])
        ]
        return jsonify({'usedAI': True, 'results': results})
    except Exception as e:
        logging.error(f"OpenAI classify error: {e}")
        return jsonify({'usedAI': False, 'results': [],
                        'message': f'OpenAI error: {str(e)}'}), 200


@app.route('/api/qa-candidates/<int:transcript_id>', methods=['GET'])
def get_qa_candidates(transcript_id):
    """Return the candidate exchanges for a transcript (for the labeling UI)."""
    if _use_github():
        # Use the in-memory cache (same path as get_transcript_for_edit)
        t = _get_cached_transcript(transcript_id)
        if not t:
            # Cache miss — fetch directly from GitHub store
            store = get_github_store()
            t = store.get_transcript(transcript_id)
    else:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM transcripts WHERE id=?", (transcript_id,))
        row = cur.fetchone()
        conn.close()
        t = dict(row) if row else None

    if not t:
        return jsonify({'error': 'Transcript not found'}), 404

    full_dialogue  = t.get('full_dialogue') or t.get('full_text') or ''
    primary        = t.get('primary_speaker') or ''
    speakers_raw   = t.get('speakers') or []
    if isinstance(speakers_raw, str):
        try: speakers_raw = json.loads(speakers_raw)
        except: speakers_raw = []
    extra_speakers = [s for s in speakers_raw if s and not _is_generic_speaker(s)]

    segments   = _parse_segments_from_dialogue(full_dialogue)
    candidates = _extract_candidate_exchanges(segments, primary, extra_speakers)

    return jsonify({
        'candidates':     candidates,
        'primarySpeaker': primary,
        'title':          t.get('title', ''),
        'transcriptId':   transcript_id,
    })


def _parse_segments_from_dialogue(full_dialogue):
    """Parse 'Speaker Name (M:SS): text' blocks separated by double newlines."""
    segments = []
    if not full_dialogue:
        return segments
    seg_pattern = re.compile(r'^(.+?)\s*\((\d+):(\d+)(?::(\d+))?\):\s*([\s\S]+)$')
    for block in full_dialogue.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        m = seg_pattern.match(block)
        if not m:
            continue
        speaker = m.group(1).strip()
        g2, g3, g4 = int(m.group(2)), int(m.group(3)), m.group(4)
        start_s = g2 * 3600 + g3 * 60 + int(g4) if g4 is not None else g2 * 60 + g3
        text = m.group(5).strip()
        if text:
            segments.append({'speaker': speaker, 'start_seconds': start_s, 'text': text})
    return segments


def _is_generic_speaker(speaker_name):
    """Return True if this is an unidentified/reporter speaker (Speaker N, Unknown Speaker)."""
    s = speaker_name.strip().lower()
    return bool(re.match(r'^speaker\s*\d+$', s)) or s in ('unknown speaker', 'unknown', 'speaker')


def _resolve_official_speakers(segments, primary_speaker, extra_speakers=None):
    """
    Identify who the official speakers are.
    Combines:
      1. The stored primary_speaker (fuzzy match)
      2. Any extra_speakers list from metadata
      3. Auto-detection: non-generic speakers who account for >15% of words
    Returns a set of speaker names (as they appear in the transcript).
    """
    officials = set()

    # Count words per speaker
    word_counts = {}
    total_words = 0
    for seg in segments:
        w = len(seg['text'].split())
        word_counts[seg['speaker']] = word_counts.get(seg['speaker'], 0) + w
        total_words += w
    if total_words == 0:
        return officials

    for spk, wc in word_counts.items():
        if _is_generic_speaker(spk):
            continue
        # Include if: matches primary_speaker, OR in extra_speakers list, OR speaks >15% of words
        is_primary = primary_speaker and (
            primary_speaker.lower() in spk.lower() or
            spk.lower() in primary_speaker.lower() or
            any(part in spk.lower() for part in primary_speaker.lower().split() if len(part) > 3)
        )
        in_extras = extra_speakers and any(
            (e.lower() in spk.lower() or spk.lower() in e.lower())
            for e in extra_speakers if e and not _is_generic_speaker(e)
        )
        dominant = (wc / total_words) > 0.15
        if is_primary or in_extras or dominant:
            officials.add(spk)

    return officials


def _extract_candidate_exchanges(segments, primary_speaker, extra_speakers=None):
    """
    Return every non-official-speaker turn (>=5 words) followed by an
    official-speaker response (>=15 words).
    Handles joint briefings (multiple official responders).
    """
    official_speakers = _resolve_official_speakers(segments, primary_speaker, extra_speakers)
    candidates = []

    for i, seg in enumerate(segments):
        # Skip official-speaker segments — those are answers, not questions
        if seg['speaker'] in official_speakers:
            continue
        word_count = len(seg['text'].split())
        if word_count < 5:
            continue

        # Find the next segment by an official speaker
        merged_text  = ''
        merged_words = 0
        resp_start   = None
        resp_speaker = ''
        for j in range(i + 1, len(segments)):
            rseg = segments[j]
            if rseg['speaker'] not in official_speakers:
                break   # Another non-official speaker before a response — stop
            if resp_start is None:
                resp_start   = rseg['start_seconds']
                resp_speaker = rseg['speaker']
            # Merge consecutive turns by the SAME official speaker
            if rseg['speaker'] == resp_speaker:
                merged_text  += (' ' if merged_text else '') + rseg['text']
                merged_words += len(rseg['text'].split())
            else:
                break   # Different official speaker started — don't merge across speakers

        if not merged_text or merged_words < 15:
            continue

        qa_key = f"{seg['speaker']}:{seg['start_seconds']}"
        candidates.append({
            'qaKey':             qa_key,
            'questionSpeaker':   seg['speaker'],
            'questionText':      seg['text'],
            'questionStart':     seg['start_seconds'],
            'responseSpeaker':   resp_speaker,
            'responseText':      merged_text,
            'responseStart':     resp_start,
            'responseWordCount': merged_words,
        })
    return candidates


@app.route('/api/qa-transcripts', methods=['GET'])
def get_qa_transcripts():
    """Return all transcripts with has_q_and_a=true, with candidate and label counts."""
    if _use_github():
        index = _get_cached_index()
        all_t = [t for t in index if t.get('has_q_and_a')]
    else:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""SELECT id, title, date, primary_speaker FROM transcripts
                       WHERE has_q_and_a=1 ORDER BY date DESC""")
        rows = cur.fetchall()
        conn.close()
        all_t = [dict(r) for r in rows]

    # Fetch label counts per transcript
    if _use_github():
        all_labels  = _github_get_all_qa_labels()
        label_count = {}
        for l in all_labels:
            tid = str(l.get('transcript_id'))
            label_count[tid] = label_count.get(tid, 0) + 1
    else:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT transcript_id, COUNT(*) as n FROM qa_labels GROUP BY transcript_id")
        label_count = {str(r['transcript_id']): r['n'] for r in cur.fetchall()}
        conn.close()

    result = []
    for t in all_t:
        tid = str(t.get('id'))
        result.append({
            'id':             t.get('id'),
            'title':          t.get('title'),
            'date':           t.get('date'),
            'primarySpeaker': t.get('primary_speaker') or t.get('primarySpeaker') or '',
            'labelCount':     label_count.get(tid, 0),
        })
    return jsonify({'transcripts': result})


@app.route('/api/qa-reclassify-all', methods=['POST'])
def qa_reclassify_all():
    """
    POST /api/qa-reclassify-all
    Iterates every has_q_and_a transcript, extracts candidate exchanges,
    classifies them with OpenAI (if enough labels), and updates qa_analytics.
    Body (optional): { "openai_key": "sk-..." }
    Returns a summary of what changed.
    """
    try:
        import openai as _openai
        HAS_OPENAI = True
    except ImportError:
        HAS_OPENAI = False

    # Accept key from request body OR environment variable
    body    = request.get_json(silent=True) or {}
    api_key = body.get('openai_key') or os.environ.get('OPENAI_API_KEY') or ''
    api_key = api_key.strip()
    use_ai  = HAS_OPENAI and bool(api_key)

    # Load labels for few-shot prompt
    if _use_github():
        all_labels = _github_get_all_qa_labels()
    else:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""SELECT question_speaker, question_text, response_speaker,
                              response_text, is_qa, reasoning FROM qa_labels
                       ORDER BY created_at DESC LIMIT 60""")
        all_labels = [dict(r) for r in cur.fetchall()]
        conn.close()

    yes_labels = [l for l in all_labels if l.get('is_qa')][-15:]
    no_labels  = [l for l in all_labels if not l.get('is_qa')][-15:]
    total_labels = len(yes_labels) + len(no_labels)
    use_ai = use_ai and total_labels >= 10

    # Get all Q&A transcripts
    if _use_github():
        index  = _get_cached_index()
        qa_ids = [t.get('id') for t in index if t.get('has_q_and_a')]
    else:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("SELECT id FROM transcripts WHERE has_q_and_a=1")
        qa_ids = [r['id'] for r in cur.fetchall()]
        conn.close()

    # Build few-shot prompt once
    def _trunc(text, words=80):
        parts = text.split()
        return ' '.join(parts[:words]) + ('…' if len(parts) > words else '')

    def _interleave(a, b):
        out = []
        for i in range(max(len(a), len(b))):
            if i < len(a): out.append(a[i])
            if i < len(b): out.append(b[i])
        return out

    few_shot_examples = _interleave(yes_labels, no_labels)
    few_shot = '\n\n'.join(
        f"Example {i+1}:\n"
        f"  Question: \"{_trunc(ex.get('question_text',''))}\"\n"
        f"  Response: \"{_trunc(ex.get('response_text',''))}\"\n"
        f"  Label: {'YES — genuine Q&A' if ex.get('is_qa') else 'NO — not Q&A'}"
        + (f"\n  Reason: {ex['reasoning']}" if ex.get('reasoning') else '')
        for i, ex in enumerate(few_shot_examples)
    )

    system_prompt = f"""You are an expert at identifying genuine Q&A exchanges in political press conferences.

WHAT COUNTS AS Q&A:
- A reporter asks a direct, substantive question about policy, events, or the speaker's actions/views
- The official speaker gives a genuine, substantive answer (not just a transition or filler)

WHAT DOES NOT COUNT AS Q&A:
- Conversational filler ("Thank you", "That's right", short acknowledgements)
- Moderator redirects ("Next question", "Go ahead")
- One official speaker commenting on another's remarks
- Very short exchanges with no real substance

HUMAN-LABELED EXAMPLES:
{few_shot}

Return JSON: {{"results": [{{"qaKey": "...", "isQA": true|false, "confidence": 0.0-1.0, "reason": "one sentence"}}]}}"""

    results_summary = []
    total_processed = 0
    total_updated   = 0

    for tid in qa_ids:
        try:
            # Fetch full transcript
            if _use_github():
                t = _get_cached_transcript(tid)
                if not t:
                    store = get_github_store()
                    t = store.get_transcript(tid)
            else:
                conn = get_db()
                cur  = conn.cursor()
                cur.execute("SELECT * FROM transcripts WHERE id=?", (tid,))
                row = cur.fetchone()
                conn.close()
                t = dict(row) if row else None
            if not t:
                continue

            full_dialogue = t.get('full_dialogue') or t.get('full_text') or ''
            primary       = t.get('primary_speaker') or ''
            speakers_raw  = t.get('speakers') or []
            if isinstance(speakers_raw, str):
                try: speakers_raw = json.loads(speakers_raw)
                except: speakers_raw = []
            extra_speakers = [s for s in speakers_raw if s and not _is_generic_speaker(s)]

            segments   = _parse_segments_from_dialogue(full_dialogue)
            candidates = _extract_candidate_exchanges(segments, primary, extra_speakers)
            total_processed += 1

            if not candidates:
                continue

            # Classify with OpenAI
            if use_ai:
                user_lines = '\n\n'.join(
                    f"Candidate {i+1}:\n"
                    f"  qaKey: \"{c['qaKey']}\"\n"
                    f"  Question speaker: {c['questionSpeaker']}\n"
                    f"  Question: \"{_trunc(c['questionText'], 120)}\"\n"
                    f"  Response speaker: {c['responseSpeaker']}\n"
                    f"  Response: \"{_trunc(c['responseText'], 120)}\""
                    for i, c in enumerate(candidates)
                )
                try:
                    client     = _openai.OpenAI(api_key=api_key)
                    completion = client.chat.completions.create(
                        model='gpt-4o-mini',
                        temperature=0,
                        response_format={'type': 'json_object'},
                        messages=[
                            {'role': 'system', 'content': system_prompt},
                            {'role': 'user',   'content': f"Classify these {len(candidates)} candidates:\n\n{user_lines}"},
                        ]
                    )
                    raw    = completion.choices[0].message.content or '{}'
                    parsed = json.loads(raw)
                    ai_map = {r.get('qaKey'): r for r in (parsed.get('results') or [])}
                except Exception as e:
                    logging.warning(f"OpenAI classify error for {tid}: {e}")
                    ai_map = {}
            else:
                ai_map = {}

            # Build updated qa_analytics pairs — only keep responses by the PRIMARY speaker
            pairs = []
            for c in candidates:
                # Filter: only include exchanges where the primary speaker answered
                if primary and not (
                    primary.lower() in c['responseSpeaker'].lower() or
                    c['responseSpeaker'].lower() in primary.lower() or
                    any(part in c['responseSpeaker'].lower()
                        for part in primary.lower().split() if len(part) > 3)
                ):
                    continue  # e.g. Vance answered — skip for Leavitt's speech analytics

                ai = ai_map.get(c['qaKey'], {})
                is_qa      = ai.get('isQA', True) if ai_map else True
                confidence = float(ai.get('confidence', 0.5) if ai_map else 0.5)
                if not is_qa and confidence >= 0.7:
                    continue  # AI confident it's not Q&A — skip
                pairs.append({
                    'qaKey':           c['qaKey'],
                    'questionSpeaker': c['questionSpeaker'],
                    'questionText':    c['questionText'],
                    'responseSpeaker': c['responseSpeaker'],
                    'responseText':    c['responseText'],
                    'responseWordCount': c['responseWordCount'],
                    'responseDuration':  None,
                    'aiClassified':    bool(ai_map),
                    'confidence':      round(confidence, 2),
                })

            if not pairs:
                continue

            new_analytics = {
                'questionCount':       len(pairs),
                'avgResponseWords':    round(sum(p['responseWordCount'] for p in pairs) / len(pairs)),
                'avgResponseSeconds':  None,
                'pairs':               pairs,
                'aiClassified':        bool(ai_map),
                'classifiedAt':        __import__('datetime').datetime.utcnow().isoformat(),
            }

            # Persist updated analytics
            if _use_github():
                store   = get_github_store()
                payload = dict(t)
                payload['qa_analytics'] = new_analytics
                store.put_transcript(tid, payload)
                _update_cache_after_write(tid, payload)
            else:
                conn = get_db()
                cur  = conn.cursor()
                cur.execute("UPDATE transcripts SET qa_analytics=? WHERE id=?",
                            (json.dumps(new_analytics), tid))
                conn.commit()
                conn.close()

            total_updated += 1
            results_summary.append({
                'id':        tid,
                'title':     (t.get('title') or '')[:60],
                'questions': len(pairs),
                'aiUsed':    bool(ai_map),
            })

        except Exception as e:
            logging.error(f"qa-reclassify-all error for transcript {tid}: {e}")

    return jsonify({
        'processed': total_processed,
        'updated':   total_updated,
        'aiUsed':    use_ai,
        'labelCount': total_labels,
        'results':   results_summary,
    })


# ---------------------------------------------------------------------------
# Warm cache on import when using GitHub store
# ---------------------------------------------------------------------------
if TRANSCRIPT_STORE == "github" and HAS_GITHUB_STORE:
    try:
        _store = get_github_store()
        if _store.enabled:
            logging.info("🔥 Warming GitHub transcript cache on startup...")
            _warm_cache()
        else:
            logging.warning("⚠️  TRANSCRIPT_STORE=github but store is disabled (missing token/repo)")
    except Exception as _e:
        logging.error(f"⚠️  Failed to warm cache on startup: {_e}")


def _start_keepalive():
    """
    Ping this service's own /api/health endpoint every 10 minutes so Render's
    free-tier never spins the dyno down due to inactivity.
    Only runs when RENDER_EXTERNAL_URL is set (i.e. on Render, not locally).
    """
    import urllib.request

    render_url = os.environ.get('RENDER_EXTERNAL_URL', '').rstrip('/')
    if not render_url:
        return  # Not running on Render – nothing to do

    ping_url = f"{render_url}/api/health"
    interval = 10 * 60  # 10 minutes

    def _ping_loop():
        # Stagger the first ping so the server has time to fully start
        time.sleep(60)
        while True:
            try:
                with urllib.request.urlopen(ping_url, timeout=10) as resp:
                    logging.info(f"[keep-alive] pinged {ping_url} → {resp.status}")
            except Exception as exc:
                logging.warning(f"[keep-alive] ping failed: {exc}")
            time.sleep(interval)

    t = threading.Thread(target=_ping_loop, daemon=True, name="keep-alive")
    t.start()
    logging.info(f"[keep-alive] started – pinging {ping_url} every {interval//60} min")


# Start keep-alive as soon as the module is imported (works with gunicorn too)
_start_keepalive()


if __name__ == '__main__':
    print("\n" + "="*80)
    print("🚀 MENTION MARKET TOOL - API SERVER")
    print("="*80)
    
    # Validate database path
    print(f"\n📁 Database path: {DB_PATH}")
    if os.path.exists(DB_PATH):
        db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        print(f"✅ Database found ({db_size_mb:.1f} MB)")
        
        # Quick check of transcript count
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transcripts")
            count = cursor.fetchone()[0]
            conn.close()
            print(f"✓ Database contains {count} transcripts")
        except Exception as e:
            print(f"⚠ Warning: Could not read transcript count: {e}")
    else:
        print(f"✗ WARNING: Database file not found!")
        print(f"  Expected at: {DB_PATH}")
        print(f"  API will return empty results until database is created.")
        print(f"  Run the scraper to populate the database.")
    
    print("\n📍 Available Endpoints:")
    print("  GET  /api/health                      - Health check with DB info")
    print("  GET  /api/stats                       - Database statistics")
    print("  GET  /api/transcripts                 - All transcripts WITH full text (large)")
    print("  GET  /api/transcripts/metadata        - All transcripts WITHOUT full text (lightweight)")
    print("  GET  /api/transcripts/<id>            - Get specific transcript")
    print("  GET  /api/analysis/word-frequency     - Word frequency analysis")
    print("  POST /api/scraper/refresh             - Trigger scraper refresh")
    print("  GET  /api/scraper/status              - Get scraper status")
    
    print("\n🌐 Server starting on http://localhost:5001")
    print("   Frontend should connect to: http://localhost:5001/api/transcripts")
    print("\n" + "="*80 + "\n")
    print("  GET  /api/scraper/status - Check scraper status")
    print("\nPress Ctrl+C to stop")
    print("="*80 + "\n")

    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
