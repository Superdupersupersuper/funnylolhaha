import requests
from bs4 import BeautifulSoup
import time
import json
from datetime import datetime
from database import Database
from text_analysis import analyze_word_frequency, count_words

class FactBaseScraper:
    def __init__(self):
        self.base_url = "https://rollcall.com/factbase"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        })
        self.db = Database()
        self.delay = 2

    def fetch_page(self, url):
        """Fetch a page and return BeautifulSoup object"""
        print(f"Fetching: {url}")
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            time.sleep(self.delay)
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def explore_structure(self, url):
        """Explore and print the structure of a page"""
        soup = self.fetch_page(url)
        if not soup:
            return

        print("\n" + "="*80)
        print(f"EXPLORING: {url}")
        print("="*80)

        # Look for common article/transcript containers
        containers = [
            soup.find_all('article'),
            soup.find_all('div', class_=lambda x: x and 'transcript' in x.lower()),
            soup.find_all('div', class_=lambda x: x and 'item' in x.lower()),
            soup.find_all('div', class_=lambda x: x and 'post' in x.lower()),
            soup.find_all('div', class_=lambda x: x and 'entry' in x.lower()),
        ]

        for i, container_list in enumerate(containers):
            if container_list:
                print(f"\nFound {len(container_list)} containers of type {i}")
                for item in container_list[:3]:  # Show first 3
                    print(f"  - Tag: {item.name}, Classes: {item.get('class', [])}")
                    title = item.find(['h1', 'h2', 'h3', 'h4', 'a'])
                    if title:
                        print(f"    Title: {title.get_text(strip=True)[:100]}")

        # Look for links
        links = soup.find_all('a', href=True)
        transcript_links = [link for link in links if 'transcript' in link.get('href', '').lower()]
        print(f"\nFound {len(transcript_links)} links with 'transcript' in href")
        for link in transcript_links[:5]:
            print(f"  - {link.get('href')}: {link.get_text(strip=True)[:80]}")

        # Look for dates
        date_elements = soup.find_all(['time', 'span'], class_=lambda x: x and 'date' in str(x).lower())
        print(f"\nFound {len(date_elements)} potential date elements")
        for elem in date_elements[:5]:
            print(f"  - {elem.get('class', [])}: {elem.get_text(strip=True)}")

        return soup

    def scrape_factbase_api(self):
        """
        Try to access FactBase data through their API or structured endpoints
        """
        # FactBase often has JSON endpoints for their data
        api_endpoints = [
            f"{self.base_url}/api/transcripts",
            f"{self.base_url}/trump/api/search",
            f"{self.base_url}/trump/transcripts.json",
        ]

        for endpoint in api_endpoints:
            try:
                print(f"\nTrying API endpoint: {endpoint}")
                response = self.session.get(endpoint, timeout=10)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"SUCCESS! Found JSON data: {list(data.keys()) if isinstance(data, dict) else 'Array data'}")
                        return data
                    except:
                        pass
            except:
                pass

        return None

    def scrape_search_page(self):
        """Scrape the main search page to find transcripts"""
        search_url = f"{self.base_url}/trump/search/"
        soup = self.explore_structure(search_url)

        if not soup:
            print("Could not load search page")
            return []

        transcripts = []

        # Try multiple strategies to find transcript entries
        # Strategy 1: Look for article tags
        articles = soup.find_all('article')
        print(f"\nStrategy 1: Found {len(articles)} article tags")

        for article in articles:
            transcript = self.extract_transcript_info(article)
            if transcript:
                transcripts.append(transcript)

        # Strategy 2: Look for specific classes
        if not transcripts:
            items = soup.find_all('div', class_=lambda x: x and any(
                keyword in str(x).lower() for keyword in ['item', 'post', 'entry', 'transcript', 'result']
            ))
            print(f"\nStrategy 2: Found {len(items)} potential items")

            for item in items:
                transcript = self.extract_transcript_info(item)
                if transcript:
                    transcripts.append(transcript)

        # Strategy 3: Look for all links that might be transcripts
        if not transcripts:
            print("\nStrategy 3: Looking for transcript links")
            links = soup.find_all('a', href=lambda x: x and ('transcript' in x.lower() or '/trump/' in x.lower()))
            for link in links:
                href = link.get('href', '')
                if not href.startswith('http'):
                    href = f"https://rollcall.com{href}"

                title = link.get_text(strip=True)
                if title and len(title) > 10:  # Filter out navigation links
                    transcripts.append({
                        'url': href,
                        'title': title,
                        'date': None,
                        'speech_type': 'Speech'
                    })

        print(f"\nTotal transcripts found: {len(transcripts)}")
        return transcripts

    def extract_transcript_info(self, element):
        """Extract transcript information from an HTML element"""
        # Find title
        title_elem = element.find(['h1', 'h2', 'h3', 'h4', 'a'])
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)

        # Find link
        link_elem = element.find('a', href=True)
        if not link_elem:
            return None

        url = link_elem.get('href', '')
        if not url.startswith('http'):
            url = f"https://rollcall.com{url}"

        # Find date
        date = None
        date_elem = element.find('time')
        if date_elem:
            date = date_elem.get('datetime', date_elem.get_text(strip=True))
        else:
            date_elem = element.find(class_=lambda x: x and 'date' in str(x).lower())
            if date_elem:
                date = date_elem.get_text(strip=True)

        # Find speech type
        speech_type = 'Speech'
        type_elem = element.find(class_=lambda x: x and any(
            keyword in str(x).lower() for keyword in ['type', 'category', 'tag']
        ))
        if type_elem:
            speech_type = type_elem.get_text(strip=True)

        return {
            'title': title,
            'url': url,
            'date': date,
            'speech_type': speech_type
        }

    def scrape_transcript_content(self, url):
        """Scrape the full content of a transcript page"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        # Find the main content
        content_selectors = [
            ('div', {'class': lambda x: x and 'transcript' in str(x).lower()}),
            ('div', {'class': lambda x: x and 'content' in str(x).lower()}),
            ('article', {}),
            ('div', {'class': 'entry-content'}),
            ('div', {'id': 'content'}),
        ]

        full_text = None
        for tag, attrs in content_selectors:
            content = soup.find(tag, attrs)
            if content:
                full_text = content.get_text(strip=True, separator=' ')
                if len(full_text) > 200:  # Must be substantial content
                    break

        if not full_text:
            # Last resort: get all paragraphs
            paragraphs = soup.find_all('p')
            full_text = ' '.join([p.get_text(strip=True) for p in paragraphs])

        # Extract metadata
        title = soup.find('h1')
        title = title.get_text(strip=True) if title else 'Unknown'

        date_elem = soup.find('time')
        date = None
        if date_elem:
            date = date_elem.get('datetime', date_elem.get_text(strip=True))

        location = None
        location_elem = soup.find(class_=lambda x: x and 'location' in str(x).lower())
        if location_elem:
            location = location_elem.get_text(strip=True)

        speech_type = 'Speech'
        type_elem = soup.find(class_=lambda x: x and any(
            keyword in str(x).lower() for keyword in ['type', 'category']
        ))
        if type_elem:
            speech_type = type_elem.get_text(strip=True)

        return {
            'title': title,
            'date': date,
            'speech_type': speech_type,
            'location': location,
            'full_text': full_text
        }

    def run(self):
        """Main scraping function"""
        print("="*80)
        print("FACTBASE TRUMP TRANSCRIPT SCRAPER")
        print("="*80)

        # Initialize database
        self.db.initialize()

        # First, try to explore the structure
        print("\nStep 1: Exploring website structure...")
        self.explore_structure(f"{self.base_url}/trump/search/")

        # Try API endpoints
        print("\nStep 2: Checking for API endpoints...")
        api_data = self.scrape_factbase_api()

        # Scrape search page
        print("\nStep 3: Scraping search page...")
        transcripts = self.scrape_search_page()

        if not transcripts:
            print("\nNo transcripts found. The website structure may have changed.")
            print("Please check the website manually and update the selectors.")
            return

        print(f"\nFound {len(transcripts)} transcripts to scrape")

        # Scrape each transcript
        success_count = 0
        for i, transcript in enumerate(transcripts[:10], 1):  # Limit to 10 for initial test
            print(f"\n[{i}/{len(transcripts)}] Processing: {transcript['title'][:60]}...")

            # Check if already exists
            if self.db.url_exists(transcript['url']):
                print("  Already in database, skipping")
                continue

            # Get full content
            content = self.scrape_transcript_content(transcript['url'])
            if not content or not content.get('full_text'):
                print("  Failed to extract content")
                continue

            # Merge metadata
            full_data = {**transcript, **content}

            # Calculate word count
            word_count = count_words(full_data['full_text'])
            print(f"  Word count: {word_count}")

            # Save to database
            transcript_id = self.db.insert_transcript(
                title=full_data['title'],
                date=full_data.get('date') or '',
                speech_type=full_data.get('speech_type', 'Speech'),
                location=full_data.get('location') or '',
                url=full_data['url'],
                full_text=full_data['full_text'],
                word_count=word_count
            )

            if transcript_id:
                # Analyze word frequency
                word_freqs = analyze_word_frequency(full_data['full_text'])
                self.db.insert_word_frequencies(transcript_id, word_freqs)
                print(f"  Saved to database (ID: {transcript_id})")
                success_count += 1

        print(f"\n{'='*80}")
        print(f"SCRAPING COMPLETE")
        print(f"Successfully scraped: {success_count} transcripts")
        print(f"{'='*80}")

        # Show stats
        stats = self.db.get_stats()
        print(f"\nDatabase Statistics:")
        print(f"  Total transcripts: {stats['total_transcripts']}")
        print(f"  Date range: {stats['date_range']}")

        self.db.close()


if __name__ == '__main__':
    scraper = FactBaseScraper()
    scraper.run()
