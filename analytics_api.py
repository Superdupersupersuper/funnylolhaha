#!/usr/bin/env python3
"""
Enhanced API for MentionMarkets-style analytics
Handles advanced search, mention tracking, and location analysis
"""
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import re
from datetime import datetime
from collections import defaultdict
import os

app = Flask(__name__, static_folder='analytics_ui/build', static_url_path='')
CORS(app)

DB_PATH = './data/transcripts.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def pluralize_search(word):
    """Generate plural and possessive variations"""
    variations = [word, word.lower()]

    # Singular possessive
    variations.append(f"{word}'s")
    variations.append(f"{word.lower()}'s")

    # Simple plural
    if word.endswith('s'):
        variations.append(f"{word}es")
    else:
        variations.append(f"{word}s")

    # Possessive plural
    variations.append(f"{word}s'")

    # Remove duplicates
    return list(set(variations))

def extract_context(text, search_term, context_size=200):
    """Extract text around search term with highlighting"""
    matches = []
    text_lower = text.lower()
    term_lower = search_term.lower()

    # Find all occurrences
    pos = 0
    while True:
        idx = text_lower.find(term_lower, pos)
        if idx == -1:
            break

        # Get context
        start = max(0, idx - context_size)
        end = min(len(text), idx + len(search_term) + context_size)

        context = text[start:end]

        # Mark position within context
        relative_pos = idx - start

        matches.append({
            'context': context,
            'position': idx,
            'relative_position': relative_pos,
            'start': start,
            'end': end
        })

        pos = idx + 1

    return matches

def calculate_mention_location(text, search_term):
    """Calculate where in the text (0.0 to 1.0) mentions occur"""
    text_lower = text.lower()
    term_lower = search_term.lower()
    locations = []

    pos = 0
    text_len = len(text)

    while True:
        idx = text_lower.find(term_lower, pos)
        if idx == -1:
            break

        # Position as percentage (0.0 to 1.0)
        location = idx / text_len if text_len > 0 else 0
        locations.append(location)

        pos = idx + 1

    return locations

@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/search', methods=['POST'])
def advanced_search():
    """Advanced search with all the features"""
    data = request.json

    search_terms = data.get('terms', [])  # Can be multiple: ["bitcoin", "crypto"]
    start_date = data.get('startDate', '')
    end_date = data.get('endDate', '')
    speech_types = data.get('speechTypes', [])
    starts_with_only = data.get('startsWithOnly', False)
    include_plural = data.get('includePlural', True)
    context_size = data.get('contextSize', 200)
    match_beginning = data.get('matchBeginning', False)
    match_ending = data.get('matchEnding', False)

    conn = get_db()
    cursor = conn.cursor()

    # Build base query
    query = """
        SELECT id, title, date, speech_type, location, url, full_text, word_count
        FROM transcripts
        WHERE 1=1
    """
    params = []

    # Date filters
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    # Speech type filter
    if speech_types and len(speech_types) > 0:
        placeholders = ','.join(['?' for _ in speech_types])
        query += f" AND speech_type IN ({placeholders})"
        params.extend(speech_types)

    query += " ORDER BY date DESC"

    cursor.execute(query, params)
    all_transcripts = cursor.fetchall()

    results = []

    for transcript in all_transcripts:
        transcript_dict = dict(transcript)
        text = transcript_dict['full_text']

        # Search for all terms
        found_terms = []
        all_mentions = []
        mention_locations = []

        for term in search_terms:
            # Generate search variations
            if include_plural:
                search_variants = pluralize_search(term)
            else:
                search_variants = [term]

            for variant in search_variants:
                # Different search modes
                if starts_with_only:
                    # "Starts with" mode - word boundary at start only
                    pattern = r'\b' + re.escape(variant)
                elif match_beginning and match_ending:
                    # Exact match
                    pattern = r'\b' + re.escape(variant) + r'\b'
                elif match_beginning:
                    # Match beginning only
                    pattern = r'\b' + re.escape(variant)
                elif match_ending:
                    # Match ending only
                    pattern = re.escape(variant) + r'\b'
                else:
                    # Contains (default)
                    pattern = re.escape(variant)

                # Find matches
                matches = re.finditer(pattern, text, re.IGNORECASE)

                for match in matches:
                    if term not in found_terms:
                        found_terms.append(term)

                    # Extract context
                    idx = match.start()
                    start = max(0, idx - context_size)
                    end = min(len(text), idx + len(variant) + context_size)

                    context = text[start:end]

                    all_mentions.append({
                        'term': term,
                        'matched': variant,
                        'context': context,
                        'position': idx,
                        'highlight_start': idx - start,
                        'highlight_end': idx - start + len(variant)
                    })

                    # Calculate location (0.0 to 1.0)
                    location = idx / len(text) if len(text) > 0 else 0
                    mention_locations.append({
                        'term': term,
                        'location': location,
                        'position': idx
                    })

        # Only include transcripts with matches
        if len(found_terms) > 0:
            transcript_dict.pop('full_text', None)  # Don't send full text
            transcript_dict['matched_terms'] = found_terms
            transcript_dict['mention_count'] = len(all_mentions)
            transcript_dict['mentions'] = all_mentions[:10]  # Limit to first 10
            transcript_dict['mention_locations'] = mention_locations
            results.append(transcript_dict)

    conn.close()

    return jsonify({
        'results': results,
        'total': len(results),
        'terms_searched': search_terms
    })

@app.route('/api/mention-timeline', methods=['POST'])
def mention_timeline():
    """Get mention counts over time (for charts)"""
    data = request.json
    search_terms = data.get('terms', [])
    start_date = data.get('startDate', '')
    end_date = data.get('endDate', '')
    speech_types = data.get('speechTypes', [])
    include_plural = data.get('includePlural', True)
    granularity = data.get('granularity', 'month')  # month, week, day

    conn = get_db()
    cursor = conn.cursor()

    # Get all transcripts in range
    query = "SELECT date, full_text FROM transcripts WHERE date LIKE '____-__-__'"
    params = []

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    if speech_types and len(speech_types) > 0:
        placeholders = ','.join(['?' for _ in speech_types])
        query += f" AND speech_type IN ({placeholders})"
        params.extend(speech_types)

    query += " ORDER BY date"

    cursor.execute(query, params)
    transcripts = cursor.fetchall()

    # Count mentions by time period
    timeline = defaultdict(lambda: {'count': 0, 'terms': defaultdict(int)})

    for transcript in transcripts:
        date = transcript['date']
        text = transcript['full_text']

        # Determine time bucket
        if granularity == 'month':
            bucket = date[:7]  # YYYY-MM
        elif granularity == 'week':
            # Convert to week number
            dt = datetime.strptime(date, '%Y-%m-%d')
            bucket = f"{dt.year}-W{dt.isocalendar()[1]:02d}"
        else:
            bucket = date  # Daily

        # Count mentions
        for term in search_terms:
            if include_plural:
                variants = pluralize_search(term)
            else:
                variants = [term]

            for variant in variants:
                count = len(re.findall(r'\b' + re.escape(variant) + r'\b', text, re.IGNORECASE))
                if count > 0:
                    timeline[bucket]['count'] += count
                    timeline[bucket]['terms'][term] += count

    # Format for chart
    chart_data = []
    for bucket in sorted(timeline.keys()):
        chart_data.append({
            'date': bucket,
            'count': timeline[bucket]['count'],
            'terms': dict(timeline[bucket]['terms'])
        })

    conn.close()

    return jsonify({
        'timeline': chart_data,
        'granularity': granularity
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get database statistics"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM transcripts")
    total = cursor.fetchone()['count']

    cursor.execute("SELECT MIN(date) as min, MAX(date) as max FROM transcripts WHERE date LIKE '____-__-__'")
    dates = cursor.fetchone()

    cursor.execute("SELECT DISTINCT speech_type FROM transcripts ORDER BY speech_type")
    types = [row['speech_type'] for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'totalTranscripts': total,
        'dateRange': {'min': dates['min'], 'max': dates['max']},
        'speechTypes': types
    })

@app.route('/api/transcripts', methods=['GET'])
def get_transcripts():
    """Get recent transcripts"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, date, speech_type, location, url, word_count
        FROM transcripts
        WHERE date LIKE '____-__-__'
        ORDER BY date DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))

    transcripts = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) as count FROM transcripts WHERE date LIKE '____-__-__'")
    total = cursor.fetchone()['count']

    conn.close()

    return jsonify({
        'transcripts': transcripts,
        'total': total
    })

@app.route('/api/transcript/<int:transcript_id>', methods=['GET'])
def get_transcript_detail(transcript_id):
    """Get full transcript with optional search highlighting"""
    search_term = request.args.get('search', '')
    context_size = request.args.get('contextSize', 200, type=int)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM transcripts WHERE id = ?", (transcript_id,))
    transcript = cursor.fetchone()

    if not transcript:
        return jsonify({'error': 'Not found'}), 404

    result = dict(transcript)

    if search_term:
        # Extract all contexts
        contexts = extract_context(result['full_text'], search_term, context_size)
        result['search_contexts'] = contexts

    conn.close()

    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"Starting MentionMarkets Analytics API on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
