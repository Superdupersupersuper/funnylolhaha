#!/usr/bin/env python3
"""
Fix Missing Transcripts Script
Re-scrapes transcripts with word_count = 0 using robust selector fallback logic

Usage:
    # Test on single transcript (ID 1765):
    python3 fix_missing_transcripts.py --test-id 1765
    
    # Fix all missing transcripts:
    python3 fix_missing_transcripts.py --all
    
    # Fix specific transcript by URL:
    python3 fix_missing_transcripts.py --url "https://rollcall.com/..."
"""

import sqlite3
import sys
import argparse
import time
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

DB_PATH = 'data/transcripts.db'

class Colors:
    """ANSI color codes"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.END}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

class TranscriptFixer:
    """Robust transcript scraper with multiple selector fallbacks"""
    
    # Comprehensive list of CSS selectors to try (in priority order)
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
    
    def __init__(self, headless: bool = True):
        self.driver = None
        self.headless = headless
        
    def init_driver(self):
        """Initialize Selenium WebDriver"""
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        try:
            self.driver = webdriver.Chrome(options=options)
            print_success("WebDriver initialized")
            return True
        except Exception as e:
            print_error(f"Failed to initialize WebDriver: {e}")
            return False
    
    def close_driver(self):
        """Close WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def scrape_transcript(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """
        Scrape a single transcript with retry logic
        
        Returns:
            Dict with 'full_dialogue' and 'word_count', or None if failed
        """
        for attempt in range(1, max_retries + 1):
            print(f"  Attempt {attempt}/{max_retries}...")
            
            try:
                # Load page
                self.driver.get(url)
                
                # Try different wait times
                wait_time = 3 + (attempt * 2)  # 5s, 7s, 9s
                time.sleep(wait_time)
                
                # Extract dialogue with multiple selector attempts
                dialogue_sections = self._extract_dialogue_robust()
                
                if dialogue_sections and len(dialogue_sections) > 0:
                    # Build full dialogue text
                    full_dialogue = self._build_dialogue_text(dialogue_sections)
                    word_count = len(full_dialogue.split())
                    
                    # Validate: must have substantial content
                    if word_count >= 100:  # At least 100 words
                        print_success(f"Extracted {word_count} words, {len(dialogue_sections)} sections")
                        return {
                            'full_dialogue': full_dialogue,
                            'word_count': word_count
                        }
                    else:
                        print_warning(f"Content too short ({word_count} words), retrying...")
                else:
                    print_warning("No dialogue sections found, retrying...")
                
                # Wait before retry
                if attempt < max_retries:
                    time.sleep(2)
                    
            except Exception as e:
                print_error(f"Error on attempt {attempt}: {e}")
                if attempt < max_retries:
                    time.sleep(3)
        
        print_error(f"Failed after {max_retries} attempts")
        return None
    
    def _extract_dialogue_robust(self) -> List[Dict]:
        """
        Extract dialogue using multiple strategies
        
        Returns:
            List of {speaker, text, timestamp} dicts
        """
        dialogue = []
        
        # Strategy 1: Try each content selector
        for selector in self.CONTENT_SELECTORS:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = elem.text.strip()
                
                # Must have substantial text
                if len(text) < 200:
                    continue
                
                print(f"    Using selector: {selector}")
                
                # Try to parse speaker sections from text
                dialogue = self._parse_speaker_sections(text)
                
                if dialogue and len(dialogue) > 0:
                    return dialogue
                    
            except NoSuchElementException:
                continue
            except Exception as e:
                continue
        
        # Strategy 2: Look for paragraph elements with speaker patterns
        try:
            paragraphs = self.driver.find_elements(By.TAG_NAME, 'p')
            dialogue = self._extract_from_paragraphs(paragraphs)
            if dialogue:
                return dialogue
        except:
            pass
        
        # Strategy 3: Get all text from body and parse
        try:
            body = self.driver.find_element(By.TAG_NAME, 'body')
            text = body.text.strip()
            dialogue = self._parse_speaker_sections(text)
            if dialogue:
                return dialogue
        except:
            pass
        
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
            if line.isupper() and len(line.split()) <= 4:
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
    
    def _build_dialogue_text(self, sections: List[Dict]) -> str:
        """Build full dialogue text from sections"""
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

def get_missing_transcripts(conn: sqlite3.Connection) -> List[Tuple[int, str, str, str]]:
    """
    Get all transcripts with word_count = 0
    
    Returns:
        List of (id, url, title, date) tuples
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, date
        FROM transcripts
        WHERE word_count = 0 OR full_dialogue = '' OR full_dialogue IS NULL
        ORDER BY date DESC
    """)
    return cursor.fetchall()

def update_transcript(conn: sqlite3.Connection, transcript_id: int, full_dialogue: str, word_count: int):
    """Update transcript in database"""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE transcripts
        SET full_dialogue = ?, word_count = ?
        WHERE id = ?
    """, (full_dialogue, word_count, transcript_id))
    conn.commit()

def fix_single_transcript(fixer: TranscriptFixer, conn: sqlite3.Connection, 
                         transcript_id: int, url: str, title: str) -> bool:
    """
    Fix a single transcript
    
    Returns:
        True if successful, False otherwise
    """
    print_header(f"Fixing Transcript ID {transcript_id}")
    print(f"Title: {title}")
    print(f"URL: {url}")
    
    result = fixer.scrape_transcript(url)
    
    if result:
        update_transcript(conn, transcript_id, result['full_dialogue'], result['word_count'])
        print_success(f"Updated database: {result['word_count']} words")
        return True
    else:
        print_error("Failed to scrape transcript")
        return False

def main():
    parser = argparse.ArgumentParser(description='Fix missing transcripts')
    parser.add_argument('--test-id', type=int, help='Test on single transcript ID')
    parser.add_argument('--url', help='Fix specific URL')
    parser.add_argument('--all', action='store_true', help='Fix all missing transcripts')
    parser.add_argument('--headless', action='store_true', default=True, help='Run browser in headless mode')
    
    args = parser.parse_args()
    
    if not any([args.test_id, args.url, args.all]):
        parser.print_help()
        sys.exit(1)
    
    # Connect to database
    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.Error as e:
        print_error(f"Failed to connect to database: {e}")
        sys.exit(1)
    
    # Initialize fixer
    fixer = TranscriptFixer(headless=args.headless)
    if not fixer.init_driver():
        sys.exit(1)
    
    try:
        if args.test_id:
            # Test single transcript by ID
            cursor = conn.cursor()
            cursor.execute("SELECT id, url, title, date FROM transcripts WHERE id = ?", (args.test_id,))
            row = cursor.fetchone()
            
            if not row:
                print_error(f"Transcript ID {args.test_id} not found")
                sys.exit(1)
            
            success = fix_single_transcript(fixer, conn, row[0], row[1], row[2])
            sys.exit(0 if success else 1)
        
        elif args.url:
            # Fix specific URL
            cursor = conn.cursor()
            cursor.execute("SELECT id, url, title, date FROM transcripts WHERE url = ?", (args.url,))
            row = cursor.fetchone()
            
            if not row:
                print_error(f"URL not found in database: {args.url}")
                sys.exit(1)
            
            success = fix_single_transcript(fixer, conn, row[0], row[1], row[2])
            sys.exit(0 if success else 1)
        
        elif args.all:
            # Fix all missing transcripts
            missing = get_missing_transcripts(conn)
            
            if not missing:
                print_success("No missing transcripts found!")
                sys.exit(0)
            
            print_header(f"Found {len(missing)} Missing Transcripts")
            
            success_count = 0
            failed = []
            
            for i, (transcript_id, url, title, date) in enumerate(missing, 1):
                print(f"\n[{i}/{len(missing)}] Processing ID {transcript_id}...")
                print(f"  Date: {date}")
                print(f"  Title: {title[:60]}...")
                
                if fix_single_transcript(fixer, conn, transcript_id, url, title):
                    success_count += 1
                else:
                    failed.append((transcript_id, url, title))
                
                # Rate limiting
                time.sleep(2)
            
            # Summary
            print_header("SUMMARY")
            print(f"Total: {len(missing)}")
            print(f"Success: {success_count}")
            print(f"Failed: {len(failed)}")
            
            if failed:
                print("\nFailed transcripts:")
                for tid, url, title in failed:
                    print(f"  - ID {tid}: {title[:50]}")
                    print(f"    {url}")
            
            sys.exit(0 if len(failed) == 0 else 1)
    
    finally:
        fixer.close_driver()
        conn.close()

if __name__ == '__main__':
    main()
