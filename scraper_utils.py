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
        Parse text into speaker sections
        
        Handles formats like:
        - SPEAKER NAME: text
        - Speaker Name\ntext
        - Speaker Name (timestamp)\ntext
        """
        dialogue = []
        lines = text.split('\n')
        
        current_speaker = None
        current_text = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line is a speaker name
            # Pattern 1: "NAME:" or "NAME (timestamp):"
            if ':' in line:
                parts = line.split(':', 1)
                potential_speaker = parts[0].strip()
                
                # Speaker names are typically short (1-4 words)
                if len(potential_speaker.split()) <= 4:
                    # Save previous speaker's text
                    if current_speaker and current_text:
                        dialogue.append({
                            'speaker': current_speaker,
                            'text': ' '.join(current_text),
                            'timestamp': ''
                        })
                    
                    # Start new speaker
                    current_speaker = potential_speaker
                    remaining_text = parts[1].strip() if len(parts) > 1 else ''
                    current_text = [remaining_text] if remaining_text else []
                    continue
            
            # Pattern 2: ALL CAPS line (likely speaker)
            if line.isupper() and len(line.split()) <= 4 and len(line) > 2:
                # Save previous
                if current_speaker and current_text:
                    dialogue.append({
                        'speaker': current_speaker,
                        'text': ' '.join(current_text),
                        'timestamp': ''
                    })
                
                current_speaker = line
                current_text = []
                continue
            
            # Otherwise, it's dialogue text
            if current_speaker:
                current_text.append(line)
        
        # Don't forget last speaker
        if current_speaker and current_text:
            dialogue.append({
                'speaker': current_speaker,
                'text': ' '.join(current_text),
                'timestamp': ''
            })
        
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

