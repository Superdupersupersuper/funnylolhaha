#!/usr/bin/env python3
"""
Clean database - Remove all Trump speeches and old transcripts
Keep only recent Mamdani uploads
"""
import sqlite3
import os

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'transcripts.db')

def clean_database():
    """Remove all Trump speeches and keep only recent Mamdani transcripts"""
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get current counts
    cursor.execute("SELECT COUNT(*) FROM transcripts")
    total_before = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM transcripts 
        WHERE title LIKE '%Trump%' OR title LIKE '%trump%'
           OR url LIKE '%trump%'
    """)
    trump_count = cursor.fetchone()[0]
    
    print(f"\n📊 Current Database Status:")
    print(f"   Total transcripts: {total_before}")
    print(f"   Trump transcripts: {trump_count}")
    print()
    
    # Get Mamdani transcripts to keep
    cursor.execute("""
        SELECT id, title, date FROM transcripts
        WHERE title LIKE '%Mamdani%' OR title LIKE '%mamdani%'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    mamdani_transcripts = cursor.fetchall()
    
    print("📝 Mamdani transcripts found:")
    for tid, title, date in mamdani_transcripts:
        print(f"   {tid}: {title} ({date})")
    print()
    
    # Confirmation from command line argument
    import sys
    if '--confirm' not in sys.argv:
        print("⚠️  This will delete ALL transcripts except recent Mamdani entries.")
        print("   Run with --confirm flag to proceed: python3 clean_database.py --confirm")
        conn.close()
        return
    
    print("⏳ Proceeding with deletion...")
    
    # Keep only admin-uploaded Mamdani transcripts
    # (These have URLs starting with 'admin-upload')
    cursor.execute("""
        DELETE FROM transcripts
        WHERE url NOT LIKE 'admin-upload%Mamdani%'
           OR url NOT LIKE 'admin-upload%mamdani%'
    """)
    
    deleted_count = cursor.rowcount
    
    # Actually, let's be more precise - keep only the ones with Mamdani in title
    # and were recently uploaded
    cursor.execute("""
        DELETE FROM transcripts
        WHERE (title NOT LIKE '%Mamdani%' AND title NOT LIKE '%mamdani%')
           OR url NOT LIKE 'admin-upload%'
    """)
    
    deleted_count = cursor.rowcount
    
    conn.commit()
    
    # Get new counts
    cursor.execute("SELECT COUNT(*) FROM transcripts")
    total_after = cursor.fetchone()[0]
    
    print(f"\n✅ Database cleaned!")
    print(f"   Deleted: {deleted_count} transcripts")
    print(f"   Remaining: {total_after} transcripts")
    
    # Show what remains
    cursor.execute("SELECT id, title, date, word_count FROM transcripts ORDER BY created_at DESC")
    remaining = cursor.fetchall()
    
    print(f"\n📋 Remaining transcripts:")
    for tid, title, date, wc in remaining:
        print(f"   {tid}: {title} ({date}) - {wc} words")
    
    conn.close()
    print("\n✨ Done!")

if __name__ == '__main__':
    clean_database()

