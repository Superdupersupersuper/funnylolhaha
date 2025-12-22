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
    if os.path.exists(DB_PATH):
        return  # Database already exists
    
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
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON transcripts(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON transcripts(url)")
    
    conn.commit()
    conn.close()
    logging.info("✅ Database initialized successfully")

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
                speakers_json
            FROM transcripts
            ORDER BY date DESC
        """)

        rows = cursor.fetchall()
        logging.info(f"✅ Fetched {len(rows)} transcript metadata entries")
        
        transcripts = []
        for row in rows:
            transcripts.append({
                'id': row['id'],
                'title': row['title'],
                'date': row['date'],
                'speech_type': row['speech_type'],
                'location': row['location'] or '',
                'url': row['url'],
                'word_count': row['word_count'] or 0,
                'preview': '',  # Empty - use separate endpoint for full text
                'speakers': json.loads(row['speakers_json']) if row['speakers_json'] else []
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
                speakers_json
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
            
            transcripts.append({
                'id': row['id'],
                'title': row['title'],
                'date': row['date'],
                'speech_type': row['speech_type'],
                'location': row['location'] or '',
                'url': row['url'],
                'word_count': row['word_count'] or 0,
                'preview': preview_text,  # FULL TRANSCRIPT TEXT
                'speakers': json.loads(row['speakers_json']) if row['speakers_json'] else []
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

@app.route('/api/scraper/refresh', methods=['POST'])
def refresh_scraper():
    """Trigger scraper to get new transcripts"""
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
    return jsonify(scraper_status)

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
