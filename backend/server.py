"""
Mention Markets - Flask API Server
REST API for serving transcript data
"""

import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path

# Import our database module
from database import (
    init_database,
    search_segments,
    get_all_transcripts,
    get_transcript_with_segments,
    get_all_speakers,
    get_all_event_types,
    get_mention_analytics,
    get_database_stats,
    insert_transcript,
    DATABASE_PATH
)

app = Flask(__name__, static_folder='../frontend/dist', static_url_path='')
CORS(app)

# Initialize database on startup
if not DATABASE_PATH.exists():
    init_database()


@app.route('/')
def serve_frontend():
    """Serve the frontend application."""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'database': str(DATABASE_PATH)})


@app.route('/api/stats')
def get_stats():
    """Get database statistics."""
    try:
        stats = get_database_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/search')
def search():
    """
    Search transcripts.
    Query params:
    - q: search query (required)
    - speaker: filter by speaker name
    - type: filter by event type
    - start_date: filter by start date (YYYY-MM-DD)
    - end_date: filter by end date (YYYY-MM-DD)
    - limit: max results (default 100)
    - offset: pagination offset (default 0)
    """
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({'error': 'Search query (q) is required'}), 400
    
    try:
        results = search_segments(
            query=query,
            speaker=request.args.get('speaker'),
            event_type=request.args.get('type'),
            start_date=request.args.get('start_date'),
            end_date=request.args.get('end_date'),
            limit=int(request.args.get('limit', 100)),
            offset=int(request.args.get('offset', 0))
        )
        
        return jsonify({
            'query': query,
            'count': len(results),
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics')
def analytics():
    """
    Get mention analytics for a search term.
    Query params:
    - q: search query (required)
    """
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({'error': 'Search query (q) is required'}), 400
    
    try:
        data = get_mention_analytics(query)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transcripts')
def list_transcripts():
    """
    List all transcripts.
    Query params:
    - speaker: filter by primary speaker
    - type: filter by event type
    - limit: max results (default 100)
    - offset: pagination offset (default 0)
    """
    try:
        transcripts = get_all_transcripts(
            speaker=request.args.get('speaker'),
            event_type=request.args.get('type'),
            limit=int(request.args.get('limit', 100)),
            offset=int(request.args.get('offset', 0))
        )
        
        return jsonify({
            'count': len(transcripts),
            'transcripts': transcripts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transcripts/<transcript_id>')
def get_transcript(transcript_id):
    """Get a single transcript with all segments."""
    try:
        transcript = get_transcript_with_segments(transcript_id)
        
        if not transcript:
            return jsonify({'error': 'Transcript not found'}), 404
        
        return jsonify(transcript)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/speakers')
def list_speakers():
    """Get all speakers with their stats."""
    try:
        speakers = get_all_speakers()
        return jsonify({'speakers': speakers})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/event-types')
def list_event_types():
    """Get all event types."""
    try:
        types = get_all_event_types()
        return jsonify({'event_types': types})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import', methods=['POST'])
def import_transcript():
    """
    Import a transcript from parsed data.
    POST body should be JSON with transcript data.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        required_fields = ['id', 'url', 'title', 'primary_speaker', 'segments']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return jsonify({'error': f'Missing required fields: {missing}'}), 400
        
        transcript_id = insert_transcript(
            transcript_id=data['id'],
            url=data['url'],
            title=data['title'],
            primary_speaker=data['primary_speaker'],
            event_type=data.get('event_type', 'Unknown'),
            event_date=data.get('event_date', ''),
            location=data.get('location', ''),
            segments=data['segments'],
            topics=data.get('topics'),
            entities=data.get('entities'),
            raw_html=data.get('raw_html')
        )
        
        return jsonify({
            'success': True,
            'transcript_id': transcript_id,
            'segments_count': len(data['segments'])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import/bulk', methods=['POST'])
def import_bulk():
    """
    Import multiple transcripts at once.
    POST body should be JSON array of transcript data.
    """
    try:
        data = request.get_json()
        
        if not data or not isinstance(data, list):
            return jsonify({'error': 'Expected JSON array of transcripts'}), 400
        
        results = []
        for transcript in data:
            try:
                transcript_id = insert_transcript(
                    transcript_id=transcript['id'],
                    url=transcript['url'],
                    title=transcript['title'],
                    primary_speaker=transcript['primary_speaker'],
                    event_type=transcript.get('event_type', 'Unknown'),
                    event_date=transcript.get('event_date', ''),
                    location=transcript.get('location', ''),
                    segments=transcript['segments'],
                    topics=transcript.get('topics'),
                    entities=transcript.get('entities')
                )
                results.append({'id': transcript_id, 'success': True})
            except Exception as e:
                results.append({'id': transcript.get('id', 'unknown'), 'success': False, 'error': str(e)})
        
        success_count = sum(1 for r in results if r['success'])
        
        return jsonify({
            'total': len(data),
            'success': success_count,
            'failed': len(data) - success_count,
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Catch-all route for SPA
@app.route('/<path:path>')
def catch_all(path):
    """Serve static files or fall back to index.html for SPA routing."""
    file_path = Path(app.static_folder) / path
    if file_path.exists():
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    print(f"Starting Mention Markets API server on port {port}")
    print(f"Database: {DATABASE_PATH}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
