#!/usr/bin/env python3
"""
Python API server for the Mention Market Tool
Provides endpoints for querying data and triggering scraper updates
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import json
import threading
import os
import logging
import sys
import re

# Import backup utilities
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

# Version info for deployment tracking
API_VERSION = "2.0.1"
DEPLOY_TIMESTAMP = "2025-12-19T01:30:00Z"

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

def _auto_restore_from_backup():
    """Auto-restore transcripts from latest JSON backup if available"""
    if not HAS_EXPORT:
        return
    
    try:
        latest_backup = 'data/json_backups/transcripts_latest.json'
        if os.path.exists(latest_backup):
            logging.info(f"📦 Found backup file: {latest_backup}")
            logging.info("🔄 Auto-restoring transcripts from backup...")
            
            if export_backup.import_from_backup(latest_backup):
                logging.info("✅ Transcripts restored from backup")
            else:
                logging.warning("⚠️ Failed to restore from backup")
        else:
            logging.info("ℹ️ No backup file found - starting with empty database")
    except Exception as e:
        logging.error(f"Auto-restore error: {e}")

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
    if HAS_EXPORT:
        try:
            export_backup.export_all_transcripts()
            logging.info("✅ Auto-exported transcripts to JSON backup")
        except Exception as e:
            logging.error(f"❌ Auto-export failed: {e}")

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
    """Health check endpoint with database info"""
    db_exists = os.path.exists(DB_PATH)

    health_data = {
        'status': 'healthy' if db_exists else 'warning',
        'version': API_VERSION,
        'deploy_timestamp': DEPLOY_TIMESTAMP,
        'database': {
            'path': DB_PATH,
            'exists': db_exists,
            'size_mb': round(os.path.getsize(DB_PATH) / (1024 * 1024), 2) if db_exists else 0
        },
        'transcripts': {
            'count': 0,
            'error': None
        }
    }
    
    if db_exists:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM transcripts")
            count = cursor.fetchone()['count']
            health_data['transcripts']['count'] = count
            
            # Also get a quick sample
            cursor.execute("SELECT COUNT(*) as empty_count FROM transcripts WHERE word_count = 0")
            empty_count = cursor.fetchone()['empty_count']
            health_data['transcripts']['empty_count'] = empty_count
            
            conn.close()
            
            if count == 0:
                health_data['status'] = 'warning'
                health_data['message'] = 'Database is empty. Run scraper to populate.'
        except Exception as e:
            health_data['status'] = 'error'
            health_data['transcripts']['error'] = str(e)
    else:
        health_data['message'] = f'Database file not found at {DB_PATH}'
    
    return jsonify(health_data)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get database statistics"""
    conn = get_db()
    cursor = conn.cursor()

    # Total transcripts
    cursor.execute("SELECT COUNT(*) as count FROM transcripts")
    total = cursor.fetchone()['count']

    # Total words
    cursor.execute("SELECT SUM(word_count) as total FROM transcripts")
    total_words = cursor.fetchone()['total'] or 0

    # Date range
    cursor.execute("""
        SELECT
            MIN(CASE WHEN date LIKE '____-__-__' THEN date END) as min_date,
            MAX(CASE WHEN date LIKE '____-__-__' THEN date END) as max_date
        FROM transcripts
    """)
    date_range = cursor.fetchone()

    # Speech types
    cursor.execute("""
        SELECT speech_type, COUNT(*) as count
        FROM transcripts
        GROUP BY speech_type
        ORDER BY count DESC
    """)
    speech_types = [dict(row) for row in cursor.fetchall()]

    # Year distribution
    cursor.execute("""
        SELECT
            SUBSTR(date, 1, 4) as year,
            COUNT(*) as count
        FROM transcripts
        WHERE date LIKE '____-__-__'
        GROUP BY SUBSTR(date, 1, 4)
        ORDER BY year
    """)
    years = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'totalTranscripts': total,
        'totalWords': total_words,
        'dateRange': {
            'minDate': date_range['min_date'],
            'maxDate': date_range['max_date']
        },
        'speechTypes': speech_types,
        'yearDistribution': years
    })

@app.route('/api/transcripts/metadata', methods=['GET'])
def get_transcripts_metadata():
    """Get transcript metadata WITHOUT full text - lightweight endpoint"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        logging.info("📋 Fetching transcript metadata (no full text)")

        cursor.execute("""
            SELECT
                id,
                title,
                date,
                speech_type,
                location,
                url,
                word_count,
                speakers_json,
                primary_speaker
            FROM transcripts
            ORDER BY date DESC
        """)

        rows = cursor.fetchall()
        logging.info(f"✅ Fetched {len(rows)} transcript metadata entries")
        
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
                'preview': '',  # Empty - use separate endpoint for full text
                'speakers': normalize_speakers(speakers_raw),
                'primary_speaker': row['primary_speaker'] or ''
            })

        conn.close()
        logging.info(f"📤 Returning {len(transcripts)} metadata entries")

        response = jsonify(transcripts)
        response.headers['Cache-Control'] = 'public, max-age=300'
        return response
        
    except Exception as e:
        logging.error(f"❌ Error in get_transcripts_metadata: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'transcripts': []}), 500

@app.route('/api/transcripts', methods=['GET'])
def get_transcripts():
    """Get ALL transcripts with FULL dialogue text - OPTIMIZED"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if full_dialogue column exists, fallback to full_text
        cursor.execute("PRAGMA table_info(transcripts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        text_column = 'full_dialogue' if 'full_dialogue' in columns else 'full_text'
        
        logging.info(f"🔍 Fetching transcripts with {text_column} column...")

        # Get ALL transcripts with FULL text - single optimized query
        cursor.execute(f"""
            SELECT
                id,
                title,
                date,
                speech_type,
                location,
                url,
                word_count,
                {text_column} as preview,
                speakers_json,
                primary_speaker
            FROM transcripts
            ORDER BY date DESC
        """)

        rows = cursor.fetchall()
        logging.info(f"✅ Fetched {len(rows)} transcripts from database")
        
        transcripts = []
        for row in rows:
            # Handle preview text - ensure it's a string
            preview_text = row['preview'] or ''
            if isinstance(preview_text, bytes):
                preview_text = preview_text.decode('utf-8', errors='ignore')
            
            speakers_raw = json.loads(row['speakers_json']) if row['speakers_json'] else []
            transcripts.append({
                'id': row['id'],
                'title': clean_title(row['title']),
                'date': row['date'],
                'speech_type': row['speech_type'],
                'location': row['location'] or '',
                'url': row['url'],
                'word_count': row['word_count'] or 0,
                'preview': preview_text,  # FULL TRANSCRIPT TEXT
                'speakers': normalize_speakers(speakers_raw),
                'primary_speaker': row['primary_speaker'] or ''
            })

        conn.close()
        logging.info(f"📤 Returning {len(transcripts)} transcripts to frontend")

        response = jsonify(transcripts)
        response.headers['Cache-Control'] = 'public, max-age=300'  # Cache for 5 minutes
        return response
        
    except Exception as e:
        logging.error(f"❌ Error in get_transcripts: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'transcripts': []}), 500

@app.route('/api/transcripts/<int:id>', methods=['GET'])
def get_transcript(id):
    """Get single transcript"""
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
    """Get all speech types"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT speech_type, COUNT(*) as count
        FROM transcripts
        GROUP BY speech_type
        ORDER BY count DESC
    """)

    types = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(types)

@app.route('/api/date-range', methods=['GET'])
def get_date_range():
    """Get min/max dates"""
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
    """Create a new transcript in the database"""
    try:
        data = request.json
        
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
        
        # Build full dialogue from segments
        full_dialogue = '\n\n'.join([
            f"{seg['speaker']} ({format_seconds(seg['start_seconds'])}): {seg['text']}"
            for seg in segments
        ])
        
        # Calculate word count
        word_count = sum(len(seg['text'].split()) for seg in segments)
        
        # Get speakers list
        speakers = list(set(seg['speaker'] for seg in segments))
        
        # Q&A data
        has_qa = data.get('has_q_and_a', False)
        qa_analytics = data.get('qa_analytics')
        
        # Insert into database
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO transcripts (
                title, date, speech_type, location, url, word_count,
                trump_word_count, speech_duration_seconds, full_dialogue, speakers_json,
                primary_speaker
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            clean_title(title),
            event_date,
            speech_type,
            '',  # location
            f'admin-upload-{event_date}-{title[:30].replace(" ", "-")}',  # unique URL
            word_count,
            0,  # trump_word_count (calculate if needed)
            data.get('total_seconds', 0),
            full_dialogue,
            json.dumps(normalize_speakers(speakers)),
            primary_speaker
        ))
        
        transcript_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logging.info(f"✅ Created transcript ID {transcript_id}: {title}")
        
        # Auto-export backup
        auto_export_backup()
        
        return jsonify({'id': transcript_id, 'success': True}), 201
        
    except Exception as e:
        logging.error(f"Create transcript error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/transcripts/by-speaker', methods=['GET'])
def get_transcripts_by_speaker():
    """Get all transcripts for database viewer"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, title, date, speech_type, word_count, speakers_json, primary_speaker
            FROM transcripts
            ORDER BY date DESC
        """)
        
        rows = cursor.fetchall()
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
        
        conn.close()
        return jsonify({'transcripts': transcripts})
        
    except Exception as e:
        logging.error(f"Get transcripts error: {e}", exc_info=True)
        return jsonify({'error': str(e), 'transcripts': []}), 500

@app.route('/api/admin/transcripts/<int:transcript_id>', methods=['GET'])
def get_transcript_for_edit(transcript_id):
    """Get a single transcript for editing"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, title, date, speech_type, location, url, word_count,
                   speech_duration_seconds, full_dialogue, speakers_json
            FROM transcripts
            WHERE id = ?
        """, (transcript_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Transcript not found'}), 404
        
        # Check if full_dialogue exists, fallback to full_text
        text_content = row['full_dialogue']
        if not text_content:
            # Try full_text column if it exists
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT full_text FROM transcripts WHERE id = ?", (transcript_id,))
            alt_row = cursor.fetchone()
            conn.close()
            if alt_row and 'full_text' in alt_row.keys():
                text_content = alt_row['full_text']
        
        speakers = json.loads(row['speakers_json']) if row['speakers_json'] else []
        
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
            'speakers': speakers
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
        
        if not all([title, date, speech_type]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Recalculate word count
        word_count = len(full_dialogue.split()) if full_dialogue else 0
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE transcripts
            SET title = ?, date = ?, speech_type = ?, full_dialogue = ?, word_count = ?
            WHERE id = ?
        """, (title, date, speech_type, full_dialogue, word_count, transcript_id))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Transcript not found'}), 404
        
        conn.commit()
        conn.close()
        
        logging.info(f"✅ Updated transcript ID {transcript_id}")
        
        # Auto-export backup
        auto_export_backup()
        
        return jsonify({'success': True})
        
    except Exception as e:
        logging.error(f"Update transcript error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/transcripts/<int:transcript_id>', methods=['DELETE'])
def delete_transcript(transcript_id):
    """Delete a transcript"""
    try:
        # Create backup before deletion
        if HAS_BACKUP:
            logging.info(f"📦 Creating backup before deleting transcript {transcript_id}")
            backup_database.create_backup(reason=f'pre_delete_{transcript_id}')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Transcript not found'}), 404
        
        conn.commit()
        conn.close()
        
        logging.info(f"🗑️ Deleted transcript ID {transcript_id}")
        
        # Auto-export backup
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

@app.route('/api/admin/fix-transcripts', methods=['POST'])
def fix_existing_transcripts_api():
    """Clean titles and normalize speaker names in existing transcripts"""
    try:
        # Create backup first
        if HAS_BACKUP:
            logging.info("📦 Creating backup before fixing transcripts")
            backup_path = backup_database.create_backup(reason='pre_fix_transcripts')
            if not backup_path:
                return jsonify({'error': 'Backup failed'}), 500
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get all transcripts
        cursor.execute("SELECT id, title, primary_speaker FROM transcripts")
        rows = cursor.fetchall()
        
        fixed_count = 0
        changes = []
        
        for row in rows:
            transcript_id = row['id']
            old_title = row['title']
            old_speaker = row['primary_speaker']
            
            new_title = clean_title(old_title)
            
            # Normalize speaker name
            new_speaker = old_speaker
            if old_speaker:
                s = old_speaker.strip()
                if 'mamdani' in s.lower():
                    new_speaker = 'Mamdani'
                elif 'hochul' in s.lower():
                    new_speaker = 'Hochul'
                elif 'trump' in s.lower():
                    new_speaker = 'Trump'
                elif 'vance' in s.lower():
                    new_speaker = 'JD Vance'
            
            if new_title != old_title or new_speaker != old_speaker:
                cursor.execute(
                    "UPDATE transcripts SET title = ?, primary_speaker = ? WHERE id = ?",
                    (new_title, new_speaker, transcript_id)
                )
                fixed_count += 1
                
                change = {'id': transcript_id}
                if new_title != old_title:
                    change['title_old'] = old_title
                    change['title_new'] = new_title
                if new_speaker != old_speaker:
                    change['speaker_old'] = old_speaker
                    change['speaker_new'] = new_speaker
                changes.append(change)
        
        conn.commit()
        conn.close()
        
        logging.info(f"✅ Fixed {fixed_count} transcripts")
        return jsonify({
            'success': True,
            'fixed_count': fixed_count,
            'changes': changes,
            'message': f'Fixed {fixed_count} transcripts'
        })
        
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

def detect_qa_patterns(segments, primary_speaker):
    """Detect Q&A patterns in segments"""
    pairs = []
    
    for i, seg in enumerate(segments):
        # Check if this is a question
        text_lower = seg['text'].lower()
        word_count = len(seg['text'].split())
        
        # Skip primary speaker's long segments
        if seg['speaker'] == primary_speaker or word_count > 100:
            continue
        
        # Question indicators
        has_question_mark = '?' in seg['text']
        has_question_words = bool(re.search(r'\b(what|how|why|when|where|who|which|is|are|can|could|would|will|should)\b', text_lower))
        has_question_phrase = bool(re.search(r'\b(question|wondering|curious|asking|quick question)\b', text_lower))
        starts_with_question = bool(re.match(r'^(what|how|why|when|where|who|which|is|are|can|could|would|will|should)\b', text_lower))
        is_short = word_count <= 50
        is_greeting = bool(re.search(r'\b(thank you|good (morning|afternoon|evening)|hello|hi\b)', text_lower))
        
        # Score
        score = 0
        if seg['speaker'] != primary_speaker: score += 2
        if has_question_mark: score += 4
        if has_question_words: score += 2
        if starts_with_question: score += 3
        if has_question_phrase: score += 3
        if is_short: score += 1
        if is_greeting: score -= 3
        
        if score < 5:
            continue
        
        # Find response (next segment from primary speaker)
        response_seg = None
        for j in range(i + 1, len(segments)):
            if segments[j]['speaker'] == primary_speaker:
                response_seg = segments[j]
                break
        
        if not response_seg:
            continue
        
        # Calculate response duration
        response_duration = None
        if i + 1 < len(segments):
            next_seg = segments[i + 1]
            if 'start_seconds' in next_seg and 'start_seconds' in response_seg:
                # Find the segment after the response
                for k in range(j + 1, len(segments)):
                    response_duration = segments[k]['start_seconds'] - response_seg['start_seconds']
                    break
        
        pairs.append({
            'questionSpeaker': seg['speaker'],
            'questionText': seg['text'],
            'questionStart': seg['start_seconds'],
            'questionWordCount': word_count,
            'responseSpeaker': response_seg['speaker'],
            'responseText': response_seg['text'],
            'responseStart': response_seg['start_seconds'],
            'responseWordCount': len(response_seg['text'].split()),
            'responseDurationSeconds': response_duration
        })
    
    # Calculate averages
    if not pairs:
        return {'questionCount': 0, 'avgResponseWords': 0, 'avgResponseSeconds': None, 'pairs': []}
    
    avg_words = round(sum(p['responseWordCount'] for p in pairs) / len(pairs))
    
    durations = [p['responseDurationSeconds'] for p in pairs if p['responseDurationSeconds'] is not None]
    avg_seconds = round(sum(durations) / len(durations), 1) if durations else None
    
    return {
        'questionCount': len(pairs),
        'avgResponseWords': avg_words,
        'avgResponseSeconds': avg_seconds,
        'pairs': pairs
    }

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
