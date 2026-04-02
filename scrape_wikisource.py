#!/usr/bin/env python3
"""
Script to scrape validated books from Catalan Wikisource
Goal: Create synthetic dataset of lines and words
"""

import requests
from bs4 import BeautifulSoup
import time
import os
from pathlib import Path
import argparse
import json
from urllib.parse import urljoin, urlparse
import re

class WikisourceScraper:
    def __init__(self, output_dir='data', delay=1.0, verbose=False):
        self.base_url = "https://ca.wikisource.org"
        self.output_dir = Path(output_dir)
        self.delay = delay
        self.verbose = verbose
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # Create output directory
        self.output_dir.mkdir(exist_ok=True)

    def get_page(self, url):
        """Get page content"""
        try:
            if self.verbose:
                print(f"    Fetching: {url}")
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"    [ERROR] Error fetching {url}: {e}")
            return None

    def sanitize_filename(self, filename):
        """Sanitize filename"""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'\s+', '_', filename)
        if len(filename) > 200:
            filename = filename[:200]
        return filename

    def get_validated_books(self):
        """Get list of validated books from category"""
        url = "https://ca.wikisource.org/wiki/Categoria:Llibres_validats"

        print("[1] Getting list of validated books...")
        html = self.get_page(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        books = []

        # Find all category groups
        category_groups = soup.find_all('div', class_='mw-category-group')

        for group in category_groups:
            # Find all links in group
            links = group.find_all('a')
            for link in links:
                if link.get('href'):
                    book_url = urljoin(self.base_url, link['href'])
                    book_title = link.get_text(strip=True)
                    books.append({
                        'title': book_title,
                        'url': book_url
                    })

        print(f"  [OK] Found {len(books)} validated books")
        return books

    def get_validated_pages(self, book_url):
        """Get validated pages from a book"""
        html = self.get_page(book_url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        validated_pages = []

        # Find page list from index
        pagelist = soup.find('div', class_='prp-index-pagelist')
        if not pagelist:
            if self.verbose:
                print(f"    [WARNING] Not found prp-index-pagelist")
            return []

        # Find links with quality4 (validated pages)
        quality4_links = pagelist.find_all('a', class_=lambda x: x and 'prp-pagequality-4' in x and 'quality4' in x)

        for link in quality4_links:
            if link.get('href'):
                page_url = urljoin(self.base_url, link['href'])
                page_title = link.get('title', link.get_text(strip=True))
                validated_pages.append({
                    'title': page_title,
                    'url': page_url
                })

        if self.verbose:
            print(f"    [OK] Found {len(validated_pages)} validated pages")

        return validated_pages

    def extract_page_content(self, page_url):
        """Extract text content from a page"""
        html = self.get_page(page_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # Estructura: prp-page-qualityheader quality4 -> hermano pagetext -> dentro mw-content-ltr mw-parser-output
        quality_header = soup.find('div', class_=lambda x: x and 'prp-page-qualityheader' in x and 'quality4' in x)

        if not quality_header:
            if self.verbose:
                print(f"    [WARNING] Not found prp-page-qualityheader quality4")
            return None

        # Buscar el hermano siguiente que es pagetext
        pagetext = quality_header.find_next_sibling('div', class_='pagetext')

        if not pagetext:
            if self.verbose:
                print(f"    [WARNING] Not found pagetext después de quality4")
            return None

        # Dentro de pagetext, buscar mw-content-ltr mw-parser-output
        page_content = pagetext.find('div', class_='mw-content-ltr mw-parser-output')

        if not page_content:
            if self.verbose:
                print(f"    [WARNING] Not found mw-content-ltr mw-parser-output dentro de pagetext")
            return None

        # Extract text
        # Eliminar scripts, styles, etc.
        #for tag in page_content(['script', 'style', 'sup', 'ref']):  #CANVI
        for tag in page_content(['script', 'style', 'sup', 'ref', 'img', 'figure', 'figcaption']):
            tag.decompose()

        # Get text
        text = page_content.get_text(separator='\n', strip=True)

        # Limpiar texto
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        return {
            'text': '\n'.join(lines),
            'lines': lines,
            'num_lines': len(lines),
            'num_words': sum(len(line.split()) for line in lines)
        }

    def save_content(self, book_title, page_title, content, book_index, page_index):
        """Save extracted content"""
        # Create folder structure: data/[libro]/
        safe_book_name = self.sanitize_filename(book_title)
        book_dir = self.output_dir / safe_book_name
        book_dir.mkdir(exist_ok=True)

        # Page filename
        safe_page_name = self.sanitize_filename(page_title)

        # Save as plain text
        txt_file = book_dir / f"{page_index:04d}_{safe_page_name}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(content['text'])

        # Save metadata as JSON
        json_file = book_dir / f"{page_index:04d}_{safe_page_name}.json"
        metadata = {
            'book_title': book_title,
            'page_title': page_title,
            'book_index': book_index,
            'page_index': page_index,
            'num_lines': content['num_lines'],
            'num_words': content['num_words']
        }
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        if self.verbose:
            print(f"    [SAVED] {txt_file.name} ({content['num_lines']} lines, {content['num_words']} words)")

    def scrape_all(self, max_books=None, start_from_book=None):
        """Complete Catalan Wikisource scrape"""
        print("=" * 60)
        print("CATALAN WIKISOURCE - VALIDATED BOOKS SCRAPER")
        print("=" * 60)
        print()

        # Get list of books
        books = self.get_validated_books()

        if not books:
            print("[ERROR] No books found")
            return

        # If start book specified, start from the next one
        if start_from_book:
            # Find book in list
            found_index = None
            for idx, book in enumerate(books):
                if start_from_book.lower() in book['title'].lower():
                    found_index = idx
                    print(f"\n[INFO] Found reference book: {book['title']}")
                    break

            if found_index is not None:
                # Empezar desde el siguiente libro
                books = books[found_index + 1:]
                print(f"[INFO] Starting from next book (skipping {found_index + 1} books)")
            else:
                print(f"\n[WARNING] Not found el libro '{start_from_book}'")
                print("[INFO] Se procesarán todos los books")

        # Limitar número de books si se especifica
        if max_books:
            books = books[:max_books]
            print(f"\n[INFO] Limited to {max_books} books")

        print(f"\n[2] Processing {len(books)} books...")
        print("=" * 60)

        total_pages = 0
        total_lines = 0
        total_words = 0

        # Procesar cada libro
        for book_idx, book in enumerate(books, 1):
            print(f"\n[{book_idx}/{len(books)}] Book: {book['title']}")
            print(f"  URL: {book['url']}")

            # Obtener validated pages
            pages = self.get_validated_pages(book['url'])

            if not pages:
                print(f"  [SKIP] No hay validated pages")
                continue

            print(f"  [INFO] Processing {len(pages)} validated pages...")

            # Procesar cada página
            for page_idx, page in enumerate(pages, 1):
                if self.verbose:
                    print(f"  [{page_idx}/{len(pages)}] Page: {page['title']}")

                # Extract content
                content = self.extract_page_content(page['url'])

                if content and content['num_lines'] > 0:
                    # Save content
                    self.save_content(
                        book['title'],
                        page['title'],
                        content,
                        book_idx,
                        page_idx
                    )

                    total_pages += 1
                    total_lines += content['num_lines']
                    total_words += content['num_words']
                else:
                    if self.verbose:
                        print(f"    [SKIP] No valid content")

                # Delay between pages
                time.sleep(self.delay)

            # Delay entre books
            time.sleep(self.delay * 2)

        # Final summary
        print("\n" + "=" * 60)
        print("FINAL SUMMARY")
        print("=" * 60)
        print(f"  Books processed: {len(books)}")
        print(f"  Pages saved: {total_pages}")
        print(f"  Total lines: {total_lines:,}")
        print(f"  Total words: {total_words:,}")
        print(f"\n[SUCCESS] Dataset saved in: {self.output_dir.absolute()}")
        print()

def main():
    parser = argparse.ArgumentParser(
        description='Catalan Wikisource scraper to create synthetic dataset'
    )
    parser.add_argument('--output-dir', default='data', help='Output directory (default: data)')
    parser.add_argument('--max-books', type=int, default=None, help='Número máximo de books a procesar')
    parser.add_argument('--start-from-book', type=str, default=None, help='Book title to start from (will scrape from the next one)')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed information')

    args = parser.parse_args()

    scraper = WikisourceScraper(
        output_dir=args.output_dir,
        delay=args.delay,
        verbose=args.verbose
    )

    scraper.scrape_all(max_books=args.max_books, start_from_book=args.start_from_book)

if __name__ == "__main__":
    main()
