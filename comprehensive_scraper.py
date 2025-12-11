import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
from database import Database
from text_analysis import analyze_word_frequency, count_words

class ComprehensiveScraper:
    """
    Comprehensive scraper that gets Trump transcripts from American Presidency Project
    """
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        self.db = Database()
        self.delay = 2
        self.base_url = "https://www.presidency.ucsb.edu"

    def fetch_page(self, url):
        """Fetch a page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            time.sleep(self.delay)
            return BeautifulSoup(response.content, 'lxml')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def get_all_document_pages(self):
        """Get all pages of Trump documents"""
        all_docs = []
        page = 0

        while True:
            url = f"{self.base_url}/advanced-search?field-keywords=&field-keywords2=&field-keywords3=&from%5Bdate%5D=01-01-2016&to%5Bdate%5D=12-31-2024&person2=200301&items_per_page=100&page={page}"

            print(f"\nFetching page {page + 1}: {url}")
            soup = self.fetch_page(url)

            if not soup:
                break

            # Find document links
            doc_links = soup.find_all('a', href=re.compile(r'/documents/'))
            new_docs = []

            for link in doc_links:
                href = link.get('href', '')
                if not href.startswith('http'):
                    href = self.base_url + href

                title = link.get_text(strip=True)

                # Skip guidebooks and category pages
                if 'guidebook' in title.lower() or 'category' in title.lower():
                    continue

                if title and href not in [d['url'] for d in all_docs]:
                    new_docs.append({
                        'url': href,
                        'title': title
                    })

            if not new_docs:
                print(f"No more documents found on page {page + 1}")
                break

            all_docs.extend(new_docs)
            print(f"Found {len(new_docs)} new documents (total: {len(all_docs)})")

            page += 1

            # Safety limit
            if page >= 50:
                print("Reached page limit")
                break

        return all_docs

    def scrape_document(self, url):
        """Scrape a single document"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        # Extract title
        title_elem = soup.find('h1', class_='title')
        if not title_elem:
            title_elem = soup.find('h1')
        title = title_elem.get_text(strip=True) if title_elem else 'Unknown'

        # Extract date
        date = None
        date_elem = soup.find('span', class_='date-display-single')
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            try:
                # Try to parse date
                date_obj = datetime.strptime(date_text, '%B %d, %Y')
                date = date_obj.strftime('%Y-%m-%d')
            except:
                date = date_text

        # Extract content
        content_div = soup.find('div', class_='field-docs-content')
        if not content_div:
            content_div = soup.find('div', class_='field-items')

        if not content_div:
            # Try to find paragraphs
            paragraphs = soup.find_all('p')
            full_text = ' '.join([p.get_text(strip=True) for p in paragraphs])
        else:
            full_text = content_div.get_text(strip=True, separator=' ')

        # Determine speech type from title
        speech_type = 'Document'
        title_lower = title.lower()
        if 'tweet' in title_lower:
            speech_type = 'Tweet Collection'
        elif 'press release' in title_lower:
            speech_type = 'Press Release'
        elif 'remarks' in title_lower or 'speech' in title_lower:
            speech_type = 'Speech'
        elif 'interview' in title_lower:
            speech_type = 'Interview'
        elif 'statement' in title_lower:
            speech_type = 'Statement'
        elif 'executive order' in title_lower:
            speech_type = 'Executive Order'
        elif 'proclamation' in title_lower:
            speech_type = 'Proclamation'

        if not full_text or len(full_text) < 100:
            return None

        return {
            'title': title,
            'date': date or '',
            'speech_type': speech_type,
            'location': '',
            'full_text': full_text
        }

    def run(self, max_docs=None):
        """Main scraping function"""
        print("="*80)
        print("COMPREHENSIVE TRUMP TRANSCRIPT SCRAPER")
        print("American Presidency Project (2016-Present)")
        print("="*80)

        self.db.initialize()

        # Get all document URLs
        print("\nStep 1: Finding all documents...")
        all_docs = self.get_all_document_pages()

        print(f"\n{'='*80}")
        print(f"Found {len(all_docs)} total documents")
        print(f"{'='*80}")

        if not all_docs:
            print("No documents found")
            return

        # Limit if specified
        if max_docs:
            all_docs = all_docs[:max_docs]
            print(f"Processing first {max_docs} documents")

        # Process each document
        success_count = 0
        skip_count = 0

        for i, doc in enumerate(all_docs, 1):
            print(f"\n[{i}/{len(all_docs)}] {doc['title'][:70]}...")

            # Check if exists
            if self.db.url_exists(doc['url']):
                print("  ✓ Already in database")
                skip_count += 1
                continue

            # Scrape content
            content = self.scrape_document(doc['url'])

            if not content:
                print("  ✗ Failed to extract content")
                continue

            word_count = count_words(content['full_text'])
            print(f"  Words: {word_count:,} | Type: {content['speech_type']}")

            # Save to database
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
                    # Analyze words
                    word_freqs = analyze_word_frequency(content['full_text'])
                    self.db.insert_word_frequencies(transcript_id, word_freqs)
                    print(f"  ✓ Saved (ID: {transcript_id})")
                    success_count += 1
            except Exception as e:
                print(f"  ✗ Error saving: {e}")

        print(f"\n{'='*80}")
        print(f"SCRAPING COMPLETE")
        print(f"{'='*80}")
        print(f"Successfully saved: {success_count} documents")
        print(f"Already in DB: {skip_count} documents")
        print(f"Failed: {len(all_docs) - success_count - skip_count} documents")

        stats = self.db.get_stats()
        print(f"\nDatabase Statistics:")
        print(f"  Total transcripts: {stats['total_transcripts']}")
        if stats['date_range'][0] and stats['date_range'][1]:
            print(f"  Date range: {stats['date_range'][0]} to {stats['date_range'][1]}")

        self.db.close()


if __name__ == '__main__':
    scraper = ComprehensiveScraper()
    # Run without limit to get all documents
    scraper.run()
