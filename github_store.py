#!/usr/bin/env python3
"""
GitHub-backed JSON store for transcripts.

Uses the GitHub Contents API to persist transcript data in a private repo,
so deploys on Render's free tier never lose data.

Storage layout:
  {prefix}/index.json                   – array of transcript metadata
  {prefix}/transcripts/{id}.json        – full transcript object
"""

import os
import json
import time
import base64
import logging
import requests
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration (all from environment)
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")          # e.g. "owner/repo"
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_STORE_PREFIX = os.environ.get("GITHUB_STORE_PREFIX", "transcripts_store")

API_BASE = "https://api.github.com"

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _contents_url(path: str) -> str:
    """Build the URL for the Contents API."""
    return f"{API_BASE}/repos/{GITHUB_REPO}/contents/{path}"


def _get_file(path: str):
    """
    GET a file from the repo.  Returns (content_dict, sha) or (None, None).
    content_dict is the parsed JSON content of the file.
    """
    url = _contents_url(path)
    r = requests.get(url, headers=_headers(), params={"ref": GITHUB_BRANCH})
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    blob = r.json()
    raw = base64.b64decode(blob["content"])
    return json.loads(raw), blob["sha"]


def _put_file(path: str, content, message: str, sha: str = None):
    """
    Create or update a file.  `content` is a Python object that will be
    JSON-serialised.  `sha` is required for updates.
    """
    url = _contents_url(path)
    encoded = base64.b64encode(json.dumps(content, indent=2).encode()).decode()
    body = {
        "message": message,
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=_headers(), json=body)
    r.raise_for_status()
    return r.json()


def _delete_file(path: str, sha: str, message: str):
    """Delete a file from the repo."""
    url = _contents_url(path)
    body = {
        "message": message,
        "sha": sha,
        "branch": GITHUB_BRANCH,
    }
    r = requests.delete(url, headers=_headers(), json=body)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _index_path() -> str:
    return f"{GITHUB_STORE_PREFIX}/index.json"


def _transcript_path(tid: int) -> str:
    return f"{GITHUB_STORE_PREFIX}/transcripts/{tid}.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class GitHubJsonStore:
    """
    Transcript store backed by GitHub Contents API.

    The index is a list of metadata dicts (no full_dialogue).
    Each transcript's full data lives in its own file.
    """

    def __init__(self):
        self.enabled = bool(GITHUB_TOKEN and GITHUB_REPO)
        if not self.enabled:
            logging.warning("GitHubJsonStore: GITHUB_TOKEN or GITHUB_REPO not set – store disabled")

    # ---- index ----------------------------------------------------------

    def load_index(self):
        """Return (list_of_metadata, sha) or ([], None) if missing."""
        try:
            data, sha = _get_file(_index_path())
            if data is None:
                return [], None
            # data is the list itself (or wrapped in a dict with key 'transcripts')
            if isinstance(data, dict) and "transcripts" in data:
                return data["transcripts"], sha
            if isinstance(data, list):
                return data, sha
            return [], sha
        except Exception as e:
            logging.error(f"GitHubJsonStore.load_index error: {e}")
            return [], None

    def save_index(self, index_list, sha=None):
        """Persist the index list to GitHub."""
        try:
            msg = f"Update index ({len(index_list)} transcripts)"
            _put_file(_index_path(), index_list, msg, sha=sha)
            logging.info(f"GitHubJsonStore: saved index with {len(index_list)} entries")
        except Exception as e:
            logging.error(f"GitHubJsonStore.save_index error: {e}")
            raise

    # ---- single transcript ----------------------------------------------

    def get_transcript(self, tid: int):
        """Return full transcript dict or None."""
        try:
            data, _sha = _get_file(_transcript_path(tid))
            return data
        except Exception as e:
            logging.error(f"GitHubJsonStore.get_transcript({tid}) error: {e}")
            return None

    def put_transcript(self, tid: int, payload: dict):
        """Create or update a transcript file."""
        path = _transcript_path(tid)
        try:
            # Check if file already exists (need sha to update)
            _existing, sha = _get_file(path)
            msg = f"{'Update' if sha else 'Add'} transcript {tid}"
            _put_file(path, payload, msg, sha=sha)
            logging.info(f"GitHubJsonStore: saved transcript {tid}")
        except Exception as e:
            logging.error(f"GitHubJsonStore.put_transcript({tid}) error: {e}")
            raise

    def delete_transcript(self, tid: int):
        """Delete a transcript file."""
        path = _transcript_path(tid)
        try:
            _existing, sha = _get_file(path)
            if sha:
                _delete_file(path, sha, f"Delete transcript {tid}")
                logging.info(f"GitHubJsonStore: deleted transcript {tid}")
            else:
                logging.warning(f"GitHubJsonStore: transcript {tid} not found for deletion")
        except Exception as e:
            logging.error(f"GitHubJsonStore.delete_transcript({tid}) error: {e}")
            raise

    # ---- bulk helpers ----------------------------------------------------

    def get_all_transcripts(self):
        """Load index + every transcript file.  Returns list of full dicts."""
        index, _sha = self.load_index()
        results = []
        for meta in index:
            tid = meta.get("id")
            full = self.get_transcript(tid)
            if full:
                results.append(full)
            else:
                # Return metadata-only as fallback
                results.append(meta)
        return results

    def create_transcript(self, payload: dict) -> int:
        """
        Assign an ID, save the transcript file, update the index.
        Returns the new ID.
        """
        # Generate unique ID
        tid = int(time.time() * 1000)
        index, idx_sha = self.load_index()
        existing_ids = {m.get("id") for m in index}
        while tid in existing_ids:
            tid += 1
        payload["id"] = tid

        # Save full transcript file
        self.put_transcript(tid, payload)

        # Build metadata entry (everything except full_dialogue)
        meta = {k: v for k, v in payload.items() if k != "full_dialogue"}
        index.append(meta)

        # Save updated index
        self.save_index(index, sha=idx_sha)

        return tid

    def update_transcript_in_store(self, tid: int, payload: dict):
        """
        Update an existing transcript: replace its file and update the index entry.
        """
        payload["id"] = tid

        # Save full transcript file
        self.put_transcript(tid, payload)

        # Update index entry
        index, idx_sha = self.load_index()
        meta = {k: v for k, v in payload.items() if k != "full_dialogue"}
        index = [m for m in index if m.get("id") != tid]
        index.append(meta)
        # Sort by date descending
        index.sort(key=lambda m: m.get("date", ""), reverse=True)
        self.save_index(index, sha=idx_sha)

    def delete_transcript_from_store(self, tid: int):
        """Delete transcript file and remove from index."""
        self.delete_transcript(tid)

        index, idx_sha = self.load_index()
        index = [m for m in index if m.get("id") != tid]
        self.save_index(index, sha=idx_sha)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_store_instance = None

def get_github_store() -> GitHubJsonStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = GitHubJsonStore()
    return _store_instance

