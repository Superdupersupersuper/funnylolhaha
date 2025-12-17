"""
Mention Markets - Factbase Transcript Scraper
Scrapes transcripts from Roll Call Factbase
"""

import re
import json
import time
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

# For running locally, you'll need:
# pip install requests beautifulsoup4 lxml aiohttp

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: requests/beautifulsoup4 not installed. Run: pip install requests beautifulsoup4 lxml")


@dataclass
class TranscriptSegment:
    speaker: str
    start_time: str
    end_time: str
    duration_seconds: int
    text: str
    sentiment_vader: float = None
    sentiment_label: str = None
    topics: List[str] = None
    headshot_url: str = None


@dataclass  
class Transcript:
    id: str
    url: str
    title: str
    primary_speaker: str
    event_type: str
    event_date: str
    location: str
    segments: List[TranscriptSegment]
    topics: List[str] = None
    entities: List[str] = None
    raw_html: str = None


class FactbaseScraper:
    """Scraper for Roll Call Factbase transcripts."""
    
    BASE_URL = "https://rollcall.com/factbase"
    
    # Known transcript listing pages
    TRANSCRIPT_SOURCES = {
        'trump': '/trump/transcripts/',
        'biden': '/biden/transcripts/',
        'harris': '/harris/transcripts/',
    }
    
    # Headers to mimic a browser
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }
    
    def __init__(self, delay_between_requests: float = 1.0):
        self.delay = delay_between_requests
        self.session = requests.Session() if HAS_REQUESTS else None
        if self.session:
            self.session.headers.update(self.HEADERS)
    
    def _get_page(self, url: str) -> Optional[str]:
        """Fetch a page with rate limiting."""
        if not self.session:
            raise RuntimeError("requests library not available")
        
        time.sleep(self.delay)
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def get_transcript_urls_from_search(self, person: str = 'trump', max_pages: int = 50) -> List[str]:
        """
        Get transcript URLs from Factbase search/listing pages.
        Note: The actual data is loaded via JavaScript, so this requires 
        either Selenium or finding their API endpoint.
        """
        urls = []
        
        # Known transcript URL patterns from search results
        # These can be discovered by examining the page source
        print(f"Fetching transcript list for {person}...")
        
        # The search page uses JavaScript to load results
        # We need to either:
        # 1. Use Selenium/Playwright for JS rendering
        # 2. Find their underlying API endpoint
        # 3. Manually compile a list of known transcripts
        
        return urls
    
    def parse_transcript_page(self, html: str, url: str) -> Optional[Transcript]:
        """Parse a transcript page HTML into structured data."""
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Extract title
        title_elem = soup.find('h1')
        if not title_elem:
            print(f"Could not find title for {url}")
            return None
        
        title = title_elem.get_text(strip=True)
        
        # Parse title for metadata
        # Format: "Speech: Donald Trump Holds a Political Rally in Washington - January 19, 2025"
        title_parts = self._parse_title(title)
        
        # Generate ID from URL
        transcript_id = self._url_to_id(url)
        
        # Extract speakers section
        speakers_data = self._extract_speakers(soup)
        
        # Extract segments (the actual transcript)
        segments = self._extract_segments(soup, speakers_data)
        
        # Extract topics
        topics = self._extract_topics(soup)
        
        # Extract entities
        entities = self._extract_entities(soup)
        
        if not segments:
            print(f"No segments found for {url}")
            return None
        
        # Determine primary speaker (most words spoken)
        primary_speaker = max(
            speakers_data.keys(),
            key=lambda s: speakers_data.get(s, {}).get('words', 0),
            default='Unknown'
        )
        
        return Transcript(
            id=transcript_id,
            url=url,
            title=title,
            primary_speaker=primary_speaker,
            event_type=title_parts.get('event_type', 'Unknown'),
            event_date=title_parts.get('date', ''),
            location=title_parts.get('location', ''),
            segments=segments,
            topics=topics,
            entities=entities,
            raw_html=html
        )
    
    def _parse_title(self, title: str) -> Dict:
        """Parse transcript title for metadata."""
        result = {
            'event_type': None,
            'location': None,
            'date': None
        }
        
        # Common patterns:
        # "Speech: Donald Trump Holds a Political Rally in Washington - January 19, 2025"
        # "Press Briefing: Karoline Leavitt Holds a Press Briefing at The White House - January 28, 2025"
        # "Interview: JD Vance on Fox News - September 6, 2025"
        
        # Extract event type (before the colon)
        if ':' in title:
            result['event_type'] = title.split(':')[0].strip()
        
        # Extract date (after the last dash)
        date_match = re.search(r'-\s*(\w+\s+\d+,?\s*\d{4})\s*$', title)
        if date_match:
            date_str = date_match.group(1)
            try:
                # Parse various date formats
                for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y']:
                    try:
                        dt = datetime.strptime(date_str.strip(), fmt)
                        result['date'] = dt.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        
        # Extract location (typically "in <Location>" pattern)
        location_match = re.search(r'\s+in\s+([^-]+?)(?:\s+-|\s*$)', title)
        if location_match:
            result['location'] = location_match.group(1).strip()
        
        # Also check for "at <Location>" pattern
        if not result['location']:
            location_match = re.search(r'\s+at\s+([^-]+?)(?:\s+-|\s*$)', title)
            if location_match:
                result['location'] = location_match.group(1).strip()
        
        return result
    
    def _extract_speakers(self, soup: BeautifulSoup) -> Dict:
        """Extract speaker information from the page."""
        speakers = {}
        
        # Look for speaker cards/sections
        # They typically have headshots and word/time counts
        speaker_sections = soup.find_all(['div', 'section'], class_=lambda x: x and 'speaker' in x.lower() if x else False)
        
        for section in speaker_sections:
            # Try to extract speaker name
            name_elem = section.find(['h2', 'h3', 'h4', 'strong', 'b'])
            if name_elem:
                name = name_elem.get_text(strip=True)
                
                # Extract headshot URL
                img = section.find('img')
                headshot = img['src'] if img and img.get('src') else None
                
                # Extract word count
                words = 0
                word_match = re.search(r'(\d+)\s*words?', section.get_text())
                if word_match:
                    words = int(word_match.group(1))
                
                speakers[name] = {
                    'headshot': headshot,
                    'words': words
                }
        
        return speakers
    
    def _extract_segments(self, soup: BeautifulSoup, speakers_data: Dict) -> List[TranscriptSegment]:
        """Extract transcript segments from the page."""
        segments = []
        
        # The transcript is typically in sections marked with h2 for speaker + timestamp
        # followed by the text content
        
        # Look for transcript section
        transcript_section = soup.find('div', id='transcript') or soup.find('section', class_='transcript')
        
        if not transcript_section:
            # Try to find segments by pattern matching
            # Look for h2 elements with speaker names
            all_h2 = soup.find_all('h2')
            current_speaker = None
            current_time = None
            current_text_parts = []
            
            for elem in soup.find_all(['h2', 'p']):
                if elem.name == 'h2':
                    # Save previous segment if exists
                    if current_speaker and current_text_parts:
                        text = ' '.join(current_text_parts)
                        if text.strip():
                            segments.append(TranscriptSegment(
                                speaker=current_speaker,
                                start_time=current_time or '',
                                end_time='',
                                duration_seconds=0,
                                text=text.strip(),
                                headshot_url=speakers_data.get(current_speaker, {}).get('headshot')
                            ))
                    
                    # Parse new speaker header
                    header_text = elem.get_text(strip=True)
                    
                    # Try to extract speaker name and time
                    # Format: "Donald Trump" or "00:00:00-00:00:27 (27 sec)"
                    current_speaker = header_text.split('\n')[0].strip()
                    current_text_parts = []
                    
                    # Look for timestamp in next sibling or within element
                    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', header_text)
                    if time_match:
                        current_time = time_match.group(1)
                    
                elif elem.name == 'p' and current_speaker:
                    text = elem.get_text(strip=True)
                    if text and not text.startswith('Sentiment') and not text.startswith('Topics'):
                        current_text_parts.append(text)
            
            # Don't forget the last segment
            if current_speaker and current_text_parts:
                text = ' '.join(current_text_parts)
                if text.strip():
                    segments.append(TranscriptSegment(
                        speaker=current_speaker,
                        start_time=current_time or '',
                        end_time='',
                        duration_seconds=0,
                        text=text.strip(),
                        headshot_url=speakers_data.get(current_speaker, {}).get('headshot')
                    ))
        
        return segments
    
    def _extract_topics(self, soup: BeautifulSoup) -> List[str]:
        """Extract topic tags from the page."""
        topics = []
        
        # Look for topic links
        topic_links = soup.find_all('a', href=lambda x: x and 'topic=' in x if x else False)
        for link in topic_links:
            topics.append(link.get_text(strip=True))
        
        return topics
    
    def _extract_entities(self, soup: BeautifulSoup) -> List[str]:
        """Extract named entities from the page."""
        entities = []
        
        # Look for entities section
        entities_section = soup.find(['div', 'section'], class_=lambda x: x and 'entit' in x.lower() if x else False)
        if entities_section:
            for elem in entities_section.find_all(['a', 'span', 'li']):
                text = elem.get_text(strip=True)
                if text and len(text) > 1:
                    entities.append(text)
        
        return entities
    
    def _url_to_id(self, url: str) -> str:
        """Generate a stable ID from a URL."""
        # Extract the slug from the URL
        # e.g., /factbase/trump/transcript/donald-trump-speech-political-rally-washington-january-19-2025/
        match = re.search(r'/transcript/([^/]+)/?$', url)
        if match:
            return match.group(1)
        
        # Fallback to hash
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def scrape_transcript(self, url: str) -> Optional[Transcript]:
        """Scrape a single transcript from its URL."""
        html = self._get_page(url)
        if not html:
            return None
        
        return self.parse_transcript_page(html, url)


def parse_transcript_from_html(html: str, url: str) -> Optional[Dict]:
    """
    Parse a transcript from raw HTML.
    This is a standalone function that can be used without the requests library.
    """
    scraper = FactbaseScraper.__new__(FactbaseScraper)
    scraper.delay = 0
    scraper.session = None
    
    transcript = scraper.parse_transcript_page(html, url)
    
    if not transcript:
        return None
    
    return {
        'id': transcript.id,
        'url': transcript.url,
        'title': transcript.title,
        'primary_speaker': transcript.primary_speaker,
        'event_type': transcript.event_type,
        'event_date': transcript.event_date,
        'location': transcript.location,
        'topics': transcript.topics,
        'entities': transcript.entities,
        'segments': [
            {
                'speaker': s.speaker,
                'start_time': s.start_time,
                'end_time': s.end_time,
                'duration_seconds': s.duration_seconds,
                'text': s.text,
                'sentiment_vader': s.sentiment_vader,
                'sentiment_label': s.sentiment_label,
                'headshot_url': s.headshot_url
            }
            for s in transcript.segments
        ]
    }


# Known transcript URLs (can be expanded)
# These are manually compiled from search results and can be used as a starting point
KNOWN_TRANSCRIPT_URLS = [
    # Trump 2025 transcripts
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-washington-january-19-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-commencement-address-west-point-usma-may-24-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-campaign-rally-new-york-madison-square-garden-october-27-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-charlotte-north-carolina-july-24-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-las-vegas-june-9-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-campaign-rally-reading-pennsylvania-november-4-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-campaign-rally-allentown-pennsylvania-october-29-2024/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-phoenix-december-22-2024/",
    
    # JD Vance transcripts
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-charlie-kirk-podcast-guest-host-september-15-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-turning-point-usa-oxford-mississippi-october-30-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-charlie-kirk-memorial-glendale-arizona-september-21-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-speech-jd-vance-economy-la-crosse-wisconsin-august-28-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-tax-spending-cuts-howell-michigan-september-17-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-usmc-ball-november-8-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-thanksgiving-troops-kentucky-november-26-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-interview-jd-vance-lara-trump-fox-news-september-6-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-jd-vance-anniversary-usmc-california-october-18-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-interview-jd-vance-bartiromo-fox-sunday-morning-futures-october-12-2025/",
    
    # Karoline Leavitt briefings
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-january-31-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-january-28-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-february-12-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-march-5-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-april-28-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-briefing-karoline-leavitt-the-white-house-june-2-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-june-11-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-july-7-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-august-12-2025/",
    "https://rollcall.com/factbase/trump/transcript/donald-trump-press-conference-briefing-karoline-leavitt-august-28-2025/",
]


if __name__ == "__main__":
    # Test parsing
    print("Factbase Scraper initialized")
    print(f"Known transcript URLs: {len(KNOWN_TRANSCRIPT_URLS)}")
    
    if HAS_REQUESTS:
        scraper = FactbaseScraper(delay_between_requests=1.5)
        print("Scraper ready with requests library")
    else:
        print("Scraper in parse-only mode (no requests library)")
