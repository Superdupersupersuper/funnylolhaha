#!/usr/bin/env python3
"""
One-time setup script for the GitHub-backed transcript store.

What it does:
  1. Creates a private GitHub repo for transcript storage (if it doesn't exist)
  2. Initialises the repo with transcripts_store/index.json
  3. Sets the required env vars on the Render web service
  4. (Optionally) migrates existing SQLite transcripts into the GitHub store
  5. Triggers a Render redeploy so the new env vars take effect

Usage:
  export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
  python3 setup_github_store.py

Required env vars:
  GITHUB_TOKEN        – GitHub Personal Access Token (classic with `repo` scope
                        OR fine-grained with Contents + Administration read/write)
  RENDER_API_KEY      – Render API key  (defaults to the key in render_cli.py)

Optional env vars:
  GITHUB_STORE_REPO   – e.g. "Superdupersupersuper/mm-transcripts"
                        If omitted the script will create a new private repo
                        named "mm-transcripts" under the token owner.
"""

import os
import sys
import json
import time
import base64
import sqlite3
import logging
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ---------- configuration ----------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy")
RENDER_SERVICE_ID = "srv-d694bsjuibrs739aiib0"
GITHUB_BRANCH = "main"
STORE_PREFIX = "transcripts_store"

# Optional: explicit repo name
GITHUB_STORE_REPO = os.environ.get("GITHUB_STORE_REPO", "")

_script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_script_dir, "data", "transcripts.db")


def gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def render_headers():
    return {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# ---------- Step 1: ensure private repo exists ----------

def get_github_username():
    r = requests.get("https://api.github.com/user", headers=gh_headers())
    r.raise_for_status()
    return r.json()["login"]


def create_private_repo(owner, name):
    """Create a private repo if it doesn't already exist. Returns 'owner/name'."""
    repo_full = f"{owner}/{name}"
    # Check if exists
    r = requests.get(f"https://api.github.com/repos/{repo_full}", headers=gh_headers())
    if r.status_code == 200:
        logging.info(f"✅ Repo {repo_full} already exists")
        return repo_full

    logging.info(f"📦 Creating private repo {name}...")
    r = requests.post("https://api.github.com/user/repos", headers=gh_headers(), json={
        "name": name,
        "private": True,
        "auto_init": True,  # creates a README so the default branch exists
        "description": "Transcript storage for MentionMarkets (auto-managed)",
    })
    r.raise_for_status()
    logging.info(f"✅ Created repo {repo_full}")
    time.sleep(2)  # give GitHub a moment to initialise
    return repo_full


# ---------- Step 2: initialise index.json ----------

def init_store(repo):
    """Create transcripts_store/index.json if it doesn't exist."""
    path = f"{STORE_PREFIX}/index.json"
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=gh_headers(), params={"ref": GITHUB_BRANCH})
    if r.status_code == 200:
        logging.info(f"✅ {path} already exists in {repo}")
        return

    logging.info(f"📦 Creating {path} in {repo}...")
    content = base64.b64encode(json.dumps([], indent=2).encode()).decode()
    r = requests.put(url, headers=gh_headers(), json={
        "message": "Initialise transcript store",
        "content": content,
        "branch": GITHUB_BRANCH,
    })
    r.raise_for_status()
    logging.info(f"✅ {path} created")


# ---------- Step 3: set Render env vars ----------

def set_render_env_vars(repo):
    """Set TRANSCRIPT_STORE, GITHUB_TOKEN, GITHUB_REPO, etc. on the Render service."""
    env_vars = [
        {"key": "TRANSCRIPT_STORE", "value": "github"},
        {"key": "GITHUB_TOKEN", "value": GITHUB_TOKEN},
        {"key": "GITHUB_REPO", "value": repo},
        {"key": "GITHUB_BRANCH", "value": GITHUB_BRANCH},
        {"key": "GITHUB_STORE_PREFIX", "value": STORE_PREFIX},
    ]

    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars"

    # Fetch current env vars
    r = requests.get(url, headers=render_headers())
    r.raise_for_status()
    existing = {ev["envVar"]["key"]: ev["envVar"] for ev in r.json()}

    for ev in env_vars:
        key = ev["key"]
        if key in existing:
            # Update
            logging.info(f"  🔄 Updating {key}")
            r = requests.put(
                f"{url}/{key}",
                headers=render_headers(),
                json={"value": ev["value"]},
            )
        else:
            # Create
            logging.info(f"  ➕ Creating {key}")
            r = requests.put(
                f"{url}/{key}",
                headers=render_headers(),
                json={"value": ev["value"]},
            )
        r.raise_for_status()

    logging.info("✅ Render env vars configured")


# ---------- Step 4 (optional): migrate SQLite data ----------

def migrate_sqlite_to_github(repo):
    """Copy any transcripts from the local SQLite DB into the GitHub store."""
    if not os.path.exists(DB_PATH):
        logging.info("ℹ️  No local SQLite database found – skipping migration")
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) as cnt FROM transcripts")
        count = cursor.fetchone()["cnt"]
    except Exception:
        logging.info("ℹ️  No transcripts table – skipping migration")
        conn.close()
        return 0

    if count == 0:
        logging.info("ℹ️  SQLite database is empty – skipping migration")
        conn.close()
        return 0

    logging.info(f"📦 Migrating {count} transcripts from SQLite to GitHub...")

    # Also check for json backup
    json_backup = os.path.join(_script_dir, "data", "json_backups", "transcripts_latest.json")
    transcripts_to_migrate = []

    if os.path.exists(json_backup):
        logging.info(f"  Using JSON backup: {json_backup}")
        with open(json_backup, "r") as f:
            data = json.load(f)
        if isinstance(data, dict) and "transcripts" in data:
            transcripts_to_migrate = data["transcripts"]
        elif isinstance(data, list):
            transcripts_to_migrate = data
    
    if not transcripts_to_migrate:
        # Fall back to reading from SQLite directly
        cursor.execute("PRAGMA table_info(transcripts)")
        columns = [col[1] for col in cursor.fetchall()]
        text_col = 'full_dialogue' if 'full_dialogue' in columns else 'full_text'
        
        cursor.execute(f"SELECT * FROM transcripts ORDER BY date DESC")
        rows = cursor.fetchall()
        
        for row in rows:
            speakers_raw = []
            if row['speakers_json']:
                try:
                    speakers_raw = json.loads(row['speakers_json'])
                except:
                    pass
            
            t = {
                'title': row['title'],
                'date': row['date'],
                'speech_type': row['speech_type'],
                'location': row.get('location', '') or '',
                'url': row['url'],
                'word_count': row['word_count'] or 0,
                'speech_duration_seconds': row.get('speech_duration_seconds', 0) or 0,
                'full_dialogue': row[text_col] if text_col in columns else '',
                'speakers': speakers_raw,
                'primary_speaker': row.get('primary_speaker', '') or '',
            }
            transcripts_to_migrate.append(t)

    conn.close()

    if not transcripts_to_migrate:
        logging.info("ℹ️  No transcripts found to migrate")
        return 0

    # Now push each transcript into GitHub store
    from github_store import GitHubJsonStore
    os.environ["GITHUB_TOKEN"] = GITHUB_TOKEN
    os.environ["GITHUB_REPO"] = repo
    os.environ["GITHUB_BRANCH"] = GITHUB_BRANCH
    os.environ["GITHUB_STORE_PREFIX"] = STORE_PREFIX

    # Re-import to pick up new env vars
    import importlib
    import github_store as gs_module
    importlib.reload(gs_module)
    store = gs_module.GitHubJsonStore()

    migrated = 0
    for t in transcripts_to_migrate:
        try:
            tid = store.create_transcript(t)
            logging.info(f"  ✅ Migrated: {t.get('title', 'untitled')} → ID {tid}")
            migrated += 1
            time.sleep(0.5)  # rate limiting
        except Exception as e:
            logging.error(f"  ❌ Failed: {t.get('title', 'untitled')} – {e}")

    logging.info(f"✅ Migration complete: {migrated}/{len(transcripts_to_migrate)} transcripts")
    return migrated


# ---------- Step 5: trigger redeploy ----------

def trigger_redeploy():
    """Trigger a new deploy on Render."""
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys"
    r = requests.post(url, headers=render_headers(), json={"clearCache": "do_not_clear"})
    r.raise_for_status()
    deploy_id = r.json().get("id", "unknown")
    logging.info(f"🚀 Deploy triggered: {deploy_id}")
    return deploy_id


# ---------- main ----------

def main():
    if not GITHUB_TOKEN:
        print("\n❌ GITHUB_TOKEN is required.")
        print("\nTo create one:")
        print("  1. Go to https://github.com/settings/tokens")
        print("  2. Generate new token (classic) with 'repo' scope")
        print("  3. export GITHUB_TOKEN='ghp_your_token_here'")
        print("  4. Re-run this script")
        sys.exit(1)

    if not RENDER_API_KEY:
        print("\n❌ RENDER_API_KEY is required.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("🔧 GitHub-Backed Transcript Store Setup")
    print("=" * 60)

    # Step 1: Ensure repo
    if GITHUB_STORE_REPO:
        repo = GITHUB_STORE_REPO
        logging.info(f"Using specified repo: {repo}")
    else:
        owner = get_github_username()
        repo = create_private_repo(owner, "mm-transcripts")

    # Step 2: Initialise store
    init_store(repo)

    # Step 3: Render env vars
    logging.info("\n📦 Configuring Render env vars...")
    set_render_env_vars(repo)

    # Step 4: Migrate
    logging.info("\n📦 Checking for data to migrate...")
    migrate_sqlite_to_github(repo)

    # Step 5: Redeploy
    logging.info("\n🚀 Triggering Render redeploy...")
    trigger_redeploy()

    print("\n" + "=" * 60)
    print("✅ Setup complete!")
    print(f"   Repo:     {repo}")
    print(f"   Branch:   {GITHUB_BRANCH}")
    print(f"   Prefix:   {STORE_PREFIX}")
    print(f"   Store:    TRANSCRIPT_STORE=github")
    print("\n   The Render service will redeploy with the new configuration.")
    print("   After deploy, visit /api/store-status to verify.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

