#!/usr/bin/env python3
"""
Incremental RollCall transcript sync module
Discovers and scrapes new transcripts since the last database update
"""

import time
import json
import sqlite3
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    logging.warning("Selenium not available - sync will not work")

# Import shared scraper utilities
try:
    from scraper_utils import (
        DialogueExtractor, 
        build_dialogue_text, 
        validate_transcript_content,
        CONTENT_SELECTORS,
        extract_date_from_url
    )
    HAS_SCRAPER_UTILS = True
except ImportError:
    HAS_SCRAPER_UTILS = False
    logging.warning("scraper_utils not available, using built-in extraction")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SyncSummary:
    """Summary of sync operation"""
    added: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    start_date: str = ''
    end_date: str = ''
    total_discovered: int = 0
    error: Optional[str] = None


class RollCallIncrementalSync:
    """Handles incremental syncing of RollCall transcripts"""
    
    def __init__(self, db_path: str, progress_callback: Optional[Callable] = None):
        """
        Initialize sync handler
        
        Args:
            db_path: Path to transcripts.db
            progress_callback: Optional function(message, counts) to report progress
        """
        self.db_path = db_path
        self.progress_callback = progress_callback
        self.driver = None
        self.base_url = 'https://rollcall.com/factbase/trump/search/'
        self.delay = 1.5  # Seconds between requests
        
    def _report_progress(self, message: str, **counts):
        """Report progress to callback if set"""
        if self.progress_callback:
            self.progress_callback(message, counts)
        logger.info(f"{message} | {counts}")
    
    def _get_sync_window(self) -> Tuple[datetime, datetime]:
        """
        Determine the date window to sync
        
        Returns:
            (start_date, end_date) tuple
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the latest transcript date in DB (with valid content)
        cursor.execute("""
            SELECT MAX(date) 
            FROM transcripts 
            WHERE date LIKE '____-__-__' 
            AND word_count > 0
            AND full_dialogue IS NOT NULL
            AND full_dialogue != ''
        """)
        
        result = cursor.fetchone()
        max_date_str = result[0] if result and result[0] else None
        conn.close()
        
        if max_date_str:
            # Start from 1 day before max date to be safe
            max_date = datetime.strptime(max_date_str, '%Y-%m-%d')
            start_date = max_date - timedelta(days=1)
        else:
            # No valid transcripts, start from Sept 2024
            start_date = datetime(2024, 9, 1)
        
        # End at today
        end_date = datetime.now()
        
        logger.info(f"Sync window: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        return start_date, end_date
    
    def _init_driver(self) -> bool:
        """Initialize Chrome driver"""
        if not HAS_SELENIUM:
            logger.error("Selenium not available")
            return False
        
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            logger.info("Chrome driver initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            return False
    
    def _discover_urls_in_range(self, start_date: datetime, end_date: datetime) -> List[Tuple[str, datetime]]:
        """
        Discover transcript URLs within date range
        
        Returns:
            List of (url, date) tuples
        """
        if not self.driver:
            if not self._init_driver():
                return []
        
        self._report_progress("Loading RollCall search page...")
        
        try:
            # Load search page
            self.driver.get(self.base_url)
            time.sleep(5)
            
            # Select "Sort By: Newest"
            try:
                from selenium.webdriver.support.ui import Select
                sort_dropdown = Select(self.driver.find_element(By.NAME, 'sort'))
                sort_dropdown.select_by_visible_text('Sort By: Newest')
                logger.info("Selected 'Sort By: Newest'")
                time.sleep(3)
            except Exception as e:
                logger.warning(f"Could not set sort order: {e}")
            
            urls_with_dates = []
            last_count = 0
            no_new_count = 0
            scroll_attempts = 0
            max_scroll_attempts = 200
            
            self._report_progress(f"Scrolling to find transcripts from {start_date.strftime('%Y-%m-%d')} onwards...")
            
            while scroll_attempts < max_scroll_attempts:
                scroll_attempts += 1
                
                # Find all transcript links
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/transcript/']")
                    
                    for elem in elements:
                        href = elem.get_attribute('href')
                        if not href or '/transcript/' not in href:
                            continue
                        
                        # Extract date from URL
                        date_str = extract_date_from_url(href)
                        if not date_str:
                            continue
                        
                        try:
                            transcript_date = datetime.strptime(date_str, '%Y-%m-%d')
                            
                            # Only collect transcripts in our sync window
                            if start_date <= transcript_date <= end_date:
                                url_date_tuple = (href, transcript_date)
                                if url_date_tuple not in urls_with_dates:
                                    urls_with_dates.append(url_date_tuple)
                            
                            # Stop scrolling if we've gone past our start date
                            elif transcript_date < start_date:
                                logger.info(f"Reached transcripts older than start date, stopping scroll")
                                return urls_with_dates
                        
                        except Exception as parse_err:
                            continue
                
                except Exception as e:
                    logger.warning(f"Error finding elements: {e}")
                
                # Check if we found new URLs
                if len(urls_with_dates) == last_count:
                    no_new_count += 1
                    if no_new_count >= 10:
                        logger.info(f"No new URLs in range after 10 scrolls, stopping")
                        break
                else:
                    no_new_count = 0
                    last_count = len(urls_with_dates)
                
                # Progress update every 10 scrolls
                if scroll_attempts % 10 == 0:
                    self._report_progress(f"Scrolling... found {len(urls_with_dates)} URLs in range", discovered=len(urls_with_dates))
                
                # Scroll down
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
            
            logger.info(f"Discovery complete: {len(urls_with_dates)} URLs in range")
            return urls_with_dates
        
        except Exception as e:
            logger.error(f"Error during URL discovery: {e}")
            return []
    
    def _get_urls_to_scrape(self, discovered_urls: List[Tuple[str, datetime]]) -> List[Tuple[str, datetime]]:
        """
        Filter discovered URLs to those that need scraping
        
        Returns:
            List of (url, date) tuples that need to be scraped
        """
        if not discovered_urls:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        to_scrape = []
        
        for url, date in discovered_urls:
            # Check if URL exists in DB
            cursor.execute("SELECT id, word_count, full_dialogue FROM transcripts WHERE url = ?", (url,))
            row = cursor.fetchone()
            
            if not row:
                # New URL, need to scrape
                to_scrape.append((url, date))
            else:
                # Exists - check if it's empty/broken
                transcript_id, word_count, full_dialogue = row
                if not word_count or word_count == 0 or not full_dialogue or full_dialogue.strip() == '':
                    # Empty transcript, need to re-scrape
                    to_scrape.append((url, date))
        
        conn.close()
        
        logger.info(f"Filtered to {len(to_scrape)} URLs that need scraping (out of {len(discovered_urls)} discovered)")
        return to_scrape
    
    def _parse_transcript_page(self, url: str, date: datetime) -> Optional[Dict]:
        """Parse a single transcript page"""
        try:
            self.driver.get(url)
            wait = WebDriverWait(self.driver, 20)
            
            # Extract title
            try:
                title_elem = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'h1')))
                title = title_elem.text.strip()
            except:
                title = url.split('/')[-1].replace('-', ' ').title()
            
            # Determine speech type
            speech_type = 'Speech'
            title_lower = title.lower()
            if 'interview' in title_lower:
                speech_type = 'Interview'
            elif 'press conference' in title_lower or 'press-conference' in url:
                speech_type = 'Press Conference'
            elif 'press gaggle' in title_lower or 'press-gaggle' in url:
                speech_type = 'Press Gaggle'
            elif 'briefing' in title_lower:
                speech_type = 'Press Briefing'
            elif 'remarks' in title_lower:
                speech_type = 'Remarks'
            
            # Extract dialogue using robust extractor
            dialogue_sections = []
            
            if HAS_SCRAPER_UTILS:
                extractor = DialogueExtractor(self.driver, selectors=CONTENT_SELECTORS)
                dialogue_sections = extractor.extract_dialogue(min_content_length=200)
            
            if not dialogue_sections:
                logger.warning(f"No dialogue found for {url}")
                return None
            
            # Build full dialogue text
            full_dialogue = []
            trump_word_count = 0
            speakers = set()
            
            for section in dialogue_sections:
                speaker = section.get('speaker', 'Unknown')
                text = section.get('text', '')
                timestamp = section.get('timestamp', '')
                
                speakers.add(speaker)
                
                if timestamp:
                    full_dialogue.append(f"{speaker} ({timestamp})\n{text}\n")
                else:
                    full_dialogue.append(f"{speaker}\n{text}\n")
                
                # Count Trump's words
                if 'donald trump' in speaker.lower() or 'trump' == speaker.lower():
                    trump_word_count += len(text.split())
            
            full_dialogue_text = '\n'.join(full_dialogue)
            total_word_count = len(full_dialogue_text.split())
            
            # Extract duration if available
            duration = self._extract_duration(self.driver.page_source)
            
            result = {
                'title': title,
                'date': date.strftime('%Y-%m-%d'),
                'speech_type': speech_type,
                'location': '',  # Could enhance later
                'url': url,
                'word_count': total_word_count,
                'trump_word_count': trump_word_count,
                'speech_duration_seconds': duration,
                'full_dialogue': full_dialogue_text,
                'speakers_json': json.dumps(list(speakers))
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            return None
    
    def _extract_duration(self, page_source: str) -> Optional[int]:
        """Extract speech duration in seconds from page source"""
        duration_pattern = r'(\d+)\s*(?:minutes?|mins?)|(\d+):(\d+)(?::(\d+))?'
        match = re.search(duration_pattern, page_source, re.IGNORECASE)
        
        if match:
            if match.group(1):
                return int(match.group(1)) * 60
            else:
                hours = int(match.group(2)) if match.group(2) else 0
                minutes = int(match.group(3)) if match.group(3) else 0
                seconds = int(match.group(4)) if match.group(4) else 0
                return hours * 3600 + minutes * 60 + seconds
        
        return None
    
    def _upsert_transcript(self, data: Dict) -> bool:
        """
        Insert or update transcript in database
        
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Use INSERT OR REPLACE (upsert based on unique url constraint)
            cursor.execute("""
                INSERT INTO transcripts 
                (title, date, speech_type, location, url, word_count, trump_word_count,
                 speech_duration_seconds, full_dialogue, speakers_json, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    date = excluded.date,
                    speech_type = excluded.speech_type,
                    location = excluded.location,
                    word_count = excluded.word_count,
                    trump_word_count = excluded.trump_word_count,
                    speech_duration_seconds = excluded.speech_duration_seconds,
                    full_dialogue = excluded.full_dialogue,
                    speakers_json = excluded.speakers_json,
                    scraped_at = CURRENT_TIMESTAMP
            """, (
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
            return True
        
        except Exception as e:
            logger.error(f"Error upserting transcript: {e}")
            return False
    
    def run_incremental_sync(self) -> SyncSummary:
        """
        Run incremental sync process
        
        Returns:
            SyncSummary with results
        """
        summary = SyncSummary()
        
        try:
            # Step 1: Determine sync window
            self._report_progress("Determining sync window...")
            start_date, end_date = self._get_sync_window()
            summary.start_date = start_date.strftime('%Y-%m-%d')
            summary.end_date = end_date.strftime('%Y-%m-%d')
            
            # Step 2: Initialize Selenium
            self._report_progress("Initializing browser...")
            if not self._init_driver():
                summary.error = "Failed to initialize Chrome driver"
                return summary
            
            # Step 3: Discover URLs in range
            self._report_progress(f"Discovering transcripts from {summary.start_date} to {summary.end_date}...")
            discovered_urls = self._discover_urls_in_range(start_date, end_date)
            summary.total_discovered = len(discovered_urls)
            
            if not discovered_urls:
                self._report_progress("No transcripts found in date range")
                return summary
            
            # Step 4: Filter to URLs that need scraping
            self._report_progress("Checking which transcripts need scraping...")
            urls_to_scrape = self._get_urls_to_scrape(discovered_urls)
            
            if not urls_to_scrape:
                self._report_progress("All discovered transcripts are already in database")
                summary.skipped = len(discovered_urls)
                return summary
            
            # Step 5: Scrape each URL
            self._report_progress(f"Scraping {len(urls_to_scrape)} transcripts...", total=len(urls_to_scrape))
            
            for i, (url, date) in enumerate(urls_to_scrape, 1):
                self._report_progress(
                    f"Scraping {i}/{len(urls_to_scrape)}: {url.split('/')[-1][:50]}...",
                    processed=i,
                    total=len(urls_to_scrape),
                    added=summary.added,
                    updated=summary.updated,
                    failed=summary.failed
                )
                
                # Check if URL already exists (for counting added vs updated)
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM transcripts WHERE url = ?", (url,))
                exists = cursor.fetchone() is not None
                conn.close()
                
                # Parse transcript
                data = self._parse_transcript_page(url, date)
                
                if data:
                    # Upsert to database
                    if self._upsert_transcript(data):
                        if exists:
                            summary.updated += 1
                            logger.info(f"Updated: {data['title'][:60]}")
                        else:
                            summary.added += 1
                            logger.info(f"Added: {data['title'][:60]}")
                    else:
                        summary.failed += 1
                else:
                    summary.failed += 1
                
                # Rate limiting
                time.sleep(self.delay)
            
            # Final summary
            self._report_progress(
                f"Sync complete! Added: {summary.added}, Updated: {summary.updated}, Failed: {summary.failed}",
                added=summary.added,
                updated=summary.updated,
                failed=summary.failed,
                total=len(urls_to_scrape)
            )
            
        except Exception as e:
            logger.error(f"Sync error: {e}")
            summary.error = str(e)
        
        finally:
            # Cleanup
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
        
        return summary


def run_incremental_sync(db_path: str, progress_callback: Optional[Callable] = None) -> SyncSummary:
    """
    Convenience function to run incremental sync
    
    Args:
        db_path: Path to transcripts.db
        progress_callback: Optional function(message, counts) to report progress
    
    Returns:
        SyncSummary with results
    """
    sync = RollCallIncrementalSync(db_path, progress_callback)
    return sync.run_incremental_sync()


if __name__ == '__main__':
    # Test run
    import os
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'transcripts.db')
    
    def progress_printer(message, counts):
        print(f"[SYNC] {message}")
        if counts:
            print(f"       Counts: {counts}")
    
    summary = run_incremental_sync(db_path, progress_printer)
    
    print("\n" + "="*80)
    print("SYNC SUMMARY")
    print("="*80)
    print(f"Date Range: {summary.start_date} to {summary.end_date}")
    print(f"Discovered: {summary.total_discovered}")
    print(f"Added: {summary.added}")
    print(f"Updated: {summary.updated}")
    print(f"Failed: {summary.failed}")
    if summary.error:
        print(f"Error: {summary.error}")
    print("="*80)

