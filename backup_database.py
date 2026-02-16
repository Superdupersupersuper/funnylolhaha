#!/usr/bin/env python3
"""
Database Backup Utility for MentionMarkets
Automatically creates timestamped backups before any destructive operations
"""

import os
import shutil
import sqlite3
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_PATH = os.environ.get('DATABASE_PATH', 'data/transcripts.db')
BACKUP_DIR = os.environ.get('BACKUP_DIR', 'data/backups')

def create_backup(reason='manual'):
    """
    Create a timestamped backup of the database
    
    Args:
        reason: String describing why the backup was created
        
    Returns:
        Path to the backup file, or None if backup failed
    """
    try:
        # Ensure backup directory exists
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        # Check if database exists
        if not os.path.exists(DB_PATH):
            logging.warning(f"⚠️ Database not found at {DB_PATH}")
            return None
        
        # Get database size
        db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        
        # Create timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create backup filename
        backup_filename = f'transcripts_backup_{timestamp}_{reason}.db'
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        logging.info(f"📦 Creating backup: {backup_filename} ({db_size_mb:.2f} MB)")
        
        # Use SQLite backup API for safe backup (handles locks)
        try:
            source = sqlite3.connect(DB_PATH)
            dest = sqlite3.connect(backup_path)
            source.backup(dest)
            dest.close()
            source.close()
            logging.info(f"✅ Backup created successfully: {backup_path}")
        except Exception as e:
            # Fallback to file copy if backup API fails
            logging.warning(f"SQLite backup failed, using file copy: {e}")
            shutil.copy2(DB_PATH, backup_path)
            logging.info(f"✅ Backup created via file copy: {backup_path}")
        
        # Verify backup
        if os.path.exists(backup_path):
            backup_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            logging.info(f"✓ Backup verified: {backup_size_mb:.2f} MB")
            
            # Clean old backups (keep last 10)
            cleanup_old_backups(keep=10)
            
            return backup_path
        else:
            logging.error("❌ Backup file not found after creation")
            return None
            
    except Exception as e:
        logging.error(f"❌ Backup failed: {e}", exc_info=True)
        return None

def cleanup_old_backups(keep=10):
    """Remove old backups, keeping only the most recent N"""
    try:
        if not os.path.exists(BACKUP_DIR):
            return
        
        # Get all backup files
        backups = [f for f in os.listdir(BACKUP_DIR) if f.startswith('transcripts_backup_') and f.endswith('.db')]
        
        if len(backups) <= keep:
            return
        
        # Sort by modification time (oldest first)
        backups.sort(key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)))
        
        # Remove oldest backups
        to_remove = backups[:-keep]
        for filename in to_remove:
            filepath = os.path.join(BACKUP_DIR, filename)
            os.remove(filepath)
            logging.info(f"🗑️ Removed old backup: {filename}")
        
        logging.info(f"✓ Cleanup complete: kept {keep} most recent backups")
        
    except Exception as e:
        logging.error(f"❌ Cleanup failed: {e}")

def list_backups():
    """List all available backups"""
    try:
        if not os.path.exists(BACKUP_DIR):
            return []
        
        backups = []
        for filename in os.listdir(BACKUP_DIR):
            if filename.startswith('transcripts_backup_') and filename.endswith('.db'):
                filepath = os.path.join(BACKUP_DIR, filename)
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                backups.append({
                    'filename': filename,
                    'path': filepath,
                    'size_mb': round(size_mb, 2),
                    'created': mtime.strftime('%Y-%m-%d %H:%M:%S')
                })
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda b: b['created'], reverse=True)
        return backups
        
    except Exception as e:
        logging.error(f"❌ Failed to list backups: {e}")
        return []

def restore_backup(backup_path):
    """
    Restore database from a backup
    
    Args:
        backup_path: Path to the backup file
        
    Returns:
        True if restore succeeded, False otherwise
    """
    try:
        if not os.path.exists(backup_path):
            logging.error(f"❌ Backup file not found: {backup_path}")
            return False
        
        # Create a backup of current database before restoring
        logging.info("📦 Creating safety backup of current database...")
        create_backup(reason='pre_restore')
        
        logging.info(f"🔄 Restoring from backup: {backup_path}")
        
        # Copy backup to database location
        shutil.copy2(backup_path, DB_PATH)
        
        # Verify restore
        if os.path.exists(DB_PATH):
            size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
            logging.info(f"✅ Database restored successfully ({size_mb:.2f} MB)")
            return True
        else:
            logging.error("❌ Database file not found after restore")
            return False
            
    except Exception as e:
        logging.error(f"❌ Restore failed: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 backup_database.py create [reason]    - Create a backup")
        print("  python3 backup_database.py list               - List all backups")
        print("  python3 backup_database.py restore <filename> - Restore from backup")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'create':
        reason = sys.argv[2] if len(sys.argv) > 2 else 'manual'
        backup_path = create_backup(reason)
        if backup_path:
            print(f"✅ Backup created: {backup_path}")
        else:
            print("❌ Backup failed")
            sys.exit(1)
    
    elif command == 'list':
        backups = list_backups()
        if backups:
            print(f"\n📦 Found {len(backups)} backups:\n")
            for b in backups:
                print(f"  {b['filename']}")
                print(f"    Created: {b['created']}")
                print(f"    Size: {b['size_mb']} MB\n")
        else:
            print("No backups found")
    
    elif command == 'restore':
        if len(sys.argv) < 3:
            print("❌ Please specify backup filename")
            sys.exit(1)
        
        backup_filename = sys.argv[2]
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        if restore_backup(backup_path):
            print("✅ Restore successful")
        else:
            print("❌ Restore failed")
            sys.exit(1)
    
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)

