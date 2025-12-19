#!/usr/bin/env python3
"""
Shared scraper utilities for RollCall transcript extraction
Provides reusable selector fallback logic and retry mechanisms
"""

import time
import re
import logging
from typing import List, Dict, Optional
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

logger = logging.getLogger(__name__)

# Comprehensive list of CSS selectors for transcript content (in priority order)
CONTENT_SELECTORS = [
    ".transcript-content",
    ".transcript-text",
    ".transcript-body",
    "#transcript-content",
    ".full-transcript",
    "[data-transcript]",
    ".speaker-section",
    "article.transcript",
    "article",
    "main.transcript",
    "main",
    ".content-body",
    ".content",
    "#transcript",
    "#content",
    "body"  # Last resort
]

# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAYS = [3, 5, 8]  # Seconds to wait between retries


class DialogueExtractor:
    """Robust dialogue extraction with multiple fallback strategies"""
    
    def __init__(self, driver, selectors=None):
        """
        Initialize extractor
        
        Args:
            driver: Selenium WebDriver instance
            selectors: Optional custom list of CSS selectors (uses CONTENT_SELECTORS if None)
        """
        self.driver = driver
        self.selectors = selectors or CONTENT_SELECTORS
    
    def extract_dialogue(self, min_content_length: int = 200) -> List[Dict]:
        """
        Extract dialogue using multiple strategies
        
        Args:
            min_content_length: Minimum character length for valid content
        
        Returns:
            List of {speaker, text, timestamp} dicts
        """
        dialogue = []
        
        # Strategy 1: Try each content selector
        for selector in self.selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = elem.text.strip()
                
                # Must have substantial text
                if len(text) < min_content_length:
                    continue
                
                logger.info(f"Using selector: {selector}")
                
                # Try to parse speaker sections from text
                dialogue = self._parse_speaker_sections(text)
                
                if dialogue and len(dialogue) > 0:
                    logger.info(f"Extracted {len(dialogue)} dialogue sections")
                    return dialogue
                    
            except NoSuchElementException:
                continue
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        # Strategy 2: Look for paragraph elements with speaker patterns
        try:
            paragraphs = self.driver.find_elements(By.TAG_NAME, 'p')
            dialogue = self._extract_from_paragraphs(paragraphs)
            if dialogue:
                logger.info(f"Extracted {len(dialogue)} sections from paragraphs")
                return dialogue
        except Exception as e:
            logger.debug(f"Paragraph extraction failed: {e}")
        
        # Strategy 3: Get all text from body and parse
        try:
            body = self.driver.find_element(By.TAG_NAME, 'body')
            text = body.text.strip()
            dialogue = self._parse_speaker_sections(text)
            if dialogue:
                logger.info(f"Extracted {len(dialogue)} sections from body")
                return dialogue
        except Exception as e:
            logger.debug(f"Body extraction failed: {e}")
        
        logger.warning("No dialogue sections found with any strategy")
        return []
    
    def _parse_speaker_sections(self, text: str) -> List[Dict]:
        """
        Parse RollCall transcript format into speaker sections
        
        RollCall Format Pattern:
        Donald Trump 00
        00:00-00:00:10 (10 sec)
        
        NO STRESSLENS: or NO SIGNAL (0.125):
        Actual dialogue text here...
        
        This parser STRICTLY extracts only speaker names and dialogue,
        stripping ALL metadata (timestamps, ratings, numeric suffixes).
        """
        dialogue = []
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Skip header/boilerplate
            if any(keyword in line for keyword in [
                'StressLens', 'Topics', 'Entities', 'Moderation', 'Speakers', 
                'Full Transcript:', 'CAPITOL HILL SINCE', 'About Contact Us',
                'CQ and Roll Call', 'FiscalNote'
            ]):
                i += 1
                continue
            
            # Check if this line is a speaker name
            # RollCall format: "Name Name 00" or "Name Name"
            # Typically 2-4 words, title case, may have " 00" suffix
            is_speaker_line = False
            clean_speaker = None
            
            # Pattern 1: Name with numeric suffix (RollCall specific)
            if re.match(r'^[A-Z][a-zA-Z\s\.]+\s+\d{1,2}$', line):
                # e.g., "Donald Trump 00" or "Mark Levin 00"
                clean_speaker = re.sub(r'\s+\d{1,2}$', '', line).strip()
                is_speaker_line = True
            
            # Pattern 2: Title case name (2-4 words, no numbers)
            elif re.match(r'^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}$', line):
                # e.g., "Donald Trump" or "Mark Levin"
                clean_speaker = line.strip()
                is_speaker_line = True
            
            if is_speaker_line and clean_speaker:
                # Found a speaker line, now extract their dialogue
                i += 1
                
                # Skip timestamp line (format: 00:00-00:00:10 (10 sec))
                if i < len(lines) and re.match(r'^\d{1,2}:\d{2}-\d{1,2}:\d{2}:\d{2}', lines[i]):
                    i += 1
                
                # Skip blank lines
                while i < len(lines) and not lines[i].strip():
                    i += 1
                
                # Skip rating line (NO STRESSLENS:, NO SIGNAL (0.123):, MEDIUM (1.5):, WEAK (1.0):)
                if i < len(lines):
                    rating_line = lines[i].strip()
                    if re.match(r'^(NO STRESSLENS|NO SIGNAL|MEDIUM|WEAK|STRONG|HIGH)(\s*\([0-9\.]+\))?:', rating_line):
                        i += 1
                
                # Now collect actual dialogue text until next speaker
                dialogue_lines = []
                while i < len(lines):
                    potential_line = lines[i].strip()
                    
                    # Stop if we hit another speaker line
                    if re.match(r'^[A-Z][a-zA-Z\s\.]+\s+\d{1,2}$', potential_line):
                        break
                    if re.match(r'^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}$', potential_line) and \
                       i + 1 < len(lines) and re.match(r'^\d{1,2}:\d{2}-', lines[i + 1]):
                        break
                    
                    # Skip metadata lines
                    if re.match(r'^\d{1,2}:\d{2}-\d{1,2}:\d{2}:\d{2}', potential_line):
                        i += 1
                        continue
                    if re.match(r'^(NO STRESSLENS|NO SIGNAL|MEDIUM|WEAK|STRONG|HIGH)(\s*\([0-9\.]+\))?:', potential_line):
                        i += 1
                        continue
                    if not potential_line:
                        i += 1
                        continue
                    
                    # This is actual dialogue
                    dialogue_lines.append(potential_line)
                    i += 1
                
                # Save this speaker's dialogue
                if dialogue_lines:
                    dialogue_text = ' '.join(dialogue_lines)
                    # Remove inline annotations like [Inaudible], [Audience members call out...], [Laughter], [Crosstalk]
                    dialogue_text = re.sub(r'\[.*?\]', '', dialogue_text)
                    # Clean up extra spaces
                    dialogue_text = ' '.join(dialogue_text.split())
                    
                    if dialogue_text.strip():
                        dialogue.append({
                            'speaker': clean_speaker,
                            'text': dialogue_text,
                            'timestamp': ''
                        })
            else:
                i += 1
        
        return dialogue
    
    def _extract_from_paragraphs(self, paragraphs) -> List[Dict]:
        """Extract dialogue from paragraph elements"""
        dialogue = []
        
        for p in paragraphs:
            text = p.text.strip()
            if not text or len(text) < 10:
                continue
            
            # Look for speaker pattern in paragraph
            if ':' in text:
                parts = text.split(':', 1)
                if len(parts[0].split()) <= 4:
                    dialogue.append({
                        'speaker': parts[0].strip(),
                        'text': parts[1].strip(),
                        'timestamp': ''
                    })
        
        return dialogue


class RetryHelper:
    """Helper for retry logic with exponential backoff"""
    
    @staticmethod
    def retry_with_backoff(func, max_retries=DEFAULT_MAX_RETRIES, 
                          delays=None, error_msg="Operation"):
        """
        Retry a function with configurable delays
        
        Args:
            func: Function to retry (should return (success, result) tuple)
            max_retries: Maximum number of attempts
            delays: List of delays in seconds (uses DEFAULT_RETRY_DELAYS if None)
            error_msg: Description for logging
        
        Returns:
            (success, result) tuple
        """
        if delays is None:
            delays = DEFAULT_RETRY_DELAYS
        
        for attempt in range(1, max_retries + 1):
            logger.info(f"{error_msg} - Attempt {attempt}/{max_retries}")
            
            try:
                success, result = func()
                
                if success:
                    logger.info(f"{error_msg} succeeded on attempt {attempt}")
                    return True, result
                else:
                    logger.warning(f"{error_msg} returned failure on attempt {attempt}")
                    
            except Exception as e:
                logger.error(f"{error_msg} failed on attempt {attempt}: {e}")
            
            # Wait before retry (if not last attempt)
            if attempt < max_retries:
                delay = delays[attempt - 1] if attempt - 1 < len(delays) else delays[-1]
                logger.info(f"Waiting {delay}s before retry...")
                time.sleep(delay)
        
        logger.error(f"{error_msg} failed after {max_retries} attempts")
        return False, None


def build_dialogue_text(sections: List[Dict]) -> str:
    """
    Build full dialogue text from sections
    
    Args:
        sections: List of {speaker, text, timestamp} dicts
    
    Returns:
        Formatted dialogue text
    """
    lines = []
    
    for section in sections:
        speaker = section.get('speaker', 'Unknown')
        text = section.get('text', '')
        timestamp = section.get('timestamp', '')
        
        if timestamp:
            lines.append(f"{speaker} ({timestamp})")
        else:
            lines.append(speaker)
        
        lines.append(text)
        lines.append('')  # Blank line between sections
    
    return '\n'.join(lines)


def validate_transcript_content(dialogue_text: str, min_words: int = 100) -> bool:
    """
    Validate that transcript content meets minimum requirements
    
    Args:
        dialogue_text: Full dialogue text
        min_words: Minimum word count
    
    Returns:
        True if valid, False otherwise
    """
    if not dialogue_text or not dialogue_text.strip():
        logger.warning("Dialogue text is empty")
        return False
    
    word_count = len(dialogue_text.split())
    
    if word_count < min_words:
        logger.warning(f"Dialogue too short: {word_count} words (minimum {min_words})")
        return False
    
    logger.info(f"Dialogue validation passed: {word_count} words")
    return True


def extract_date_from_url(url: str) -> Optional[str]:
    """
    Extract date from RollCall URL
    
    Args:
        url: RollCall transcript URL
    
    Returns:
        Date string in YYYY-MM-DD format, or None if not found
    """
    # Pattern 1: month-day-year (e.g., january-7-2025)
    month_pattern = r'-(january|february|march|april|may|june|july|august|september|october|november|december)-(\d{1,2})-(\d{4})'
    match = re.search(month_pattern, url, re.IGNORECASE)
    
    if match:
        month_name = match.group(1).lower()
        day = int(match.group(2))
        year = int(match.group(3))
        
        month_map = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        month = month_map.get(month_name)
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"
    
    # Pattern 2: YYYY-MM-DD
    date_pattern = r'-(\d{4})-(\d{2})-(\d{2})'
    match = re.search(date_pattern, url)
    
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    
    return None


def normalize_url(url: str) -> str:
    """
    Normalize URL for comparison
    
    Args:
        url: URL to normalize
    
    Returns:
        Normalized URL (stripped, trailing slash removed)
    """
    url = url.strip()
    if url.endswith('/'):
        url = url[:-1]
    return url

