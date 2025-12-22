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
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        HAS_WEBDRIVER_MANAGER = True
    except ImportError:
        HAS_WEBDRIVER_MANAGER = False
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    HAS_WEBDRIVER_MANAGER = False
    logging.warning("Selenium not available - sync will not work")

# Playwright imports (alternative browser automation)
try:
    from playwright.sync_api import sync_playwright, Browser, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    sync_playwright = None
    Browser = None
    Page = None
    logging.warning("Playwright not available - will use Selenium only")

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


# ============================================================================
# TRANSCRIPT NORMALIZATION FUNCTIONS
# ============================================================================

def normalize_speaker_label(raw_speaker: str) -> Tuple[str, bool]:
    """
    Normalize speaker label to canonical form
    
    Removes:
    - Trailing numeric suffixes: "Donald Trump 00" -> "Donald Trump"
    - Timestamps: "Donald Trump (00:10:12)" -> "Donald Trump"
    - Timestamp-like patterns: "Donald Trump 00:10:12" -> "Donald Trump"
    - Trailing colons: "Donald Trump:" -> "Donald Trump"
    
    Args:
        raw_speaker: Raw speaker label from scraper
    
    Returns:
        (normalized_label, was_modified) tuple
    """
    if not raw_speaker:
        return raw_speaker, False
    
    original = raw_speaker
    cleaned = raw_speaker.strip()
    
    # Remove timestamps in parentheses: (00:10:12)
    cleaned = re.sub(r'\s*\([^)]*\)\s*$', '', cleaned)
    
    # Remove timestamp-like patterns: 00:10:12 or 0:10:12
    cleaned = re.sub(r'\s+\d{1,2}:\d{2}(?::\d{2})?\s*$', '', cleaned)
    
    # Remove trailing numeric suffixes: " 00", " 01", etc.
    cleaned = re.sub(r'\s+\d{1,2}\s*$', '', cleaned)
    
    # Remove trailing colons
    cleaned = re.sub(r'\s*:\s*$', '', cleaned)
    
    # Normalize whitespace
    cleaned = ' '.join(cleaned.split())
    
    was_modified = (cleaned != original)
    
    return cleaned, was_modified


def strip_rollcall_artifacts(text: str) -> Tuple[str, Dict[str, int]]:
    """
    Remove RollCall-specific artifacts and boilerplate from transcript text
    
    Removes:
    - Header metadata (StressLens, Topics, Entities, etc.)
    - Timestamp lines (00:00-00:00:10)
    - Rating lines (NO STRESSLENS:, NO SIGNAL (0.125):, etc.)
    - Signal rating blocks
    - RollCall site boilerplate (header/footer)
    - Advertisement text
    - Inline annotations ([Inaudible], [Laughter], etc.)
    
    Args:
        text: Raw transcript text
    
    Returns:
        (cleaned_text, stats) where stats contains removal counts
    """
    if not text:
        return text, {}
    
    stats = {
        'signal_rating_blocks': 0,
        'boilerplate_lines': 0,
        'timestamp_lines': 0,
        'rating_lines': 0,
        'annotations_removed': 0
    }
    
    lines = text.split('\n')
    cleaned_lines = []
    
    # Known boilerplate patterns (case-insensitive)
    boilerplate_patterns = [
        r'StressLens.*Topics.*Entities',
        r'Moderation.*Speakers.*Full Transcript',
        r'CAPITOL HILL SINCE \d{4}',
        r'About Contact Us Advertise Events Privacy',
        r'RC Jobs Newsletters The Staff Subscriptions',
        r'CQ and Roll Call are part of',
        r'FiscalNote.*provider of political',
        r'Sign up for our newsletters',
        r'Subscribe to.*Roll Call',
        r'©.*Roll Call',
        r'All Rights Reserved',
        r'Privacy Policy|Terms of Service',
        r'Cookie Policy|Cookie Settings'
    ]
    
    # Patterns for RollCall metadata lines
    timestamp_pattern = re.compile(r'^\d{1,2}:\d{2}-\d{1,2}:\d{2}:\d{2}\s*\(.*\)$')
    rating_pattern = re.compile(r'^(NO STRESSLENS|NO SIGNAL|MEDIUM|WEAK|STRONG|HIGH)(\s*\([0-9\.]+\))?:')
    signal_rating_pattern = re.compile(r'signal\s+rating', re.IGNORECASE)
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines (will add back controlled spacing)
        if not stripped:
            # Don't add multiple consecutive blank lines
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            continue
        
        # Skip timestamp lines (00:00-00:00:10 (10 sec))
        if timestamp_pattern.match(stripped):
            stats['timestamp_lines'] += 1
            continue
        
        # Skip rating lines (NO STRESSLENS:, NO SIGNAL (0.125):, etc.)
        if rating_pattern.match(stripped):
            stats['rating_lines'] += 1
            continue
        
        # Skip signal rating blocks
        if signal_rating_pattern.search(stripped):
            stats['signal_rating_blocks'] += 1
            continue
        
        # Skip boilerplate
        is_boilerplate = False
        for pattern in boilerplate_patterns:
            if re.search(pattern, stripped, re.IGNORECASE):
                stats['boilerplate_lines'] += 1
                is_boilerplate = True
                break
        
        if is_boilerplate:
            continue
        
        cleaned_lines.append(line)
    
    # Join and normalize whitespace
    cleaned_text = '\n'.join(cleaned_lines)
    
    # Remove inline annotations: [Inaudible], [Laughter], [Audience...], [Crosstalk], etc.
    annotation_pattern = r'\[(?:Inaudible|Laughter|Laughs|Applause|Crosstalk|Audience.*?)\]'
    annotation_count = len(re.findall(annotation_pattern, cleaned_text, re.IGNORECASE))
    stats['annotations_removed'] = annotation_count
    cleaned_text = re.sub(annotation_pattern, '', cleaned_text, flags=re.IGNORECASE)
    
    # Remove excessive blank lines (more than 2 consecutive)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    
    # Clean up spaces
    cleaned_text = re.sub(r' +', ' ', cleaned_text)
    
    return cleaned_text.strip(), stats


def normalize_transcript_format(dialogue_sections: List[Dict], 
                                existing_dialogue: Optional[str] = None) -> Tuple[str, str, int, int, Dict[str, int]]:
    """
    Normalize transcript format before DB insertion
    
    Args:
        dialogue_sections: List of {speaker, text, timestamp} dicts from scraper
        existing_dialogue: Existing full_dialogue from DB (for comparison)
    
    Returns:
        (full_dialogue, speakers_json, word_count, trump_word_count, normalization_stats)
    """
    if not dialogue_sections:
        return '', '[]', 0, 0, {}
    
    normalization_stats = {
        'speaker_labels_normalized': 0,
        'signal_rating_blocks': 0,
        'boilerplate_lines': 0,
        'timestamp_lines': 0,
        'rating_lines': 0,
        'annotations_removed': 0
    }
    
    full_dialogue = []
    trump_word_count = 0
    speakers = set()
    
    for section in dialogue_sections:
        raw_speaker = section.get('speaker', 'Unknown')
        raw_text = section.get('text', '')
        timestamp = section.get('timestamp', '')
        
        # Normalize speaker label (remove timestamps, numeric suffixes)
        normalized_speaker, was_modified = normalize_speaker_label(raw_speaker)
        if was_modified:
            normalization_stats['speaker_labels_normalized'] += 1
        
        speakers.add(normalized_speaker)
        
        # Strip artifacts from text (signal ratings, boilerplate, timestamps, etc.)
        cleaned_text, text_stats = strip_rollcall_artifacts(raw_text)
        normalization_stats['signal_rating_blocks'] += text_stats.get('signal_rating_blocks', 0)
        normalization_stats['boilerplate_lines'] += text_stats.get('boilerplate_lines', 0)
        normalization_stats['timestamp_lines'] += text_stats.get('timestamp_lines', 0)
        normalization_stats['rating_lines'] += text_stats.get('rating_lines', 0)
        normalization_stats['annotations_removed'] += text_stats.get('annotations_removed', 0)
        
        # Skip empty sections
        if not cleaned_text or not cleaned_text.strip():
            continue
        
        # Build consistent format: "Speaker\nText\n" (no timestamps in output)
        full_dialogue.append(f"{normalized_speaker}\n{cleaned_text}\n")
        
        # Count Trump's words
        if 'donald trump' in normalized_speaker.lower() or normalized_speaker.lower() == 'trump':
            trump_word_count += len(cleaned_text.split())
    
    full_dialogue_text = '\n'.join(full_dialogue)
    total_word_count = len(full_dialogue_text.split())
    speakers_json = json.dumps(sorted(list(speakers)))
    
    return full_dialogue_text, speakers_json, total_word_count, trump_word_count, normalization_stats


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
    # Normalization stats
    speaker_labels_normalized: int = 0
    signal_rating_blocks_removed: int = 0
    boilerplate_lines_removed: int = 0
    timestamp_lines_removed: int = 0
    rating_lines_removed: int = 0
    annotations_removed: int = 0


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
        self.playwright_browser = None
        self.playwright_context = None
        self.playwright_page = None
        self.base_url = 'https://rollcall.com/factbase/trump/search/'
        self.delay = 1.5  # Seconds between requests
        self._last_error = None  # Store last error for debugging
        self._diagnostics = []  # Store diagnostic messages
        
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
            # Start from the day after max date to get new transcripts
            max_date = datetime.strptime(max_date_str, '%Y-%m-%d')
            start_date = max_date + timedelta(days=1)
        else:
            # No valid transcripts, start from Sept 2024
            start_date = datetime(2024, 9, 1)
        
        # End at today
        end_date = datetime.now()
        
        logger.info(f"Sync window: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        return start_date, end_date
    
    def _init_driver(self) -> bool:
        """Initialize browser driver (tries Playwright first, then Selenium)"""
        # Try Playwright first (bundles browsers, works better on cloud)
        if HAS_PLAYWRIGHT:
            try:
                from playwright.sync_api import sync_playwright
                self.playwright_context = sync_playwright().start()
                self.playwright_browser = self.playwright_context.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                self.playwright_page = self.playwright_browser.new_page()
                logger.info("Browser initialized via Playwright")
                return True
            except Exception as pw_err:
                logger.warning(f"Playwright initialization failed: {pw_err}, trying Selenium...")
        
        # Fallback to Selenium
        if not HAS_SELENIUM:
            logger.error("Neither Playwright nor Selenium available")
            self._last_error = "No browser automation library available (Playwright or Selenium)"
            return False
        
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-setuid-sandbox')
            options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Try multiple strategies to initialize Chrome driver
            driver_initialized = False
            
            # Strategy 1: Use webdriver-manager (auto-downloads ChromeDriver)
            if HAS_WEBDRIVER_MANAGER:
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=options)
                    driver_initialized = True
                    logger.info("Chrome driver initialized via webdriver-manager")
                except Exception as wdm_err:
                    logger.warning(f"webdriver-manager failed: {wdm_err}")
            
            # Strategy 2: Standard Chrome initialization (assumes ChromeDriver in PATH)
            if not driver_initialized:
                try:
                    self.driver = webdriver.Chrome(options=options)
                    driver_initialized = True
                    logger.info("Chrome driver initialized via standard method")
                except Exception as std_err:
                    logger.warning(f"Standard Chrome init failed: {std_err}")
            
            # Strategy 3: Try with explicit Chrome binary path (for Render/cloud)
            if not driver_initialized:
                chrome_paths = [
                    '/usr/bin/google-chrome',
                    '/usr/bin/google-chrome-stable',
                    '/usr/bin/chromium-browser',
                    '/usr/bin/chromium',
                ]
                for chrome_path in chrome_paths:
                    try:
                        import os
                        if os.path.exists(chrome_path):
                            options.binary_location = chrome_path
                            self.driver = webdriver.Chrome(options=options)
                            driver_initialized = True
                            logger.info(f"Chrome driver initialized with binary at {chrome_path}")
                            break
                    except Exception as path_err:
                        logger.debug(f"Chrome path {chrome_path} failed: {path_err}")
                        continue
            
            if not driver_initialized:
                error_details = []
                error_details.append("All Chrome driver initialization strategies failed")
                error_details.append("This usually means Chrome/Chromium is not installed on the server")
                error_details.append("On Render free tier, Chrome may not be available")
                error_details.append("Consider using a different scraping method or upgrading Render plan")
                raise Exception(" | ".join(error_details))
            
            self.driver.set_page_load_timeout(30)
            logger.info("Chrome driver initialized successfully")
            return True
        except Exception as e:
            error_msg = f"Failed to initialize Chrome driver: {e}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            # Store detailed error for API status endpoint
            self._last_error = str(e)
            return False
    
    def _discover_urls_in_range(self, start_date: datetime, end_date: datetime) -> List[Tuple[str, datetime]]:
        """
        Discover transcript URLs within date range
        
        Returns:
            List of (url, date) tuples
        """
        # Initialize driver if needed (Playwright or Selenium)
        if not self.driver and not self.playwright_page:
            if not self._init_driver():
                return []
        
        self._report_progress("Loading RollCall search page...")
        
        try:
            # Load search page (use Playwright if available, else Selenium)
            if self.playwright_page:
                self.playwright_page.goto(self.base_url, wait_until='networkidle', timeout=60000)
                time.sleep(2)
                current_url = self.playwright_page.url
                page_title = self.playwright_page.title()
                logger.info(f"Playwright loaded page: {current_url}, title: {page_title}")
                self._diagnostics.append(f"Page loaded: {current_url[:100]}")
            else:
                self.driver.get(self.base_url)
                time.sleep(5)
                current_url = self.driver.current_url
                page_title = self.driver.title
                logger.info(f"Selenium loaded page: {current_url}, title: {page_title}")
                self._diagnostics.append(f"Page loaded: {current_url[:100]}")
            
            # Select "Sort By: Newest" - try multiple strategies
            sort_selected = False
            selected_text = "Unknown"
            
            if self.playwright_page:
                # Playwright approach for sort selection
                try:
                    # Try to find and select the sort dropdown
                    select_elem = self.playwright_page.query_selector('select[name="sort"]')
                    if select_elem:
                        # Get all options
                        options = select_elem.query_selector_all('option')
                        for opt in options:
                            opt_text = opt.inner_text()
                            if 'newest' in opt_text.lower():
                                # Select this option
                                value = opt.get_attribute('value')
                                if value:
                                    select_elem.select_option(value=value)
                                    selected_text = opt_text
                                    sort_selected = True
                                    logger.info(f"Playwright sort selection succeeded: {selected_text}")
                                    break
                except Exception as e:
                    logger.warning(f"Playwright sort selection failed: {e}")
            
            # Selenium approach for sort selection
            if not sort_selected:
                # Strategy 1: Try standard select element by name
                try:
                    from selenium.webdriver.support.ui import Select
                    sort_dropdown = Select(self.driver.find_element(By.NAME, 'sort'))
                    sort_dropdown.select_by_visible_text('Sort By: Newest')
                    selected_text = sort_dropdown.first_selected_option.text
                    sort_selected = True
                    logger.info(f"Sort selection strategy 1 succeeded: {selected_text}")
                except Exception as e:
                    logger.warning(f"Sort strategy 1 (by name) failed: {e}")
                
                # Strategy 2: Try finding select/combobox by text content
                if not sort_selected:
                    try:
                        from selenium.webdriver.support.ui import Select
                        # Look for select elements containing "Sort By"
                        selects = self.driver.find_elements(By.TAG_NAME, 'select')
                        for select_elem in selects:
                            try:
                                select = Select(select_elem)
                                options = [opt.text for opt in select.options]
                                if any('newest' in opt.lower() for opt in options):
                                    # Found the sort dropdown
                                    for opt in select.options:
                                        if 'newest' in opt.text.lower():
                                            select.select_by_visible_text(opt.text)
                                            selected_text = select.first_selected_option.text
                                            sort_selected = True
                                            logger.info(f"Sort selection strategy 2 succeeded: {selected_text}")
                                            break
                                    if sort_selected:
                                        break
                            except:
                                continue
                    except Exception as e:
                        logger.warning(f"Sort strategy 2 (by text search) failed: {e}")
                
                # Strategy 3: Try clicking on option elements directly
                if not sort_selected:
                    try:
                        # Find option elements containing "newest"
                        options = self.driver.find_elements(By.TAG_NAME, 'option')
                        for option in options:
                            if 'newest' in option.text.lower():
                                option.click()
                                selected_text = option.text
                                sort_selected = True
                                logger.info(f"Sort selection strategy 3 succeeded: {selected_text}")
                                break
                    except Exception as e:
                        logger.warning(f"Sort strategy 3 (direct click) failed: {e}")
            
            # Report sort status
            if sort_selected:
                self._report_progress(f"Sort order set: {selected_text}")
                time.sleep(3)  # Let page reload
            else:
                self._report_progress("Warning: Could not set sort order, proceeding anyway")
            
            urls_with_dates = []
            last_count = 0
            no_new_count = 0
            scroll_attempts = 0
            max_scroll_attempts = 200
            min_date_seen = None  # Track the oldest date we've encountered
            
            self._report_progress(f"Scrolling to find transcripts from {start_date.strftime('%Y-%m-%d')} onwards...")
            
            while scroll_attempts < max_scroll_attempts:
                scroll_attempts += 1
                
                # Find all transcript links (use Playwright if available, else Selenium)
                try:
                    if self.playwright_page:
                        # Wait for page to load and elements to appear
                        try:
                            self.playwright_page.wait_for_selector("a[href*='/factbase/trump/transcript/'], a[href*='/transcript/']", timeout=10000)
                        except:
                            pass  # Continue even if timeout
                        # Playwright approach - try both URL patterns
                        elements1 = self.playwright_page.query_selector_all("a[href*='/factbase/trump/transcript/']")
                        elements2 = self.playwright_page.query_selector_all("a[href*='/transcript/']")
                        # Combine and deduplicate by href
                        seen_hrefs = set()
                        elements = []
                        for elem in elements1 + elements2:
                            try:
                                href = elem.get_attribute('href') or elem.evaluate('el => el.href')
                                if href and href not in seen_hrefs:
                                    seen_hrefs.add(href)
                                    elements.append(elem)
                            except:
                                continue
                        logger.info(f"Found {len(elements)} transcript link elements (Playwright: {len(elements1)} + {len(elements2)})")
                        if scroll_attempts == 1:
                            self._diagnostics.append(f"Playwright found {len(elements1)} with /factbase/trump/transcript/ and {len(elements2)} with /transcript/, {len(elements)} total")
                        sample_hrefs = []
                        for elem in elements:
                            # Playwright ElementHandle.get_attribute() method
                            try:
                                href = elem.get_attribute('href')
                            except Exception as attr_err:
                                # Fallback: use evaluate to get href
                                try:
                                    href = elem.evaluate('el => el.href')
                                except Exception as eval_err:
                                    logger.debug(f"Could not get href: attr_err={attr_err}, eval_err={eval_err}")
                                    continue
                            
                            if not href or '/transcript/' not in href:
                                continue
                            
                            if len(sample_hrefs) < 5:
                                sample_hrefs.append(href)
                            
                            # Extract date from URL
                            date_str = extract_date_from_url(href)
                            if not date_str:
                                if len(sample_hrefs) <= 3:
                                    logger.debug(f"Could not extract date from URL: {href}")
                                continue
                            
                            try:
                                transcript_date = datetime.strptime(date_str, '%Y-%m-%d')
                                
                                # Track the oldest date we've seen
                                if min_date_seen is None or transcript_date < min_date_seen:
                                    min_date_seen = transcript_date
                                
                                # Only collect transcripts in our sync window
                                if start_date <= transcript_date <= end_date:
                                    url_date_tuple = (href, transcript_date)
                                    if url_date_tuple not in urls_with_dates:
                                        urls_with_dates.append(url_date_tuple)
                                elif len(sample_hrefs) <= 3:
                                    logger.debug(f"URL date {transcript_date.strftime('%Y-%m-%d')} outside range {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}: {href}")
                            
                            except Exception as parse_err:
                                if len(sample_hrefs) <= 3:
                                    logger.debug(f"Date parse error for {href}: {parse_err}")
                                continue
                        
                        if scroll_attempts == 1 and len(sample_hrefs) > 0:
                            logger.info(f"Sample URLs found: {sample_hrefs[:3]}")
                    else:
                        # Selenium approach - try both URL patterns
                        elements1 = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/factbase/trump/transcript/']")
                        elements2 = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/transcript/']")
                        # Combine and deduplicate
                        seen_hrefs = set()
                        elements = []
                        for elem in elements1 + elements2:
                            try:
                                href = elem.get_attribute('href')
                                if href and href not in seen_hrefs:
                                    seen_hrefs.add(href)
                                    elements.append(elem)
                            except:
                                continue
                        logger.info(f"Found {len(elements)} transcript link elements (Selenium)")
                        if scroll_attempts == 1:
                            self._diagnostics.append(f"Selenium found {len(elements1)} with /factbase/trump/transcript/ and {len(elements2)} with /transcript/, {len(elements)} total after dedup")
                        sample_hrefs = []
                        for elem in elements:
                            href = elem.get_attribute('href')
                            if not href or ('/transcript/' not in href and '/factbase/trump/transcript/' not in href):
                                continue
                            
                            if len(sample_hrefs) < 5:
                                sample_hrefs.append(href)
                            
                            # Extract date from URL
                            date_str = extract_date_from_url(href)
                            if not date_str:
                                if len(sample_hrefs) <= 3:
                                    logger.debug(f"Could not extract date from URL: {href}")
                                continue
                            
                            try:
                                transcript_date = datetime.strptime(date_str, '%Y-%m-%d')
                                
                                # Track the oldest date we've seen
                                if min_date_seen is None or transcript_date < min_date_seen:
                                    min_date_seen = transcript_date
                                
                                # Only collect transcripts in our sync window
                                if start_date <= transcript_date <= end_date:
                                    url_date_tuple = (href, transcript_date)
                                    if url_date_tuple not in urls_with_dates:
                                        urls_with_dates.append(url_date_tuple)
                                elif len(sample_hrefs) <= 3:
                                    logger.debug(f"URL date {transcript_date.strftime('%Y-%m-%d')} outside range {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}: {href}")
                            
                            except Exception as parse_err:
                                if len(sample_hrefs) <= 3:
                                    logger.debug(f"Date parse error for {href}: {parse_err}")
                                continue
                        
                        if scroll_attempts == 1 and len(sample_hrefs) > 0:
                            logger.info(f"Sample URLs found: {sample_hrefs[:3]}")
                
                except Exception as e:
                    logger.error(f"Error finding elements: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                
                # Check if we found new URLs
                if len(urls_with_dates) == last_count:
                    no_new_count += 1
                    # Stop if: (1) we've seen dates older than start_date AND (2) no new URLs for 10 scrolls
                    # BUT: Don't stop if we haven't seen any dates yet (page might not be loaded)
                    if no_new_count >= 10:
                        if min_date_seen:
                            if min_date_seen < start_date:
                                logger.info(f"No new URLs after 10 scrolls and reached dates before {start_date.strftime('%Y-%m-%d')} (saw {min_date_seen.strftime('%Y-%m-%d')}), stopping")
                                self._diagnostics.append(f"Stopped: saw date {min_date_seen.strftime('%Y-%m-%d')} before start {start_date.strftime('%Y-%m-%d')}")
                            else:
                                logger.info(f"No new URLs after 10 scrolls but dates are still >= {start_date.strftime('%Y-%m-%d')} (saw {min_date_seen.strftime('%Y-%m-%d')}), continuing...")
                                no_new_count = 0  # Reset counter, keep scrolling
                        else:
                            logger.warning(f"No new URLs after 10 scrolls and no dates seen yet - page may not be loading correctly")
                            self._diagnostics.append("Stopped: no dates seen after 10 scrolls")
                            break
                else:
                    no_new_count = 0
                    last_count = len(urls_with_dates)
                
                # Progress update every 10 scrolls
                if scroll_attempts % 10 == 0:
                    min_date_str = min_date_seen.strftime('%Y-%m-%d') if min_date_seen else 'N/A'
                    self._report_progress(
                        f"Scrolling... found {len(urls_with_dates)} URLs (oldest: {min_date_str})", 
                        discovered=len(urls_with_dates)
                    )
                
                # Scroll down (use Playwright if available, else Selenium)
                if self.playwright_page:
                    self.playwright_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)
                else:
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
            List of (url, date) tuples that need to be scraped or re-normalized
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
                # Exists - check if it needs updating
                transcript_id, word_count, full_dialogue = row
                
                needs_rescrape = False
                
                # Check 1: Empty or broken content
                if not word_count or word_count == 0 or not full_dialogue or full_dialogue.strip() == '':
                    needs_rescrape = True
                    logger.info(f"Re-scraping (empty content): {url}")
                
                # Check 2: Has formatting artifacts that need normalization
                elif full_dialogue:
                    # Check for numeric suffixes in speaker labels: "Donald Trump 00"
                    if re.search(r'(Donald Trump|Trump)\s+\d{1,2}\s*\n', full_dialogue):
                        needs_rescrape = True
                        logger.info(f"Re-scraping (speaker format): {url}")
                    
                    # Check for signal rating blocks
                    elif re.search(r'signal\s+rating', full_dialogue, re.IGNORECASE):
                        needs_rescrape = True
                        logger.info(f"Re-scraping (signal rating artifact): {url}")
                    
                    # Check for timestamps in speaker lines: "Donald Trump (00:10:12)"
                    elif re.search(r'(Donald Trump|Trump)\s*\([0-9:]+\)', full_dialogue):
                        needs_rescrape = True
                        logger.info(f"Re-scraping (timestamp format): {url}")
                
                if needs_rescrape:
                    to_scrape.append((url, date))
        
        conn.close()
        
        logger.info(f"Filtered to {len(to_scrape)} URLs that need scraping (out of {len(discovered_urls)} discovered)")
        return to_scrape
    
    def _parse_transcript_page(self, url: str, date: datetime) -> Optional[Dict]:
        """Parse a single transcript page"""
        try:
            # Use Playwright if available, else Selenium
            if self.playwright_page:
                self.playwright_page.goto(url, wait_until='networkidle', timeout=30000)
                page_source = self.playwright_page.content()
                # Extract title
                try:
                    title_elem = self.playwright_page.query_selector('h1')
                    title = title_elem.inner_text() if title_elem else url.split('/')[-1].replace('-', ' ').title()
                except:
                    title = url.split('/')[-1].replace('-', ' ').title()
            else:
                if not self.driver:
                    logger.error("No browser driver available for parsing")
                    return None
                self.driver.get(url)
                wait = WebDriverWait(self.driver, 20)
                page_source = self.driver.page_source
                # Extract title (Selenium)
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
            
            if HAS_SCRAPER_UTILS and self.driver:
                extractor = DialogueExtractor(self.driver, selectors=CONTENT_SELECTORS)
                dialogue_sections = extractor.extract_dialogue(min_content_length=200)
            elif self.playwright_page:
                # For Playwright, use BeautifulSoup to parse HTML
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(page_source, 'html.parser')
                # Try to find transcript content area
                transcript_elem = (soup.find(class_='transcript-content') or 
                                 soup.find(class_='transcript-text') or
                                 soup.find('article') or 
                                 soup.find('main'))
                if transcript_elem:
                    # Simple parsing - look for speaker patterns
                    text = transcript_elem.get_text()
                    lines = text.split('\n')
                    current_speaker = None
                    current_text = []
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        # Check if line looks like a speaker name
                        if re.match(r'^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}$', line) and len(line.split()) <= 4:
                            if current_speaker and current_text:
                                dialogue_sections.append({
                                    'speaker': current_speaker,
                                    'text': ' '.join(current_text),
                                    'timestamp': ''
                                })
                            current_speaker = line
                            current_text = []
                        else:
                            if current_speaker:
                                current_text.append(line)
                    if current_speaker and current_text:
                        dialogue_sections.append({
                            'speaker': current_speaker,
                            'text': ' '.join(current_text),
                            'timestamp': ''
                        })
            
            if not dialogue_sections:
                logger.warning(f"No dialogue found for {url}")
                return None
            
            # Normalize transcript format (clean speaker labels, remove artifacts)
            full_dialogue_text, speakers_json, total_word_count, trump_word_count, norm_stats = \
                normalize_transcript_format(dialogue_sections)
            
            # Track normalization stats
            if hasattr(self, '_current_sync_stats'):
                self._current_sync_stats['speaker_labels_normalized'] += norm_stats.get('speaker_labels_normalized', 0)
                self._current_sync_stats['signal_rating_blocks'] += norm_stats.get('signal_rating_blocks', 0)
                self._current_sync_stats['boilerplate_lines'] += norm_stats.get('boilerplate_lines', 0)
                self._current_sync_stats['timestamp_lines'] += norm_stats.get('timestamp_lines', 0)
                self._current_sync_stats['rating_lines'] += norm_stats.get('rating_lines', 0)
                self._current_sync_stats['annotations_removed'] += norm_stats.get('annotations_removed', 0)
            
            # Extract duration if available (page_source already set above)
            duration = self._extract_duration(page_source)
            
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
                'speakers_json': speakers_json
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
        
        # Initialize normalization stats tracker
        self._current_sync_stats = {
            'speaker_labels_normalized': 0,
            'signal_rating_blocks': 0,
            'boilerplate_lines': 0,
            'timestamp_lines': 0,
            'rating_lines': 0,
            'annotations_removed': 0
        }
        
        try:
            # Step 1: Determine sync window
            self._report_progress("Determining sync window...")
            start_date, end_date = self._get_sync_window()
            summary.start_date = start_date.strftime('%Y-%m-%d')
            summary.end_date = end_date.strftime('%Y-%m-%d')
            
            # Step 2: Initialize Selenium
            self._report_progress("Initializing browser...")
            if not self._init_driver():
                error_msg = "Failed to initialize Chrome driver"
                if self._last_error:
                    error_msg += f": {self._last_error}"
                summary.error = error_msg
                logger.error(f"Sync failed: {error_msg}")
                self._report_progress(f"Error: {error_msg}")
                return summary
            
            # Step 3: Discover URLs in range
            self._report_progress(f"Discovering transcripts from {summary.start_date} to {summary.end_date}...")
            discovered_urls = self._discover_urls_in_range(start_date, end_date)
            summary.total_discovered = len(discovered_urls)
            
            if not discovered_urls:
                error_msg = "No transcripts discovered in date range"
                if self._last_error:
                    error_msg += f" (Browser error: {self._last_error})"
                if self._diagnostics:
                    # Include ALL diagnostics to see what's happening
                    error_msg += f" (Diagnostics: {'; '.join(self._diagnostics)})"
                else:
                    error_msg += " (No diagnostics - page may not have loaded)"
                self._report_progress(error_msg)
                summary.error = error_msg
                logger.warning(error_msg)
                if self._diagnostics:
                    logger.warning(f"Full diagnostics list ({len(self._diagnostics)} items): {self._diagnostics}")
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
            
            # Copy normalization stats to summary
            summary.speaker_labels_normalized = self._current_sync_stats['speaker_labels_normalized']
            summary.signal_rating_blocks_removed = self._current_sync_stats['signal_rating_blocks']
            summary.boilerplate_lines_removed = self._current_sync_stats['boilerplate_lines']
            summary.timestamp_lines_removed = self._current_sync_stats['timestamp_lines']
            summary.rating_lines_removed = self._current_sync_stats['rating_lines']
            summary.annotations_removed = self._current_sync_stats['annotations_removed']
            
            # Final summary
            self._report_progress(
                f"Sync complete! Added: {summary.added}, Updated: {summary.updated}, Failed: {summary.failed}",
                added=summary.added,
                updated=summary.updated,
                failed=summary.failed,
                total=len(urls_to_scrape),
                speaker_labels_normalized=summary.speaker_labels_normalized,
                timestamp_lines_removed=summary.timestamp_lines_removed,
                rating_lines_removed=summary.rating_lines_removed,
                signal_rating_blocks_removed=summary.signal_rating_blocks_removed,
                boilerplate_lines_removed=summary.boilerplate_lines_removed,
                annotations_removed=summary.annotations_removed
            )
            
        except Exception as e:
            logger.error(f"Sync error: {e}")
            summary.error = str(e)
        
        finally:
            # Cleanup - use try-except for each to handle any AttributeError
            try:
                if hasattr(self, 'playwright_browser') and self.playwright_browser:
                    try:
                        self.playwright_browser.close()
                    except:
                        pass
            except AttributeError:
                pass
            except:
                pass
            
            try:
                if hasattr(self, 'playwright_context') and self.playwright_context:
                    try:
                        self.playwright_context.stop()
                    except:
                        pass
            except AttributeError:
                pass
            except:
                pass
            
            try:
                if hasattr(self, 'driver') and self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
            except AttributeError:
                pass
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
    print(f"\nNormalization Stats:")
    print(f"  Speaker labels normalized: {summary.speaker_labels_normalized}")
    print(f"  Timestamp lines removed: {summary.timestamp_lines_removed}")
    print(f"  Rating lines removed: {summary.rating_lines_removed}")
    print(f"  Signal rating blocks removed: {summary.signal_rating_blocks_removed}")
    print(f"  Boilerplate lines removed: {summary.boilerplate_lines_removed}")
    print(f"  Annotations removed: {summary.annotations_removed}")
    if summary.error:
        print(f"\nError: {summary.error}")
    print("="*80)




