#!/usr/bin/env python3
"""
Fix existing transcripts in the database:
- Clean titles (remove "otter ai" artifacts)
- Update primary_speaker format ("Zohran Mamdani" -> "Mamdani")
"""

import sqlite3
import os
import re
import backup_database

DB_PATH = os.environ.get('DATABASE_PATH', 'data/transcripts.db')

def clean_title(title):
    """Remove 'otter ai' / 'otter.ai' / 'Transcribed by...' artifacts from titles."""
    if not title:
        return title
    title = re.sub(r'\s*[-–—]\s*Transcribed by\s+(?:https?://)?otter\.?ai\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*Transcribed by\s+(?:https?://)?otter\.?ai\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*otter\.?ai\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*otter\s+ai\s*$', '', title, flags=re.IGNORECASE)
    return title.strip()

def normalize_primary_speaker(speaker):
    """Normalize primary speaker names to short form"""
    if not speaker:
        return speaker
    
    s = speaker.strip()
    if 'mamdani' in s.lower():
        return 'Mamdani'
    elif 'hochul' in s.lower():
        return 'Hochul'
    elif 'trump' in s.lower():
        return 'Trump'
    elif 'vance' in s.lower():
        return 'JD Vance'
    
    return s

def fix_transcripts():
    """Fix all transcripts in the database"""
    # Create backup first
    print("📦 Creating backup before making changes...")
    backup_path = backup_database.create_backup(reason='pre_fix_transcripts')
    if backup_path:
        print(f"✅ Backup created: {backup_path}")
    else:
        print("❌ Backup failed - aborting")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all transcripts
        cursor.execute("SELECT id, title, primary_speaker FROM transcripts")
        rows = cursor.fetchall()
        
        print(f"\n🔍 Found {len(rows)} transcripts to check\n")
        
        fixed_count = 0
        for row in rows:
            transcript_id = row['id']
            old_title = row['title']
            old_speaker = row['primary_speaker']
            
            new_title = clean_title(old_title)
            new_speaker = normalize_primary_speaker(old_speaker) if old_speaker else old_speaker
            
            if new_title != old_title or new_speaker != old_speaker:
                cursor.execute(
                    "UPDATE transcripts SET title = ?, primary_speaker = ? WHERE id = ?",
                    (new_title, new_speaker, transcript_id)
                )
                fixed_count += 1
                
                print(f"✓ Fixed transcript #{transcript_id}")
                if new_title != old_title:
                    print(f"  Title: '{old_title}' -> '{new_title}'")
                if new_speaker != old_speaker:
                    print(f"  Speaker: '{old_speaker}' -> '{new_speaker}'")
                print()
        
        conn.commit()
        conn.close()
        
        print(f"\n✅ Fixed {fixed_count} transcripts")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("🔧 Fixing existing transcripts...\n")
    if fix_transcripts():
        print("\n✅ All done!")
    else:
        print("\n❌ Failed")

