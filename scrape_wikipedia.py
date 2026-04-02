#!/usr/bin/env python3
"""
Script to download texts from Wikipedia in any language
using the MediaWiki API.
Goal: Create text corpus for synthetic handwriting dataset.
Compatible with the build_dataset.py pipeline
"""

import requests
import time
import os
from pathlib import Path
import argparse
import json
import re


class WikipediaScraper:
    def __init__(self, language='ca', output_dir='data', delay=1.0, verbose=False):
        self.language = language
        self.base_url = f"https://{language}.wikipedia.org/w/api.php"
        self.output_dir = Path(output_dir) / f"wikipedia_{language}"
        self.delay = delay
        self.verbose = verbose
        self.headers = {
            'User-Agent': 'SyntheticHTRDatasetGenerator/1.0 (Research project; contact@university.edu)'
        }

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_random_articles(self, count=20):
        """Gets a list of random articles"""
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'random',
            'rnnamespace': 0,  # Only articles (namespace 0)
            'rnlimit': min(count, 20)  # API limits to 20 per request
        }

        articles = []
        remaining = count

        while remaining > 0:
            params['rnlimit'] = min(remaining, 20)

            try:
                if self.verbose:
                    print(f"    Fetching {params['rnlimit']} random articles...")
                response = requests.get(self.base_url, params=params,
                                       headers=self.headers, timeout=15)
                response.raise_for_status()
                data = response.json()

                for article in data.get('query', {}).get('random', []):
                    articles.append({
                        'title': article['title'],
                        'id': article['id']
                    })

                remaining -= params['rnlimit']
                time.sleep(self.delay)

            except Exception as e:
                print(f"    [ERROR] Error fetching random articles: {e}")
                break

        return articles

    def get_articles_from_category(self, category, max_articles=100):
        """Gets articles from a specific category"""
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'categorymembers',
            'cmtitle': f'Category:{category}',
            'cmtype': 'page',
            'cmlimit': 50
        }

        articles = []

        while len(articles) < max_articles:
            try:
                if self.verbose:
                    print(f"    Fetching articles from category '{category}'...")
                response = requests.get(self.base_url, params=params,
                                       headers=self.headers, timeout=15)
                response.raise_for_status()
                data = response.json()

                for member in data.get('query', {}).get('categorymembers', []):
                    articles.append({
                        'title': member['title'],
                        'id': member['pageid']
                    })

                # Check if there are more pages
                if 'continue' in data and len(articles) < max_articles:
                    params['cmcontinue'] = data['continue']['cmcontinue']
                    time.sleep(self.delay)
                else:
                    break

            except Exception as e:
                print(f"    [ERROR] Error fetching category: {e}")
                break

        return articles[:max_articles]

    def get_article_text(self, title):
        """Extracts clean text from an article using the API"""
        params = {
            'action': 'query',
            'format': 'json',
            'titles': title,
            'prop': 'extracts',
            'explaintext': True,  # Plain text, no HTML
            'exsectionformat': 'plain'
        }

        try:
            if self.verbose:
                print(f"    Fetching: {title}")
            response = requests.get(self.base_url, params=params,
                                   headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            pages = data.get('query', {}).get('pages', {})
            for page_id, page_data in pages.items():
                if page_id == '-1':
                    return None

                text = page_data.get('extract', '')
                if not text:
                    return None

                # Clean text
                text = self._clean_text(text)

                lines = [line.strip() for line in text.split('\n') if line.strip()]

                if not lines:
                    return None

                return {
                    'text': '\n'.join(lines),
                    'lines': lines,
                    'num_lines': len(lines),
                    'num_words': sum(len(line.split()) for line in lines),
                    'title': page_data.get('title', title)
                }

        except Exception as e:
            print(f"    [ERROR] Error fetching {title}: {e}")
            return None

    def _clean_text(self, text):
        """Cleans the text extracted from Wikipedia"""
        # Remove unwanted sections
        sections_to_remove = [
            'Referències', 'References', 'Bibliografía', 'Bibliography',
            'Enllaços externs', 'External links', 'Enlaces externos',
            'Vegeu també', 'See also', 'Véase también',
            'Notes', 'Notas', 'Footnotes',
            'Fonts', 'Sources', 'Sources',
            'Lectura addicional', 'Further reading', 'Lectura adicional'
        ]

        for section in sections_to_remove:
            pattern = rf'==\s*{re.escape(section)}\s*==.*'
            text = re.split(pattern, text, flags=re.IGNORECASE)[0]

        # Remove section headers (== Title ==)
        text = re.sub(r'={2,}.*?={2,}', '', text)

        # Remove content in braces (residual templates)
        text = re.sub(r'\{[^}]*\}', '', text)

        # Remove content in brackets (coordinates, refs)
        text = re.sub(r'\[[^\]]*\]', '', text)

        # Remove URLs
        text = re.sub(r'https?://\S+', '', text)

        # Remove lines that are only numbers (residual tables)
        text = re.sub(r'^[\d\s.,]+$', '', text, flags=re.MULTILINE)

        # Remove very short lines (< 10 characters) which are usually residue
        lines = text.split('\n')
        lines = [line.strip() for line in lines if len(line.strip()) >= 10]

        # Remove consecutive duplicate lines
        cleaned_lines = []
        for line in lines:
            if not cleaned_lines or line != cleaned_lines[-1]:
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def sanitize_filename(self, filename):
        """Sanitizes the file name"""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'\s+', '_', filename)
        if len(filename) > 200:
            filename = filename[:200]
        return filename

    def save_content(self, article_title, content, article_index):
        """Saves extracted content in the same format as scrape_wikisource"""
        safe_name = self.sanitize_filename(article_title)

        # Save as plain text
        txt_file = self.output_dir / f"{article_index:04d}_{safe_name}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(content['text'])

        # Save metadata as JSON
        json_file = self.output_dir / f"{article_index:04d}_{safe_name}.json"
        metadata = {
            'article_title': article_title,
            'article_index': article_index,
            'language': self.language,
            'source': 'wikipedia',
            'num_lines': content['num_lines'],
            'num_words': content['num_words']
        }
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        if self.verbose:
            print(f"    [SAVED] {txt_file.name} ({content['num_lines']} lines, {content['num_words']} words)")

    def scrape_all(self, max_articles=100, category=None):
        """Complete Wikipedia scraping"""
        print("=" * 60)
        print(f"WIKIPEDIA ({self.language.upper()}) - ARTICLE SCRAPER")
        print("=" * 60)
        print(f"  Language: {self.language}")
        print(f"  Max articles: {max_articles}")
        if category:
            print(f"  Category: {category}")
        print()

        # Get list of articles
        if category:
            print(f"[1] Getting articles from category '{category}'...")
            articles = self.get_articles_from_category(category, max_articles)
        else:
            print(f"[1] Getting {max_articles} random articles...")
            articles = self.get_random_articles(max_articles)

        if not articles:
            print("[ERROR] No articles found")
            return

        print(f"  [OK] Found {len(articles)} articles")

        print(f"\n[2] Processing articles...")
        print("=" * 60)

        total_articles = 0
        total_lines = 0
        total_words = 0

        for idx, article in enumerate(articles, 1):
            print(f"\n[{idx}/{len(articles)}] Article: {article['title']}")

            # Extract content
            content = self.get_article_text(article['title'])

            if content and content['num_lines'] > 0 and content['num_words'] >= 20:
                self.save_content(article['title'], content, idx)

                total_articles += 1
                total_lines += content['num_lines']
                total_words += content['num_words']
            else:
                if self.verbose:
                    print(f"    [SKIP] Insufficient content")

            # Delay between requests
            time.sleep(self.delay)

        # Final summary
        print("\n" + "=" * 60)
        print("FINAL SUMMARY")
        print("=" * 60)
        print(f"  Language: {self.language}")
        print(f"  Articles saved: {total_articles}")
        print(f"  Total lines: {total_lines:,}")
        print(f"  Total words: {total_words:,}")
        print(f"\n[SUCCESS] Texts saved in: {self.output_dir.absolute()}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Wikipedia scraper for creating multilingual text corpus'
    )
    parser.add_argument('--language', '-l', default='ca',
                        help='Language code (default: ca). Examples: ca, es, eu, gl, en, fr, de, it')
    parser.add_argument('--output-dir', default='data',
                        help='Base output directory (default: data). Creates subfolder wikipedia_[language]/')
    parser.add_argument('--max-articles', type=int, default=100,
                        help='Maximum number of articles to download (default: 100)')
    parser.add_argument('--category', type=str, default=None,
                        help='Wikipedia category to get articles from (optional)')
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed information')

    args = parser.parse_args()

    scraper = WikipediaScraper(
        language=args.language,
        output_dir=args.output_dir,
        delay=args.delay,
        verbose=args.verbose
    )

    scraper.scrape_all(
        max_articles=args.max_articles,
        category=args.category
    )


if __name__ == "__main__":
    main()
