#!/usr/bin/env python3
"""
Complete scraper that gets ALL Trump transcripts from 2016-present
Designed to be run on-demand to refresh and get new transcripts
"""
import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
from database import Database
from text_analysis import analyze_word_frequency, count_words

class FullScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        })
        self.db = Database()
        self.delay = 1.5  # Faster but still respectful
        self.base_url = "https://www.presidency.ucsb.edu"

    def fetch_page(self, url, retries=3):
        """Fetch with retries"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                time.sleep(self.delay)
                return BeautifulSoup(response.content, 'lxml')
            except Exception as e:
                if attempt == retries - 1:
                    print(f"  ✗ Failed after {retries} attempts: {e}")
                    return None
                time.sleep(2)
        return None

    def parse_date(self, date_text):
        """Parse date into YYYY-MM-DD format"""
        if not date_text:
            return None

        # Already in correct format
        if re.match(r'\d{4}-\d{2}-\d{2}', date_text):
            return date_text

        # Try to parse various formats
        formats = [
            '%B %d, %Y',  # January 1, 2016
            '%b %d, %Y',  # Jan 1, 2016
            '%Y-%m-%d',
            '%m/%d/%Y',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_text.strip(), fmt)
                return dt.strftime('%Y-%m-%d')
            except:
                continue

        return date_text

    def get_all_pages(self):
        """Get all document listing pages - NO LIMIT"""
        all_docs = []
        page = 0
        consecutive_empty = 0

        print("\n🔍 Discovering all Trump documents...")

        while True:
            url = f"{self.base_url}/advanced-search?field-keywords=&from%5Bdate%5D=01-01-2016&to%5Bdate%5D=12-31-2024&person2=200301&items_per_page=100&page={page}"

            if page % 10 == 0:
                print(f"  Page {page + 1}... (Total: {len(all_docs)})")

            soup = self.fetch_page(url)
            if not soup:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                continue

            doc_links = soup.find_all('a', href=re.compile(r'/documents/'))
            new_docs = []

            for link in doc_links:
                href = link.get('href', '')
                if not href.startswith('http'):
                    href = self.base_url + href

                title = link.get_text(strip=True)

                # Skip navigation/system pages
                if any(x in title.lower() for x in ['guidebook', 'category', 'attributes']):
                    continue

                if title and href not in [d['url'] for d in all_docs]:
                    new_docs.append({'url': href, 'title': title})

            if not new_docs:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    print(f"  No more documents found after page {page + 1}")
                    break
            else:
                consecutive_empty = 0
                all_docs.extend(new_docs)

            page += 1

        return all_docs

    def scrape_document(self, url):
        """Extract content from a document page"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        # Title
        title_elem = soup.find('h1', class_='title') or soup.find('h1')
        title = title_elem.get_text(strip=True) if title_elem else 'Unknown'

        # Date
        date = None
        date_elem = soup.find('span', class_='date-display-single')
        if date_elem:
            date = self.parse_date(date_elem.get_text(strip=True))

        # Content
        content_div = soup.find('div', class_='field-docs-content')
        if not content_div:
            content_div = soup.find('div', class_='field-items')

        if content_div:
            full_text = content_div.get_text(strip=True, separator=' ')
        else:
            # Fallback: get all paragraphs
            paragraphs = soup.find_all('p')
            full_text = ' '.join([p.get_text(strip=True) for p in paragraphs])

        # Determine speech type
        speech_type = self.determine_type(title)

        if not full_text or len(full_text) < 100:
            return None

        return {
            'title': title,
            'date': date or '',
            'speech_type': speech_type,
            'location': '',
            'full_text': full_text
        }

    def determine_type(self, title):
        """Determine document type from title"""
        title_lower = title.lower()

        if 'tweet' in title_lower or 'twitter' in title_lower:
            return 'Tweet Collection'
        elif 'press release' in title_lower:
            return 'Press Release'
        elif any(x in title_lower for x in ['remarks', 'address', 'speech']):
            return 'Speech'
        elif 'interview' in title_lower:
            return 'Interview'
        elif 'statement' in title_lower:
            return 'Statement'
        elif 'executive order' in title_lower:
            return 'Executive Order'
        elif 'proclamation' in title_lower:
            return 'Proclamation'
        elif 'memorandum' in title_lower:
            return 'Memorandum'
        elif 'press briefing' in title_lower or 'press gaggle' in title_lower:
            return 'Press Briefing'
        else:
            return 'Document'

    def run(self, skip_existing=True):
        """Main scraper - gets EVERYTHING"""
        print("="*80)
        print("FULL TRUMP TRANSCRIPT SCRAPER")
        print("Getting ALL documents from 2016 to present")
        print("="*80)

        self.db.initialize()

        # Get all document URLs
        all_docs = self.get_all_pages()

        print(f"\n{'='*80}")
        print(f"📄 Found {len(all_docs)} total documents")
        print(f"{'='*80}")

        if not all_docs:
            print("No documents found")
            return

        # Process each
        success = 0
        skipped = 0
        failed = 0

        print(f"\n🚀 Starting scrape...")

        for i, doc in enumerate(all_docs, 1):
            if i % 50 == 0 or i == 1:
                print(f"\n[{i}/{len(all_docs)}] Progress: {success} saved, {skipped} skipped, {failed} failed")

            # Check if exists
            if skip_existing and self.db.url_exists(doc['url']):
                skipped += 1
                continue

            # Scrape
            content = self.scrape_document(doc['url'])

            if not content:
                failed += 1
                continue

            word_count = count_words(content['full_text'])

            # Save
            try:
                transcript_id = self.db.insert_transcript(
                    title=content['title'],
                    date=content['date'],
                    speech_type=content['speech_type'],
                    location=content['location'],
                    url=doc['url'],
                    full_text=content['full_text'],
                    word_count=word_count
                )

                if transcript_id:
                    word_freqs = analyze_word_frequency(content['full_text'])
                    self.db.insert_word_frequencies(transcript_id, word_freqs)
                    success += 1

                    if success % 10 == 0:
                        print(f"  ✓ {success} documents saved...")
            except Exception as e:
                print(f"  ✗ Error saving: {e}")
                failed += 1

        print(f"\n{'='*80}")
        print(f"✅ SCRAPING COMPLETE")
        print(f"{'='*80}")
        print(f"✓ Successfully saved: {success}")
        print(f"⊘ Already existed: {skipped}")
        print(f"✗ Failed: {failed}")

        # Final stats
        stats = self.db.get_stats()
        print(f"\n📊 DATABASE TOTALS:")
        print(f"  Total transcripts: {stats['total_transcripts']}")
        if stats['date_range'][0] and stats['date_range'][1]:
            print(f"  Date range: {stats['date_range'][0]} to {stats['date_range'][1]}")

        self.db.close()

        return {
            'success': success,
            'skipped': skipped,
            'failed': failed,
            'total': stats['total_transcripts']
        }


if __name__ == '__main__':
    scraper = FullScraper()
    scraper.run(skip_existing=True)
