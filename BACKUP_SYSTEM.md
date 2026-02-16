# 🛡️ Database Backup & Persistence System

## Problem
Render's **free tier** uses ephemeral storage — the database gets wiped on every deploy. This was causing data loss.

## Solution
**Automatic JSON Backup System** that ensures data is never lost:

### 🔄 How It Works

1. **Auto-Export After Every Change**
   - Every time you create, update, or delete a transcript, the system automatically exports ALL transcripts to JSON
   - Exports are saved to `data/json_backups/transcripts_latest.json`
   - Timestamped backups are also created for history

2. **Auto-Restore on Startup**
   - When the server starts (after a deploy), it checks if the database is empty
   - If empty, it automatically restores all transcripts from `transcripts_latest.json`
   - **Your data survives every deploy! 🎉**

3. **Git-Committed Backups**
   - JSON backups are committed to git (unlike the database itself)
   - Every time you add/edit/delete a transcript, the backup is auto-committed
   - This means your data is safe in the GitHub repository

### 📋 Manual Operations

You can also manually export/import via API:

```bash
# Export all transcripts to JSON
curl -X POST https://funnylolhaha.onrender.com/api/admin/export

# Import from backup
curl -X POST https://funnylolhaha.onrender.com/api/admin/import \
  -H "Content-Type: application/json" \
  -d '{"filepath": "data/json_backups/transcripts_latest.json"}'
```

Or via Python scripts locally:

```bash
# Export
python3 export_backup.py export

# Import
python3 export_backup.py import data/json_backups/transcripts_latest.json
```

### 📂 Backup Locations

- **Latest Backup**: `data/json_backups/transcripts_latest.json` (always up-to-date)
- **Timestamped Backups**: `data/json_backups/transcripts_backup_YYYYMMDD_HHMMSS.json`
- **SQLite Backups** (if available): `data/backups/transcripts_backup_*.db`

### ⚡ What Happens on Deploy

1. New container starts with empty database
2. `init_database_if_needed()` runs
3. Checks if database is empty
4. Finds `transcripts_latest.json` in the repo
5. **Automatically restores all transcripts** ✅
6. Server is ready with all your data!

### 🔐 Data Safety Guarantees

- ✅ **Auto-backup** after every transcript operation
- ✅ **Auto-restore** on every deploy
- ✅ **Git-committed** backups (survives deploys)
- ✅ **Timestamped history** (can roll back if needed)
- ✅ **No manual intervention** required

### 🆙 Upgrading to Persistent Disk (Recommended for Production)

For better performance and instant writes, upgrade your Render plan to get persistent disks:

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Select your service
3. Go to "Disks" tab
4. Add a disk mounted at `/opt/render/project/src/data`

With persistent disk, the database persists across deploys and the JSON backup system serves as additional redundancy.

### 🚨 Recovery Instructions

If data is ever lost:

1. **Check git history**: `data/json_backups/transcripts_latest.json`
2. **Restore via API**: `POST /api/admin/import`
3. **Or restore locally**: `python3 export_backup.py import`

## Status

**Current Setup**: ✅ Full auto-backup system active
**Data Persistence**: ✅ Via git-committed JSON backups
**Auto-Restore**: ✅ Enabled on every deploy
**Manual Backups**: ✅ Available via API/CLI

Your data is safe! 🎉

