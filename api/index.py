#!/usr/bin/env python3
"""
Vercel Serverless Function Handler for Analytics API
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import re
from datetime import datetime
from collections import defaultdict
import os
import urllib.request
import zipfile

app = Flask(__name__)
CORS(app)

# Database will be downloaded to /tmp (Vercel writable directory)
DB_PATH = '/tmp/transcripts.db'
DB_URL = os.environ.get('DATABASE_URL', 'https://github.com/Superdupersupersuper/funnylolhaha/releases/download/v1.0/transcripts.db.zip')

def ensure_database():
    """Download and extract database if not present"""
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}, downloading from {DB_URL}...")
        try:
            # Download zip file
            zip_path = '/tmp/transcripts.db.zip'
            urllib.request.urlretrieve(DB_URL, zip_path)

            # Extract
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Extract to /tmp
                zip_ref.extractall('/tmp')

            # Move from data/transcripts.db to /tmp/transcripts.db
            extracted_path = '/tmp/data/transcripts.db'
            if os.path.exists(extracted_path):
                os.rename(extracted_path, DB_PATH)

            # Clean up
            os.remove(zip_path)
            if os.path.exists('/tmp/data'):
                os.rmdir('/tmp/data')

            print(f"Database downloaded and extracted to {DB_PATH}")
        except Exception as e:
            print(f"Error downloading database: {e}")
            raise

def get_db():
    ensure_database()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def pluralize_search(word):
    """Generate plural and possessive variations"""
    variations = [word, word.lower()]
    variations.append(f"{word}'s")
    variations.append(f"{word.lower()}'s")
    if word.endswith('s'):
        variations.append(f"{word}es")
    else:
        variations.append(f"{word}s")
    variations.append(f"{word}s'")
    return list(set(variations))

@app.route('/')
@app.route('/api')
def health():
    return jsonify({'status': 'ok', 'message': 'MentionMarkets Analytics API'})

@app.route('/api/search', methods=['POST'])
def advanced_search():
    """Advanced search with all the features"""
    data = request.json
    search_terms = data.get('terms', [])
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

    query = """
        SELECT id, title, date, speech_type, location, url, full_text, word_count
        FROM transcripts
        WHERE 1=1
    """
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

    query += " ORDER BY date DESC"
    cursor.execute(query, params)
    all_transcripts = cursor.fetchall()

    results = []
    for transcript in all_transcripts:
        transcript_dict = dict(transcript)
        text = transcript_dict['full_text']
        found_terms = []
        all_mentions = []
        mention_locations = []

        for term in search_terms:
            search_variants = pluralize_search(term) if include_plural else [term]

            for variant in search_variants:
                if starts_with_only:
                    pattern = r'\b' + re.escape(variant)
                elif match_beginning and match_ending:
                    pattern = r'\b' + re.escape(variant) + r'\b'
                elif match_beginning:
                    pattern = r'\b' + re.escape(variant)
                elif match_ending:
                    pattern = re.escape(variant) + r'\b'
                else:
                    pattern = re.escape(variant)

                matches = re.finditer(pattern, text, re.IGNORECASE)

                for match in matches:
                    if term not in found_terms:
                        found_terms.append(term)

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

                    location = idx / len(text) if len(text) > 0 else 0
                    mention_locations.append({
                        'term': term,
                        'location': location,
                        'position': idx
                    })

        if len(found_terms) > 0:
            transcript_dict.pop('full_text', None)
            transcript_dict['matched_terms'] = found_terms
            transcript_dict['mention_count'] = len(all_mentions)
            transcript_dict['mentions'] = all_mentions[:10]
            transcript_dict['mention_locations'] = mention_locations
            results.append(transcript_dict)

    conn.close()
    return jsonify({
        'results': results,
        'total': len(results),
        'terms_searched': search_terms
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

# Vercel serverless handler
def handler(request):
    with app.request_context(request.environ):
        return app.full_dispatch_request()
