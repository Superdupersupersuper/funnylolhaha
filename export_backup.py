#!/usr/bin/env python3
"""
Export all transcripts to JSON backup files
This ensures data is never lost, even without persistent disk
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.environ.get('DATABASE_PATH', 'data/transcripts.db')
BACKUP_DIR = 'data/json_backups'

def export_all_transcripts():
    """Export all transcripts to a timestamped JSON file"""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        if not os.path.exists(DB_PATH):
            print(f"⚠️ Database not found at {DB_PATH}")
            return None
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, title, date, speech_type, location, url, 
                   word_count, trump_word_count, speech_duration_seconds,
                   full_dialogue, speakers_json, primary_speaker
            FROM transcripts
            ORDER BY date DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        if len(rows) == 0:
            print("⚠️ No transcripts to export")
            return None
        
        # Convert to list of dicts
        transcripts = []
        for row in rows:
            transcript = dict(row)
            # Parse JSON fields
            if transcript['speakers_json']:
                transcript['speakers'] = json.loads(transcript['speakers_json'])
                del transcript['speakers_json']
            transcripts.append(transcript)
        
        # Create timestamped backup file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'transcripts_backup_{timestamp}.json'
        filepath = os.path.join(BACKUP_DIR, filename)
        
        # Write backup
        with open(filepath, 'w') as f:
            json.dump({
                'exported_at': datetime.now().isoformat(),
                'count': len(transcripts),
                'transcripts': transcripts
            }, f, indent=2)
        
        # Also write to a "latest" file for easy access
        latest_path = os.path.join(BACKUP_DIR, 'transcripts_latest.json')
        with open(latest_path, 'w') as f:
            json.dump({
                'exported_at': datetime.now().isoformat(),
                'count': len(transcripts),
                'transcripts': transcripts
            }, f, indent=2)
        
        print(f"✅ Exported {len(transcripts)} transcripts to:")
        print(f"   {filepath}")
        print(f"   {latest_path}")
        
        return filepath
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def import_from_backup(filepath):
    """Import transcripts from a JSON backup file"""
    try:
        if not os.path.exists(filepath):
            print(f"❌ Backup file not found: {filepath}")
            return False
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        transcripts = data.get('transcripts', [])
        if len(transcripts) == 0:
            print("⚠️ No transcripts in backup file")
            return False
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        imported = 0
        for t in transcripts:
            # Convert speakers list back to JSON
            speakers_json = json.dumps(t.get('speakers', []))
            
            cursor.execute("""
                INSERT OR REPLACE INTO transcripts (
                    id, title, date, speech_type, location, url,
                    word_count, trump_word_count, speech_duration_seconds,
                    full_dialogue, speakers_json, primary_speaker
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get('id'),
                t.get('title'),
                t.get('date'),
                t.get('speech_type'),
                t.get('location', ''),
                t.get('url'),
                t.get('word_count', 0),
                t.get('trump_word_count', 0),
                t.get('speech_duration_seconds', 0),
                t.get('full_dialogue', ''),
                speakers_json,
                t.get('primary_speaker')
            ))
            imported += 1
        
        conn.commit()
        conn.close()
        
        print(f"✅ Imported {imported} transcripts from backup")
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 export_backup.py export          - Export all transcripts to JSON")
        print("  python3 export_backup.py import <file>   - Import transcripts from JSON backup")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'export':
        filepath = export_all_transcripts()
        if filepath:
            print(f"\n✅ Success! Backup saved.")
        else:
            print(f"\n❌ Export failed")
            sys.exit(1)
    
    elif command == 'import':
        if len(sys.argv) < 3:
            # Try to import from latest backup
            latest_path = os.path.join(BACKUP_DIR, 'transcripts_latest.json')
            if os.path.exists(latest_path):
                print(f"Using latest backup: {latest_path}")
                filepath = latest_path
            else:
                print("❌ Please specify backup file")
                sys.exit(1)
        else:
            filepath = sys.argv[2]
        
        if import_from_backup(filepath):
            print("✅ Import successful")
        else:
            print("❌ Import failed")
            sys.exit(1)
    
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)

