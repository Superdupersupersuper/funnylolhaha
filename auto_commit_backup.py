#!/usr/bin/env python3
"""
Auto-commit JSON backups to git after export
This ensures backups are always saved to the repository
"""

import os
import subprocess
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)

def auto_commit_backups():
    """Automatically commit backup files to git"""
    try:
        backup_dir = 'data/json_backups'
        
        # Check if there are any JSON files to commit
        result = subprocess.run(
            ['git', 'status', '--porcelain', backup_dir],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.stdout.strip():
            logging.info(f"📝 Found uncommitted backups, committing...")
            
            # Add backup files
            subprocess.run(['git', 'add', backup_dir], check=True)
            
            # Commit
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            subprocess.run(
                ['git', 'commit', '-m', f'Auto-backup: {timestamp}'],
                check=True
            )
            
            logging.info("✅ Backup committed to git")
            return True
        else:
            logging.info("ℹ️ No new backups to commit")
            return False
            
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Git command failed: {e}")
        return False
    except Exception as e:
        logging.error(f"❌ Auto-commit failed: {e}")
        return False

if __name__ == '__main__':
    auto_commit_backups()

