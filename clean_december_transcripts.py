#!/usr/bin/env python3
"""
Cleanup script: Re-normalize December 2025 transcripts in database
This applies the normalization functions to existing corrupt transcripts
"""

import sqlite3
import sys
import re
import json
from typing import Tuple, Dict

# Import normalization functions
from rollcall_sync import normalize_speaker_label, strip_rollcall_artifacts

def normalize_existing_transcript(full_dialogue: str) -> Tuple[str, str, int, int, Dict]:
    """
    Normalize an existing transcript's full_dialogue text
    
    Args:
        full_dialogue: Raw transcript text from database
    
    Returns:
        (normalized_dialogue, speakers_json, word_count, trump_word_count, stats)
    """
    if not full_dialogue:
        return full_dialogue, '[]', 0, 0, {}
    
    stats = {
        'speaker_labels_normalized': 0,
        'timestamp_lines': 0,
        'rating_lines': 0,
        'signal_rating_blocks': 0,
        'boilerplate_lines': 0,
        'annotations_removed': 0
    }
    
    lines = full_dialogue.split('\n')
    cleaned_sections = []
    speakers = set()
    trump_word_count = 0
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty
        if not line:
            i += 1
            continue
        
        # Check if speaker line (has " 00" suffix or timestamp pattern follows)
        is_speaker = False
        clean_speaker = None
        
        # Pattern: "Name Name 00" or just "Name Name"
        if re.match(r'^[A-Z][a-zA-Z\s\.]+(\s+\d{1,2})?$', line):
            raw_speaker = line
            clean_speaker, was_modified = normalize_speaker_label(raw_speaker)
            if was_modified:
                stats['speaker_labels_normalized'] += 1
            is_speaker = True
        
        if is_speaker and clean_speaker:
            speakers.add(clean_speaker)
            i += 1
            
            # Skip timestamp line
            if i < len(lines) and re.match(r'^\d{1,2}:\d{2}-', lines[i]):
                stats['timestamp_lines'] += 1
                i += 1
            
            # Skip blank
            while i < len(lines) and not lines[i].strip():
                i += 1
            
            # Skip rating line
            if i < len(lines) and re.match(r'^(NO STRESSLENS|NO SIGNAL|MEDIUM|WEAK|STRONG)', lines[i]):
                stats['rating_lines'] += 1
                i += 1
            
            # Collect dialogue until next speaker
            dialogue_lines = []
            while i < len(lines):
                current_line = lines[i].strip()
                
                # Stop at next speaker
                if re.match(r'^[A-Z][a-zA-Z\s\.]+(\s+\d{1,2})?$', current_line):
                    break
                
                # Skip metadata
                if re.match(r'^\d{1,2}:\d{2}-', current_line):
                    stats['timestamp_lines'] += 1
                    i += 1
                    continue
                if re.match(r'^(NO STRESSLENS|NO SIGNAL|MEDIUM|WEAK|STRONG)', current_line):
                    stats['rating_lines'] += 1
                    i += 1
                    continue
                if not current_line:
                    i += 1
                    continue
                
                # This is dialogue
                dialogue_lines.append(current_line)
                i += 1
            
            # Clean and save
            if dialogue_lines:
                dialogue_text = ' '.join(dialogue_lines)
                # Remove annotations
                annotation_count = len(re.findall(r'\[(?:Inaudible|Laughter|Laughs|Audience|Crosstalk|Applause).*?\]', dialogue_text, re.IGNORECASE))
                stats['annotations_removed'] += annotation_count
                dialogue_text = re.sub(r'\[(?:Inaudible|Laughter|Laughs|Audience|Crosstalk|Applause).*?\]', '', dialogue_text, flags=re.IGNORECASE)
                dialogue_text = ' '.join(dialogue_text.split())  # Clean whitespace
                
                if dialogue_text:
                    cleaned_sections.append(f"{clean_speaker}\n{dialogue_text}\n")
                    if 'donald trump' in clean_speaker.lower() or clean_speaker.lower() == 'trump':
                        trump_word_count += len(dialogue_text.split())
        else:
            i += 1
    
    # Build output
    normalized_dialogue = '\n'.join(cleaned_sections)
    word_count = len(normalized_dialogue.split())
    speakers_json = json.dumps(sorted(list(speakers)))
    
    return normalized_dialogue, speakers_json, word_count, trump_word_count, stats

def clean_december_transcripts(db_path: str, dry_run: bool = False, quiet: bool = False):
    """
    Clean all December 2025 transcripts in the database
    
    Args:
        db_path: Path to transcripts.db
        dry_run: If True, show what would be changed but don't update
        quiet: If True, minimal output (for API calls)
    """
    def log(msg):
        if not quiet:
            print(msg)
    
    log("\n" + "="*80)
    log("DECEMBER 2025 TRANSCRIPT CLEANUP")
    log("="*80)
    log(f"Database: {db_path}")
    log(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will update database)'}")
    log("="*80 + "\n")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Find December 2025 transcripts
    cursor.execute("""
        SELECT id, title, date, url, full_dialogue, word_count
        FROM transcripts
        WHERE date >= '2025-12-01' AND date <= '2025-12-31'
        ORDER BY date DESC
    """)
    
    transcripts = cursor.fetchall()
    log(f"Found {len(transcripts)} December 2025 transcripts\n")
    
    total_stats = {
        'processed': 0,
        'updated': 0,
        'skipped_clean': 0,
        'speaker_labels_normalized': 0,
        'timestamp_lines': 0,
        'rating_lines': 0,
        'annotations_removed': 0
    }
    
    for row in transcripts:
        transcript_id, title, date, url, full_dialogue, old_word_count = row
        
        log(f"\n[{date}] {title[:60]}...")
        
        # Check if needs cleaning
        needs_cleaning = False
        if re.search(r'(Donald Trump|Trump)\s+\d{2}', full_dialogue or ''):
            needs_cleaning = True
            print(f"  ⚠️  Has speaker numeric suffixes")
        if re.search(r'NO SIGNAL|NO STRESSLENS|MEDIUM|WEAK', full_dialogue or ''):
            needs_cleaning = True
            print(f"  ⚠️  Has rating metadata")
        if re.search(r'\d{1,2}:\d{2}-\d{1,2}:\d{2}:\d{2}', full_dialogue or ''):
            needs_cleaning = True
            print(f"  ⚠️  Has timestamp lines")
        
        if not needs_cleaning:
            print(f"  ✅ Already clean, skipping")
            total_stats['skipped_clean'] += 1
            continue
        
        # Normalize
        log(f"  🔧 Normalizing...")
        normalized_dialogue, speakers_json, word_count, trump_word_count, norm_stats = \
            normalize_existing_transcript(full_dialogue)
        
        # Aggregate stats
        for key in norm_stats:
            if key in total_stats:
                total_stats[key] += norm_stats[key]
        
        log(f"  📊 Before: {old_word_count} words")
        log(f"  📊 After: {word_count} words")
        log(f"  📊 Normalized: {norm_stats['speaker_labels_normalized']} labels, " + 
              f"{norm_stats['timestamp_lines']} timestamps, " +
              f"{norm_stats['rating_lines']} ratings, " +
              f"{norm_stats['annotations_removed']} annotations")
        
        # Update database
        if not dry_run:
            cursor.execute("""
                UPDATE transcripts
                SET full_dialogue = ?,
                    speakers_json = ?,
                    word_count = ?,
                    trump_word_count = ?,
                    scraped_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (normalized_dialogue, speakers_json, word_count, trump_word_count, transcript_id))
            print(f"  ✅ Updated in database")
            total_stats['updated'] += 1
        else:
            print(f"  (would update in database)")
        
        total_stats['processed'] += 1
    
    if not dry_run:
        conn.commit()
        log(f"\n✅ Changes committed to database")
    else:
        log(f"\n(DRY RUN - no changes made)")
    
    conn.close()
    
    # Print summary
    print("\n" + "="*80)
    print("CLEANUP SUMMARY")
    print("="*80)
    print(f"Transcripts processed: {total_stats['processed']}")
    print(f"Transcripts updated: {total_stats['updated']}")
    print(f"Transcripts skipped (already clean): {total_stats['skipped_clean']}")
    print(f"\nNormalization totals:")
    print(f"  Speaker labels fixed: {total_stats['speaker_labels_normalized']}")
    print(f"  Timestamp lines removed: {total_stats['timestamp_lines']}")
    print(f"  Rating lines removed: {total_stats['rating_lines']}")
    print(f"  Annotations removed: {total_stats['annotations_removed']}")
    print("="*80 + "\n")

if __name__ == '__main__':
    db_path = '/Users/alexandermiron/Downloads/mention-markets/data/transcripts.db'
    
    # Check arguments
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
    
    if not dry_run:
        response = input("⚠️  This will UPDATE the database. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
    
    clean_december_transcripts(db_path, dry_run=dry_run)


