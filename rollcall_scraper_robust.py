#!/usr/bin/env python3
"""
ROBUST RollCall Scraper with Live Progress Dashboard
- Bulletproof error handling (won't crash)
- Auto-retry logic (3 attempts per transcript)
- Checkpointing (saves every 10 transcripts)
- Resume capability (can restart where it left off)
- Live progress webpage
- Rate limiting (polite delays)

IMPROVEMENTS (Phase 1 - Dec 2025):
- Shared selector fallback logic via scraper_utils.py
- Structured logging with levels
- Never writes empty transcripts without recording failure
- Comprehensive CSS selector list (15+ selectors)
- Multiple dialogue extraction strategies
"""

import time
import json
import sqlite3
import re
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

# Import shared scraper utilities
try:
    from scraper_utils import (
        DialogueExtractor, 
        build_dialogue_text, 
        validate_transcript_content,
        CONTENT_SELECTORS
    )
    HAS_SCRAPER_UTILS = True
except ImportError:
    HAS_SCRAPER_UTILS = False
    logging.warning("scraper_utils not available, using built-in extraction")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProgressTracker:
    """Tracks scraping progress and serves live dashboard"""

    def __init__(self):
        self.data = {
            'total': 0,
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'current_title': '',
            'current_url': '',
            'errors': [],
            'start_time': datetime.now().isoformat(),
            'last_update': datetime.now().isoformat(),
            'status': 'Starting...',
            'eta': 'Calculating...'
        }
        self.lock = threading.Lock()

    def update(self, **kwargs):
        """Thread-safe update of progress data"""
        with self.lock:
            self.data.update(kwargs)
            self.data['last_update'] = datetime.now().isoformat()
            self.save()

    def add_error(self, error_msg):
        """Add error to log"""
        with self.lock:
            self.data['errors'].append({
                'time': datetime.now().isoformat(),
                'message': error_msg
            })
            # Keep only last 50 errors
            self.data['errors'] = self.data['errors'][-50:]
            self.save()

    def save(self):
        """Save progress to JSON file"""
        with open('scraper_progress.json', 'w') as f:
            json.dump(self.data, f, indent=2)

    def get_data(self):
        """Get current progress data"""
        with self.lock:
            return self.data.copy()

class RobustRollCallScraper:
    """Production-ready scraper with all safety features"""

    def __init__(self):
        self.progress = ProgressTracker()
        self.db_path = 'data/transcripts_new.db'
        self.base_url = 'https://rollcall.com/factbase/trump/transcript/'
        self.max_retries = 3
        self.delay = 2  # Seconds between requests
        self.driver = None

    def init_database(self):
        """Initialize clean database"""
        os.makedirs('data', exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Drop old table if exists
        cursor.execute('DROP TABLE IF EXISTS transcripts')

        # Create new optimized schema
        cursor.execute('''
            CREATE TABLE transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                date DATE NOT NULL,
                speech_type TEXT NOT NULL,
                location TEXT,
                url TEXT UNIQUE NOT NULL,
                word_count INTEGER,
                trump_word_count INTEGER,
                speech_duration_seconds INTEGER,
                full_dialogue TEXT NOT NULL,
                speakers_json TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('CREATE INDEX idx_date ON transcripts(date)')
        cursor.execute('CREATE INDEX idx_url ON transcripts(url)')

        conn.commit()
        conn.close()
        print("✓ Database initialized")

    def init_driver(self):
        """Initialize Chrome driver with safety options"""
        try:
            options = Options()
            options.add_argument('--headless')  # Run in background
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            print("✓ Browser initialized")
            return True
        except Exception as e:
            self.progress.add_error(f"Failed to init driver: {str(e)}")
            return False

    def get_transcript_urls(self):
        """Get all transcript URLs from search page with infinite scroll

        Scrolls DOWN (newest to oldest) by setting sort="Newest" first,
        then scrolling until we reach Jan 1, 2023 or earlier.
        """
        try:
            self.progress.update(status='Loading transcript list and scrolling...')

            # Load search page
            print("Loading RollCall search page...")
            self.driver.get('https://rollcall.com/factbase/trump/search/')
            time.sleep(5)  # Let JavaScript load

            # Select "Sort By: Newest" from dropdown
            try:
                from selenium.webdriver.support.ui import Select
                sort_dropdown = Select(self.driver.find_element(By.NAME, 'sort'))
                sort_dropdown.select_by_visible_text('Sort By: Newest')
                print("✓ Selected 'Sort By: Newest'")
                time.sleep(3)  # Let page reload with new sort
            except Exception as e:
                print(f"⚠️  Could not set sort order: {str(e)}")
                print("   Continuing anyway...")

            urls = set()
            last_count = 0
            no_new_count = 0
            scroll_attempts = 0
            max_scroll_attempts = 1000
            oldest_date_seen = None
            newest_date_seen = None

            print("\n🔽 Scrolling to collect transcripts (Sept 2024 - Dec 2025)...")
            print("   Will skip transcripts outside this date range\n")

            while scroll_attempts < max_scroll_attempts:
                scroll_attempts += 1

                # Find all transcript links currently visible
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/transcript/']")

                    for elem in elements:
                        href = elem.get_attribute('href')
                        if href and '/transcript/' in href:
                            # Extract date from URL (format: -january-7-2025 or -december-31-2023)
                            date_match = re.search(r'-([a-z]+-\d{1,2}-\d{4})$', href, re.IGNORECASE)
                            if date_match:
                                try:
                                    # Parse date from URL
                                    date_str = date_match.group(1)
                                    transcript_date = datetime.strptime(date_str, '%B-%d-%Y')

                                    # ONLY collect Sept 2024 - Dec 2025
                                    cutoff_start = datetime(2024, 9, 1)
                                    cutoff_end = datetime(2026, 1, 1)

                                    if transcript_date < cutoff_start or transcript_date >= cutoff_end:
                                        continue  # Skip transcripts outside our range

                                    # Track date range
                                    if newest_date_seen is None or transcript_date > newest_date_seen:
                                        newest_date_seen = transcript_date
                                    if oldest_date_seen is None or transcript_date < oldest_date_seen:
                                        oldest_date_seen = transcript_date

                                    # Add transcript
                                    urls.add(href)

                                except Exception as parse_err:
                                    # If date parsing fails, skip
                                    pass

                except Exception as e:
                    print(f"  Warning: Error finding elements: {str(e)}")

                # Check if we found new URLs
                if len(urls) == last_count:
                    no_new_count += 1
                    if no_new_count >= 10:
                        # No new URLs found in last 10 scrolls, we're done
                        print(f"\n✓ Reached bottom - no new URLs after 10 scrolls")
                        print(f"\n📊 Collection Summary:")
                        print(f"   Newest: {newest_date_seen.strftime('%B %d, %Y') if newest_date_seen else 'N/A'}")
                        print(f"   Oldest: {oldest_date_seen.strftime('%B %d, %Y') if oldest_date_seen else 'N/A'}")
                        print(f"   Total: {len(urls)} transcripts")
                        print(f"   ✅ Collected ALL available RollCall transcripts!\n")
                        break
                else:
                    no_new_count = 0
                    last_count = len(urls)

                # Progress update every 5 scrolls
                if scroll_attempts % 5 == 0:
                    date_info = ""
                    if oldest_date_seen:
                        date_info = f" | Currently at: {oldest_date_seen.strftime('%b %d, %Y')}"
                    print(f"  Scroll {scroll_attempts}: {len(urls)} URLs{date_info}")
                    self.progress.update(status=f'Scrolling... {len(urls)} found')

                # Scroll down to load more (newest → oldest)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)  # Wait for new content to load

            print(f"✓ Scrolling complete - found {len(urls)} transcripts")
            return list(urls)

        except Exception as e:
            self.progress.add_error(f"Failed to get URLs: {str(e)}")
            print(f"❌ Error during URL collection: {str(e)}")
            return list(urls) if urls else []

    def parse_transcript_page(self, url, attempt=1):
        """Parse a single transcript page with retry logic"""
        try:
            self.progress.update(
                current_url=url,
                status=f'Loading transcript (attempt {attempt}/{self.max_retries})...'
            )

            # Load page - catch session errors
            try:
                self.driver.get(url)
            except WebDriverException as e:
                if 'invalid session id' in str(e).lower() or 'session' in str(e).lower():
                    # Browser crashed, need to restart
                    print("  ⚠️  Browser session lost, restarting...")
                    if self.restart_driver():
                        self.driver.get(url)
                    else:
                        raise Exception("Failed to restart browser after session loss")
                else:
                    raise

            # Wait for content to load
            wait = WebDriverWait(self.driver, 20)

            # Extract title
            try:
                title_elem = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'h1')))
                title = title_elem.text.strip()
            except:
                title = url.split('/')[-1].replace('-', ' ').title()

            self.progress.update(current_title=title)

            # Extract date from URL or page
            date = self.extract_date(url, self.driver.page_source)

            # Extract speech type
            speech_type = 'Speech'
            if 'interview' in title.lower():
                speech_type = 'Interview'
            elif 'press-conference' in url or 'press conference' in title.lower():
                speech_type = 'Press Conference'
            elif 'press-gaggle' in url or 'press gaggle' in title.lower():
                speech_type = 'Press Gaggle'
            elif 'remarks' in title.lower():
                speech_type = 'Remarks'

            # Extract dialogue sections
            dialogue_sections = self.extract_dialogue()

            if not dialogue_sections:
                logger.error(f"CRITICAL: No dialogue found for URL: {url} (attempt {attempt})")
                # Phase 1 improvement: Never silently accept empty transcripts
                # Return None to trigger retry logic, don't save empty content
                return None, "No dialogue found - will retry with different selectors"

            # Build full dialogue text with speaker labels
            full_dialogue = []
            trump_word_count = 0
            speakers = set()

            for section in dialogue_sections:
                speaker = section['speaker']
                text = section['text']
                timestamp = section.get('timestamp', '')

                speakers.add(speaker)

                # Format: Speaker Name (timestamp)\nText
                if timestamp:
                    full_dialogue.append(f"{speaker} ({timestamp})\n{text}\n")
                else:
                    full_dialogue.append(f"{speaker}\n{text}\n")

                # Count Trump's words
                if 'donald trump' in speaker.lower():
                    trump_word_count += len(text.split())

            full_dialogue_text = '\n'.join(full_dialogue)
            total_word_count = len(full_dialogue_text.split())

            # Extract duration if available
            duration = self.extract_duration(self.driver.page_source)

            result = {
                'title': title,
                'date': date,
                'speech_type': speech_type,
                'location': '',  # Can enhance later
                'url': url,
                'word_count': total_word_count,
                'trump_word_count': trump_word_count,
                'speech_duration_seconds': duration,
                'full_dialogue': full_dialogue_text,
                'speakers_json': json.dumps(list(speakers))
            }

            return result, None

        except TimeoutException:
            return None, f"Timeout loading page (attempt {attempt})"
        except WebDriverException as e:
            if 'invalid session id' in str(e).lower():
                return None, f"Browser session crashed (attempt {attempt})"
            return None, f"WebDriver error: {str(e)} (attempt {attempt})"
        except Exception as e:
            return None, f"Parse error: {str(e)} (attempt {attempt})"

    def extract_dialogue(self):
        """Extract speaker-separated dialogue sections with robust selector fallback"""
        dialogue = []

        try:
            # Use shared DialogueExtractor if available (Phase 1 improvement)
            if HAS_SCRAPER_UTILS:
                extractor = DialogueExtractor(self.driver, selectors=CONTENT_SELECTORS)
                dialogue = extractor.extract_dialogue(min_content_length=200)
                if dialogue:
                    return dialogue
                # If shared extractor fails, fall back to legacy logic below
                logger.warning("Shared extractor failed, using legacy extraction")
            
            # Legacy extraction logic (kept as fallback)
            selectors = [
                ".transcript-content",
                ".full-transcript",
                "[data-transcript]",
                ".speaker-section",
                "article",
                "main",
                ".content",
                "#transcript",
                "body"  # Last resort
            ]

            content_elem = None
            for selector in selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if elem:
                        # Check if element has substantial text (>200 chars)
                        text = elem.text.strip()
                        if len(text) >= 200:
                            content_elem = elem
                            logger.info(f"Using selector: {selector}")
                            break
                except:
                    continue

            if not content_elem:
                # Fallback: use body
                content_elem = self.driver.find_element(By.TAG_NAME, 'body')

            # Get all text
            html = content_elem.get_attribute('innerHTML')

            # Parse speaker sections using regex
            # Pattern: Speaker Name (optional timestamp)\nText
            speaker_pattern = r'<(?:p|div)[^>]*>\s*<strong>([^<]+)</strong>\s*(?:\(([^)]+)\))?\s*</(?:p|div)>\s*<(?:p|div)[^>]*>([^<]+)</(?:p|div)>'

            matches = re.finditer(speaker_pattern, html, re.IGNORECASE)

            for match in matches:
                speaker = match.group(1).strip()
                timestamp = match.group(2).strip() if match.group(2) else ''
                text = match.group(3).strip()

                if text:
                    dialogue.append({
                        'speaker': speaker,
                        'timestamp': timestamp,
                        'text': text
                    })

            # Alternative: Look for pattern in plain text
            if not dialogue:
                text = content_elem.text
                lines = text.split('\n')
                current_speaker = None
                current_text = []

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Check if line is a speaker name (ends with colon or is all caps)
                    if ':' in line and len(line.split(':')[0].split()) <= 4:
                        # Save previous speaker's text
                        if current_speaker and current_text:
                            dialogue.append({
                                'speaker': current_speaker,
                                'timestamp': '',
                                'text': ' '.join(current_text)
                            })

                        # Start new speaker
                        parts = line.split(':', 1)
                        current_speaker = parts[0].strip()
                        current_text = [parts[1].strip()] if len(parts) > 1 and parts[1].strip() else []
                    elif current_speaker:
                        current_text.append(line)

                # Don't forget last speaker
                if current_speaker and current_text:
                    dialogue.append({
                        'speaker': current_speaker,
                        'timestamp': '',
                        'text': ' '.join(current_text)
                    })

        except Exception as e:
            logger.error(f"Dialogue extraction error: {str(e)}")
            self.progress.add_error(f"Dialogue extraction error: {str(e)}")

        return dialogue

    def extract_date(self, url, page_source):
        """Extract date from URL or page"""
        # Try URL first (format: ...-january-7-2025 or ...-2025-01-07)
        date_patterns = [
            r'-(january|february|march|april|may|june|july|august|september|october|november|december)-(\d{1,2})-(\d{4})',
            r'-(\d{4})-(\d{2})-(\d{2})',
        ]

        for pattern in date_patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                try:
                    if len(match.groups()) == 3 and match.group(1).isalpha():
                        # Month name format
                        month = match.group(1).capitalize()
                        day = match.group(2)
                        year = match.group(3)
                        date_str = f"{month} {day}, {year}"
                        return datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
                    else:
                        # Numeric format
                        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                except:
                    pass

        return datetime.now().strftime("%Y-%m-%d")

    def extract_duration(self, page_source):
        """Extract speech duration in seconds"""
        # Look for duration in page
        duration_pattern = r'(\d+)\s*(?:minutes?|mins?)|(\d+):(\d+)(?::(\d+))?'
        match = re.search(duration_pattern, page_source, re.IGNORECASE)

        if match:
            if match.group(1):
                # Minutes format
                return int(match.group(1)) * 60
            else:
                # HH:MM:SS or MM:SS format
                hours = int(match.group(2)) if match.group(2) else 0
                minutes = int(match.group(3)) if match.group(3) else 0
                seconds = int(match.group(4)) if match.group(4) else 0
                return hours * 3600 + minutes * 60 + seconds

        return None

    def save_transcript(self, data):
        """Save transcript to database with validation"""
        try:
            # Validate that we have actual content
            if not data.get('full_dialogue') or data.get('word_count', 0) == 0:
                logger.error(f"Attempted to save empty transcript: {data.get('url')}")
                self.progress.add_error(f"Blocked save of empty transcript: {data.get('title')}")
                return False
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR IGNORE INTO transcripts
                (title, date, speech_type, location, url, word_count, trump_word_count,
                 speech_duration_seconds, full_dialogue, speakers_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['title'],
                data['date'],
                data['speech_type'],
                data['location'],
                data['url'],
                data['word_count'],
                data['trump_word_count'],
                data['speech_duration_seconds'],
                data['full_dialogue'],
                data['speakers_json']
            ))

            conn.commit()
            conn.close()
            logger.info(f"Saved transcript: {data['title']} ({data['word_count']} words)")
            return True
        except Exception as e:
            logger.error(f"DB save error for {data.get('url')}: {str(e)}")
            self.progress.add_error(f"DB save error: {str(e)}")
            return False

    def get_existing_urls(self):
        """Get list of URLs already in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM transcripts")
            existing = set(row[0] for row in cursor.fetchall())
            conn.close()
            return existing
        except:
            return set()

    def restart_driver(self):
        """Restart Chrome driver to prevent session crashes"""
        try:
            if self.driver:
                self.driver.quit()
                time.sleep(2)
            return self.init_driver()
        except Exception as e:
            print(f"  Error restarting driver: {str(e)}")
            return False

    def run(self):
        """Main scraping loop with full safety"""
        print("\n" + "="*80)
        print("ROBUST ROLLCALL SCRAPER - OVERNIGHT EDITION")
        print("="*80 + "\n")

        # Initialize database (but don't drop existing data)
        os.makedirs('data', exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                date DATE NOT NULL,
                speech_type TEXT NOT NULL,
                location TEXT,
                url TEXT UNIQUE NOT NULL,
                word_count INTEGER,
                trump_word_count INTEGER,
                speech_duration_seconds INTEGER,
                full_dialogue TEXT NOT NULL,
                speakers_json TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        print("✓ Database ready")

        if not self.init_driver():
            print("❌ Failed to initialize browser")
            return

        try:
            # Get all URLs
            urls = self.get_transcript_urls()

            if not urls:
                print("❌ No transcripts found")
                return

            # Check which URLs we already have
            existing_urls = self.get_existing_urls()
            remaining_urls = [url for url in urls if url not in existing_urls]

            print(f"\n📋 Total transcripts: {len(urls)}")
            print(f"✓ Already scraped: {len(existing_urls)}")
            print(f"📥 Remaining to scrape: {len(remaining_urls)}\n")

            if not remaining_urls:
                print("✅ All transcripts already scraped!")
                return

            self.progress.update(total=len(remaining_urls), status='Starting scrape...')

            # Process each transcript
            for i, url in enumerate(remaining_urls, 1):
                print(f"\n[{i}/{len(remaining_urls)}] {url}")

                # Restart browser every 50 transcripts to prevent crashes
                if i % 50 == 0:
                    print("\n🔄 Restarting browser to prevent session errors...")
                    if not self.restart_driver():
                        print("❌ Failed to restart browser, stopping")
                        break
                    print("✓ Browser restarted\n")

                # Skip if already exists (double check)
                if url in existing_urls:
                    print("  ⏭️  Already in database, skipping")
                    continue

                # Try up to max_retries times
                success = False
                for attempt in range(1, self.max_retries + 1):
                    data, error = self.parse_transcript_page(url, attempt)

                    if data:
                        # Success! Save to database
                        if self.save_transcript(data):
                            print(f"  ✓ Saved: {data['title'][:60]}")
                            print(f"    Words: {data['word_count']} | Trump: {data['trump_word_count']}")

                            self.progress.update(
                                processed=i,
                                successful=self.progress.data['successful'] + 1,
                                status=f'Successfully saved transcript {i}/{len(urls)}'
                            )
                            success = True
                            break
                        else:
                            error = "Database save failed"

                    if attempt < self.max_retries:
                        print(f"  ⚠️  {error} - Retrying...")
                        time.sleep(self.delay * attempt)  # Exponential backoff

                if not success:
                    print(f"  ❌ Failed after {self.max_retries} attempts: {error}")
                    self.progress.update(
                        processed=i,
                        failed=self.progress.data['failed'] + 1
                    )
                    self.progress.add_error(f"{url}: {error}")

                # Checkpoint every 10 transcripts
                if i % 10 == 0:
                    print(f"\n📊 CHECKPOINT: {i}/{len(urls)} processed")
                    print(f"   ✓ Success: {self.progress.data['successful']}")
                    print(f"   ✗ Failed: {self.progress.data['failed']}\n")

                # Polite delay
                time.sleep(self.delay)

            # Final summary
            print("\n" + "="*80)
            print("SCRAPING COMPLETE!")
            print("="*80)
            print(f"Total: {len(urls)}")
            print(f"✓ Successful: {self.progress.data['successful']}")
            print(f"✗ Failed: {self.progress.data['failed']}")
            print("="*80 + "\n")

            self.progress.update(status='Complete!')

        except KeyboardInterrupt:
            print("\n\n⚠️  INTERRUPTED BY USER")
            print(f"Progress saved. Processed: {self.progress.data['processed']}/{self.progress.data['total']}")
            self.progress.update(status='Interrupted by user')
        except Exception as e:
            print(f"\n\n❌ CRITICAL ERROR: {str(e)}")
            self.progress.add_error(f"Critical: {str(e)}")
            self.progress.update(status=f'Error: {str(e)}')
        finally:
            if self.driver:
                self.driver.quit()
                print("✓ Browser closed")

def start_progress_server():
    """Start HTTP server for progress dashboard"""

    # Create dashboard HTML
    dashboard_html = '''<!DOCTYPE html>
<html>
<head>
    <title>RollCall Scraper Progress</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1200px;
            margin: 50px auto;
            padding: 20px;
            background: #0f172a;
            color: #e2e8f0;
        }
        h1 {
            color: #60a5fa;
            border-bottom: 2px solid #1e293b;
            padding-bottom: 10px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .stat-card {
            background: #1e293b;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #334155;
        }
        .stat-value {
            font-size: 36px;
            font-weight: bold;
            color: #60a5fa;
        }
        .stat-label {
            font-size: 14px;
            color: #94a3b8;
            margin-top: 5px;
        }
        .progress-bar {
            width: 100%;
            height: 40px;
            background: #1e293b;
            border-radius: 8px;
            overflow: hidden;
            margin: 20px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #60a5fa);
            transition: width 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
        }
        .current-task {
            background: #1e293b;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #60a5fa;
            margin: 20px 0;
        }
        .error-log {
            background: #1e293b;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #ef4444;
            max-height: 400px;
            overflow-y: auto;
            margin: 20px 0;
        }
        .error-item {
            padding: 10px;
            margin: 5px 0;
            background: #0f172a;
            border-radius: 4px;
            font-size: 13px;
        }
        .timestamp {
            color: #64748b;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <h1>🤖 RollCall Scraper - Live Progress</h1>

    <div id="content">
        <p>Loading...</p>
    </div>

    <script>
        async function updateProgress() {
            try {
                const response = await fetch('scraper_progress.json');
                const data = await response.json();

                const percent = data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0;

                document.getElementById('content').innerHTML = `
                    <div class="stats">
                        <div class="stat-card">
                            <div class="stat-value">${data.processed}</div>
                            <div class="stat-label">Processed</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.successful}</div>
                            <div class="stat-label">✓ Successful</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.failed}</div>
                            <div class="stat-label">✗ Failed</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.total}</div>
                            <div class="stat-label">Total</div>
                        </div>
                    </div>

                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${percent}%">
                            ${percent}%
                        </div>
                    </div>

                    <div class="current-task">
                        <strong>Status:</strong> ${data.status}<br>
                        <strong>Current:</strong> ${data.current_title || 'N/A'}<br>
                        <strong>Last Update:</strong> ${new Date(data.last_update).toLocaleTimeString()}
                    </div>

                    ${data.errors && data.errors.length > 0 ? `
                        <h2>Recent Errors (${data.errors.length})</h2>
                        <div class="error-log">
                            ${data.errors.slice(-20).reverse().map(e => `
                                <div class="error-item">
                                    <div class="timestamp">${new Date(e.time).toLocaleTimeString()}</div>
                                    ${e.message}
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                `;
            } catch (e) {
                document.getElementById('content').innerHTML = '<p>Error loading progress data</p>';
            }
        }

        updateProgress();
        setInterval(updateProgress, 5000);
    </script>
</body>
</html>'''

    with open('scraper_dashboard.html', 'w') as f:
        f.write(dashboard_html)

    print("✓ Dashboard created at: scraper_dashboard.html")
    print("📊 View progress at: http://localhost:8000/scraper_dashboard.html\n")

if __name__ == '__main__':
    # Create dashboard
    start_progress_server()

    # Start scraping
    scraper = RobustRollCallScraper()
    scraper.run()
