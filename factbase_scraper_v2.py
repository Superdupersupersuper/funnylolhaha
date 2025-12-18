import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
from database import Database
from text_analysis import analyze_word_frequency, count_words

class FactBaseScraper2:
    """
    Alternative scraper that tries different FactBase URLs and structures
    """
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        self.db = Database()
        self.delay = 2

    def fetch_page(self, url):
        """Fetch a page"""
        print(f"Fetching: {url}")
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            time.sleep(self.delay)
            return BeautifulSoup(response.content, 'lxml')
        except Exception as e:
            print(f"Error: {e}")
            return None

    def try_archive_org(self):
        """
        Try to get transcripts from archive.org's copy of factbase
        """
        # The Wayback Machine might have factbase data
        urls = [
            "https://web.archive.org/web/20200101000000*/factba.se/trump/transcript",
            "https://web.archive.org/web/2020/https://factba.se/trump/transcript",
        ]

        for url in urls:
            print(f"\nTrying Archive.org: {url}")
            soup = self.fetch_page(url)
            if soup:
                # Look for transcript links
                links = soup.find_all('a', href=re.compile(r'transcript'))
                print(f"Found {len(links)} potential transcript links")
                return links
        return []

    def scrape_miller_center(self):
        """
        Scrape transcripts from UVA Miller Center (has presidential speeches)
        """
        base_url = "https://millercenter.org"
        search_url = f"{base_url}/the-presidency/presidential-speeches"

        print(f"\nTrying Miller Center: {search_url}")
        soup = self.fetch_page(search_url)

        if not soup:
            return []

        transcripts = []
        # Find all speech links
        speech_links = soup.find_all('a', href=re.compile(r'/speech/'))

        for link in speech_links:
            href = link.get('href', '')
            if not href.startswith('http'):
                href = base_url + href

            title = link.get_text(strip=True)
            if 'Trump' in title or 'trump' in href.lower():
                transcripts.append({
                    'url': href,
                    'title': title,
                    'source': 'miller_center'
                })

        print(f"Found {len(transcripts)} Trump speeches from Miller Center")
        return transcripts

    def scrape_american_presidency_project(self):
        """
        Scrape from American Presidency Project (comprehensive archive)
        """
        base_url = "https://www.presidency.ucsb.edu"

        # Trump's document archive
        urls = [
            f"{base_url}/advanced-search?field-keywords=&field-keywords2=&field-keywords3=&from%5Bdate%5D=01-01-2016&to%5Bdate%5D=12-31-2024&person2=200301&category2%5B%5D=&items_per_page=100",
        ]

        all_transcripts = []

        for url in urls:
            print(f"\nTrying American Presidency Project: {url}")
            soup = self.fetch_page(url)

            if not soup:
                continue

            # Find document links
            doc_links = soup.find_all('a', href=re.compile(r'/documents/'))

            for link in doc_links[:50]:  # Limit for now
                href = link.get('href', '')
                if not href.startswith('http'):
                    href = base_url + href

                title = link.get_text(strip=True)
                if title:
                    all_transcripts.append({
                        'url': href,
                        'title': title,
                        'source': 'presidency_project'
                    })

        print(f"Found {len(all_transcripts)} documents from American Presidency Project")
        return all_transcripts

    def scrape_rev_transcripts(self):
        """
        Try Rev.com (they have many political transcripts)
        """
        search_url = "https://www.rev.com/blog/transcript-category/donald-trump-transcripts"

        print(f"\nTrying Rev.com: {search_url}")
        soup = self.fetch_page(search_url)

        if not soup:
            return []

        transcripts = []
        # Find all article links
        articles = soup.find_all('article')

        for article in articles:
            link = article.find('a', href=True)
            if link:
                href = link.get('href', '')
                title_elem = article.find(['h2', 'h3'])
                title = title_elem.get_text(strip=True) if title_elem else link.get_text(strip=True)

                if title:
                    transcripts.append({
                        'url': href,
                        'title': title,
                        'source': 'rev'
                    })

        print(f"Found {len(transcripts)} transcripts from Rev.com")
        return transcripts

    def scrape_transcript_content(self, url, source):
        """Scrape content based on source"""
        soup = self.fetch_page(url)
        if not soup:
            return None

        full_text = None
        title = None
        date = None
        speech_type = 'Speech'

        if source == 'miller_center':
            # Miller Center specific selectors
            content_div = soup.find('div', class_='view-transcript')
            if content_div:
                full_text = content_div.get_text(strip=True, separator=' ')

            title_elem = soup.find('h1')
            title = title_elem.get_text(strip=True) if title_elem else 'Unknown'

            date_elem = soup.find('span', class_='date-display-single')
            if date_elem:
                date = date_elem.get_text(strip=True)

        elif source == 'presidency_project':
            # American Presidency Project selectors
            content_div = soup.find('div', class_='field-docs-content')
            if not content_div:
                content_div = soup.find('div', class_='field-items')

            if content_div:
                full_text = content_div.get_text(strip=True, separator=' ')

            title_elem = soup.find('h1')
            title = title_elem.get_text(strip=True) if title_elem else 'Unknown'

            date_elem = soup.find('span', class_='date-display-single')
            if date_elem:
                date = date_elem.get_text(strip=True)

        elif source == 'rev':
            # Rev.com selectors
            content_div = soup.find('div', class_='fl-callout-text')
            if not content_div:
                content_div = soup.find('div', class_='post-content')

            if content_div:
                full_text = content_div.get_text(strip=True, separator=' ')

            title_elem = soup.find('h1')
            title = title_elem.get_text(strip=True) if title_elem else 'Unknown'

            date_elem = soup.find('time')
            if date_elem:
                date = date_elem.get('datetime', date_elem.get_text(strip=True))

        else:
            # Generic scraping
            paragraphs = soup.find_all('p')
            full_text = ' '.join([p.get_text(strip=True) for p in paragraphs])
            title_elem = soup.find('h1')
            title = title_elem.get_text(strip=True) if title_elem else 'Unknown'

        if not full_text or len(full_text) < 200:
            return None

        return {
            'title': title,
            'date': date,
            'speech_type': speech_type,
            'location': '',
            'full_text': full_text
        }

    def run(self):
        """Main execution"""
        print("="*80)
        print("TRUMP TRANSCRIPT SCRAPER v2")
        print("="*80)

        self.db.initialize()

        all_transcripts = []

        # Try different sources
        print("\n1. Trying Miller Center...")
        all_transcripts.extend(self.scrape_miller_center())

        print("\n2. Trying American Presidency Project...")
        all_transcripts.extend(self.scrape_american_presidency_project())

        print("\n3. Trying Rev.com...")
        all_transcripts.extend(self.scrape_rev_transcripts())

        print(f"\n{'='*80}")
        print(f"Total transcripts found: {len(all_transcripts)}")
        print(f"{'='*80}")

        if not all_transcripts:
            print("\nNo transcripts found from any source.")
            print("The websites may have changed or require JavaScript.")
            return

        # Process transcripts
        success_count = 0
        limit = min(50, len(all_transcripts))  # Process up to 50 transcripts

        for i, transcript in enumerate(all_transcripts[:limit], 1):
            print(f"\n[{i}/{limit}] {transcript['title'][:60]}...")

            if self.db.url_exists(transcript['url']):
                print("  Already in database")
                continue

            content = self.scrape_transcript_content(transcript['url'], transcript.get('source', 'generic'))

            if not content or not content.get('full_text'):
                print("  Failed to extract content")
                continue

            word_count = count_words(content['full_text'])
            print(f"  Words: {word_count}")

            # Save to database
            transcript_id = self.db.insert_transcript(
                title=content['title'],
                date=content.get('date') or '',
                speech_type=content.get('speech_type', 'Speech'),
                location=content.get('location') or '',
                url=transcript['url'],
                full_text=content['full_text'],
                word_count=word_count
            )

            if transcript_id:
                word_freqs = analyze_word_frequency(content['full_text'])
                self.db.insert_word_frequencies(transcript_id, word_freqs)
                print(f"  ✓ Saved (ID: {transcript_id})")
                success_count += 1

        print(f"\n{'='*80}")
        print(f"COMPLETE - Saved {success_count} transcripts")
        print(f"{'='*80}")

        stats = self.db.get_stats()
        print(f"\nDatabase: {stats['total_transcripts']} total transcripts")
        self.db.close()


if __name__ == '__main__':
    scraper = FactBaseScraper2()
    scraper.run()
