import json
import sqlite3
import os
import urllib.request
import zipfile

DB_PATH = '/tmp/transcripts.db'
DB_URL = 'https://github.com/Superdupersupersuper/funnylolhaha/releases/download/v2.0/transcripts.db.zip'

def ensure_database():
    """Download and extract database if not present"""
    if not os.path.exists(DB_PATH):
        print(f"Downloading database from {DB_URL}...")
        try:
            zip_path = '/tmp/transcripts.db.zip'
            urllib.request.urlretrieve(DB_URL, zip_path)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall('/tmp')

            extracted_path = '/tmp/data/transcripts.db'
            if os.path.exists(extracted_path):
                os.rename(extracted_path, DB_PATH)

            os.remove(zip_path)
            if os.path.exists('/tmp/data'):
                os.rmdir('/tmp/data')

            print(f"Database ready at {DB_PATH}")
        except Exception as e:
            print(f"Error: {e}")
            raise

def handler(event, context):
    """Netlify function handler for stats endpoint"""
    try:
        ensure_database()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM transcripts")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(date) as min, MAX(date) as max FROM transcripts WHERE date LIKE '____-__-__'")
        dates = cursor.fetchone()

        cursor.execute("SELECT DISTINCT speech_type FROM transcripts ORDER BY speech_type")
        types = [row[0] for row in cursor.fetchall()]

        conn.close()

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'totalTranscripts': total,
                'dateRange': {'min': dates[0], 'max': dates[1]},
                'speechTypes': types
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
