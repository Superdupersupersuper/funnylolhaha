#!/usr/bin/env python3
"""
Python API server for the Mention Market Tool
Provides endpoints for querying data and triggering scraper updates
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import threading
from full_scraper import FullScraper
from database import Database
from text_analysis import analyze_word_frequency, analyze_word_trends, count_words

app = Flask(__name__)
CORS(app)  # Allow frontend to connect

DB_PATH = './data/transcripts.db'
scraper_status = {'running': False, 'progress': '', 'last_run': None}

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

def run_scraper_async():
    """Run scraper in background"""
    global scraper_status
    scraper_status['running'] = True
    scraper_status['progress'] = 'Starting scraper...'

    try:
        scraper = FullScraper()
        result = scraper.run(skip_existing=True)
        scraper_status['progress'] = f"Complete! Saved {result['success']} new transcripts"
        scraper_status['last_run'] = result
    except Exception as e:
        scraper_status['progress'] = f'Error: {str(e)}'
    finally:
        scraper_status['running'] = False

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

@app.route('/api/transcripts', methods=['GET'])
def get_transcripts():
    """Get transcripts with filtering"""
    start_date = request.args.get('startDate', '')
    end_date = request.args.get('endDate', '')
    speech_type = request.args.get('speechType', '')
    search = request.args.get('search', '')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    conn = get_db()
    cursor = conn.cursor()

    # Build query
    query = "SELECT id, title, date, speech_type, location, url, word_count FROM transcripts WHERE 1=1"
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

    if search:
        query += " AND (title LIKE ? OR full_text LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])

    # Get count
    count_query = query.replace('SELECT id, title, date, speech_type, location, url, word_count', 'SELECT COUNT(*) as count')
    cursor.execute(count_query, params)
    total = cursor.fetchone()['count']

    # Get page
    query += " ORDER BY date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    transcripts = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'transcripts': transcripts,
        'total': total,
        'limit': limit,
        'offset': offset
    })

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
    print("="*80)
    print("MENTION MARKET TOOL - API SERVER")
    print("="*80)
    print("\nStarting server on http://localhost:5000")
    print("Endpoints:")
    print("  GET  /api/stats - Database statistics")
    print("  GET  /api/transcripts - List transcripts")
    print("  GET  /api/transcripts/<id> - Get specific transcript")
    print("  GET  /api/analysis/word-frequency - Word frequency analysis")
    print("  POST /api/scraper/refresh - Trigger scraper refresh")
    print("  GET  /api/scraper/status - Check scraper status")
    print("\nPress Ctrl+C to stop")
    print("="*80 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
