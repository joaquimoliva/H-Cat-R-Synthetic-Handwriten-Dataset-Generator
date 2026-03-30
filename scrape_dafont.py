#!/usr/bin/env python3
"""
DaFont Scraper for Language-Compatible Fonts
Finds fonts that support language-specific special characters
"""

import requests
from bs4 import BeautifulSoup
import time
import csv
from urllib.parse import urljoin
import argparse
import io
import zipfile
from fontTools.ttLib import TTFont
from pathlib import Path

class DaFontScraper:
    def __init__(self, language='catalan', use_accent_filter=True, verbose=False):
        self.base_url = "https://www.dafont.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.language = language
        self.lang_config = self._load_language_config(language)
        self.required_chars = self.lang_config.get('required_chars', [])
        self.use_accent_filter = use_accent_filter and len(self.required_chars) > 0
        self.verbose = verbose
        self.filter_params = "&a=on" if self.use_accent_filter else ""
        self.font_blacklist = [
            'Loveletter_No._9',
            'Loveletter No. 9',
            'Autograf',
        ]

    def _load_language_config(self, language):
        """Carrega la configuració de l'idioma des de languages/"""
        import json
        config_path = Path(__file__).parent / 'languages' / f'{language}.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print(f"[WARNING] No language config found: {config_path}")
            print(f"  Available: {', '.join(p.stem for p in (Path(__file__).parent / 'languages').glob('*.json'))}")
            return {'required_chars': []}

    def get_page(self, url):
        """Fetch a page with error handling"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.ProxyError as e:
            print(f"❌ Network Error: DaFont appears to be blocked by your network/proxy")
            print(f"   You may need to run this script from a different network")
            print(f"   Error: {e}")
            return None
        except requests.RequestException as e:
            print(f"❌ Error fetching {url}: {e}")
            return None

    def get_font_categories(self):
        """Get all font categories from DaFont"""
        # Hardcoded list of major DaFont categories
        # This is more reliable than trying to scrape them
        categories = [
            ("Sans Serif", f"{self.base_url}/theme.php?cat=501"),
            ("Serif", f"{self.base_url}/theme.php?cat=502"),
            ("Fixed Width", f"{self.base_url}/theme.php?cat=503"),
            ("Various", f"{self.base_url}/theme.php?cat=504"),
            ("Script", f"{self.base_url}/theme.php?cat=601"),
            ("School", f"{self.base_url}/theme.php?cat=602"),
            ("Handwritten", f"{self.base_url}/theme.php?cat=603"),
            ("Brush", f"{self.base_url}/theme.php?cat=604"),
            ("Calligraphy", f"{self.base_url}/theme.php?cat=605"),
            ("Graffiti", f"{self.base_url}/theme.php?cat=606"),
            ("Typewriter", f"{self.base_url}/theme.php?cat=607"),
            ("Fancy", f"{self.base_url}/theme.php?cat=701"),
            ("Retro", f"{self.base_url}/theme.php?cat=702"),
            ("Modern", f"{self.base_url}/theme.php?cat=703"),
            ("Decorative", f"{self.base_url}/theme.php?cat=704"),
            ("Cartoon", f"{self.base_url}/theme.php?cat=801"),
            ("Bitmap", f"{self.base_url}/theme.php?cat=901"),
            ("Gothic", f"{self.base_url}/theme.php?cat=902"),
            ("Medieval", f"{self.base_url}/theme.php?cat=903"),
            ("Celtic", f"{self.base_url}/theme.php?cat=904"),
            ("Techno", f"{self.base_url}/theme.php?cat=101"),
            ("LCD", f"{self.base_url}/theme.php?cat=102"),
            ("Holiday", f"{self.base_url}/theme.php?cat=201"),
            ("Valentines", f"{self.base_url}/theme.php?cat=202"),
            ("Halloween", f"{self.base_url}/theme.php?cat=203"),
            ("Christmas", f"{self.base_url}/theme.php?cat=204"),
        ]

        return categories

    def scrape_category(self, category_url, category_name, max_pages=3):
        """Scrape fonts from a category"""
        fonts = []

        for page in range(1, max_pages + 1):
            if page == 1:
                # Add accent filter to the URL
                if '?' in category_url:
                    url = f"{category_url}{self.filter_params}&page={page}"
                else:
                    url = f"{category_url}?psize=m{self.filter_params}&page={page}"
            else:
                # DaFont pagination format
                if '?' in category_url:
                    url = f"{category_url}{self.filter_params}&page={page}"
                else:
                    url = f"{category_url}?psize=m{self.filter_params}&page={page}"

            print(f"  Scraping: {url}")
            html = self.get_page(url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')

            # Find font entries
            font_divs = soup.find_all('div', class_='lv1left')
            if not font_divs:
                # Try alternative structure
                font_divs = soup.find_all('div', style=lambda x: x and 'font-size' in x)

            for font_div in font_divs:
                font_link = font_div.find('a', href=True)
                if font_link:
                    font_name = font_link.get_text(strip=True)
                    # Skip blacklisted fonts
                    if any(bl.lower() in font_name.lower() for bl in self.font_blacklist):
                        if self.verbose:
                            print(f"  [SKIP] Blacklisted font: {font_name}")
                        continue
                    font_url = urljoin(self.base_url, font_link['href'])

                    # Get font details page
                    font_info = self.get_font_details(font_url)
                    if font_info:
                        font_info['name'] = font_name
                        font_info['url'] = font_url
                        font_info['category'] = category_name
                        fonts.append(font_info)

            time.sleep(1)  # Be polite to the server

        return fonts

    def get_font_details(self, font_url):
        """Get detailed information about a font"""
        html = self.get_page(font_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        info = {
            'supports_language': False,
            'download_url': None
        }

        # Look for download link
        for link in soup.find_all('a', href=True):
            if link.get_text(strip=True).lower() == 'download':
                info['download_url'] = urljoin(self.base_url, link['href'])
                break

        # Check font file for language support by downloading and inspecting it
        if info['download_url']:
            language_support = self.check_character_support(info['download_url'])
            info['supports_language'] = language_support

        return info

    def check_character_support(self, download_url):
        """
        Check if a font supports language-specific characters, numbers,
        and punctuation by downloading and inspecting the font file.
        Characters are loaded from the language config file (languages/*.json).
        """
        if not download_url:
            if self.verbose:
                print("      [X] No download URL available")
            return False

        # Download the font file
        try:
            response = requests.get(download_url, headers=self.headers, timeout=30)
            response.raise_for_status()
        except Exception as e:
            if self.verbose:
                print(f"      [X] Failed to download: {e}")
            return False

        # Check if it's a ZIP file
        if response.content[:2] == b'PK':
            try:
                with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                    # Find TTF or OTF files
                    font_files = [f for f in zf.namelist() if f.lower().endswith(('.ttf', '.otf'))]

                    if not font_files:
                        if self.verbose:
                            print("      [X] No font files found in ZIP")
                        return False

                    # Check the first font file
                    font_filename = font_files[0]
                    font_data = zf.read(font_filename)

            except Exception as e:
                if self.verbose:
                    print(f"      [X] Failed to extract ZIP: {e}")
                return False
        else:
            # Direct font file
            font_data = response.content
            font_filename = "font"

        # Load and check the font
        try:
            font = TTFont(io.BytesIO(font_data))
            cmap = font.getBestCmap()

            if not cmap:
                if self.verbose:
                    print("      [X] No character map found in font")
                return False

        except Exception as e:
            if self.verbose:
                print(f"      [X] Failed to load font: {e}")
            return False

        # Check for language-specific characters, numbers, and punctuation
        required_chars = {
            0x0030: ('0', '0'), 0x0031: ('1', '1'), 0x0032: ('2', '2'),
            0x0033: ('3', '3'), 0x0034: ('4', '4'), 0x0035: ('5', '5'),
            0x0036: ('6', '6'), 0x0037: ('7', '7'), 0x0038: ('8', '8'),
            0x0039: ('9', '9'), 0x002D: ('hyphen', '-'),
            0x0028: ('left paren', '('), 0x0029: ('right paren', ')'),
        }
        # Add language-specific characters
        for char in self.required_chars:
            required_chars[ord(char)] = (f'lang: {char}', char)

        results = {}
        for codepoint, (name, char) in required_chars.items():
            if codepoint in cmap:
                glyph_name = cmap[codepoint]
                results[codepoint] = True
                if self.verbose:
                    print(f"      [OK] Found {char} (U+{codepoint:04X}) - {name} [glyph: {glyph_name}]")
            else:
                results[codepoint] = False
                if self.verbose:
                    print(f"      [X] Missing {char} (U+{codepoint:04X}) - {name}")

        # STRICT REQUIREMENT: ALL required characters must be present
        if all(results.values()):
            if self.verbose:
                print(f"      [ACCEPT] Font has all required characters ({self.language})")
            return True
        else:
            if self.verbose:
                missing = [f"{char}" for cp, (name, char) in required_chars.items() if not results.get(cp)]
                print(f"      [REJECT] Font missing: {', '.join(missing)}")
            return False

    def search_with_preview(self, search_text="l·l", category=""):
        """
        Alternative method: Use DaFont's preview feature to test fonts
        This simulates what you'd see when typing in the preview box
        """
        print(f"\nSearching fonts that can display: '{search_text}'")

        # DaFont's preview URL format
        preview_url = f"{self.base_url}/search.php?q={search_text}"
        if category:
            preview_url += f"&cat={category}"

        html = self.get_page(preview_url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        compatible_fonts = []

        # Parse search results
        # This is a simplified version - actual implementation would need to be
        # adjusted based on DaFont's current HTML structure

        return compatible_fonts

    def save_results(self, fonts, filename='compatible_fonts.csv'):
        """Save results to CSV"""
        if not fonts:
            print("No fonts to save")
            return

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'category', 'url', 'supports_language', 'download_url'])
            writer.writeheader()
            writer.writerows(fonts)

        print(f"\n[OK] Results saved to {filename}")

def main():
    parser = argparse.ArgumentParser(description='Scrape DaFont for language-compatible fonts')
    parser.add_argument('--language', default='catalan',
                        help='Language to filter fonts (default: catalan). Options: catalan, spanish, basque, galician, french, english, german, etc.')
    parser.add_argument('--categories', type=int, default=3, help='Number of categories to scrape')
    parser.add_argument('--category-filter', type=str, default=None,
                        help='Filter by category name(s), comma-separated (e.g., "Handwritten,Script,Brush")')
    parser.add_argument('--pages', type=int, default=2, help='Number of pages per category')
    parser.add_argument('--output', default='compatible_fonts.csv', help='Output CSV file')
    parser.add_argument('--no-accent-filter', action='store_true',
                        help='Disable DaFont accent filter (include all fonts)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed character detection information')

    args = parser.parse_args()

    scraper = DaFontScraper(
        language=args.language,
        use_accent_filter=not args.no_accent_filter,
        verbose=args.verbose
    )

    print(f"Starting DaFont scraper for {args.language} fonts...")
    print(f"  Required chars: {', '.join(scraper.required_chars) if scraper.required_chars else '(base only)'}")
    print("=" * 60)
    if scraper.use_accent_filter:
        print("[OK] Using DaFont's accent filter (&a=on)")
    else:
        print("[WARNING] Accent filter disabled - checking all fonts")

    # Get categories
    print("\nFetching font categories...")
    categories = scraper.get_font_categories()
    print(f"Found {len(categories)} categories")

    # Filter categories by name if specified
    if args.category_filter:
        filter_names = [name.strip() for name in args.category_filter.split(',')]
        filtered_categories = [(name, url) for name, url in categories if name in filter_names]

        if not filtered_categories:
            print(f"\n[ERROR] No categories found matching: {', '.join(filter_names)}")
            print(f"Available categories: {', '.join([name for name, _ in categories])}")
            return

        categories_to_scrape = filtered_categories
        print(f"Filtered to {len(categories_to_scrape)} category(ies): {', '.join([name for name, _ in categories_to_scrape])}")
    else:
        categories_to_scrape = categories[:args.categories]

    all_fonts = []
    compatible_fonts = []

    # Scrape fonts from each category
    for i, (cat_name, cat_url) in enumerate(categories_to_scrape, 1):
        print(f"\n[{i}/{len(categories_to_scrape)}] Scraping category: {cat_name}")
        fonts = scraper.scrape_category(cat_url, cat_name, max_pages=args.pages)
        all_fonts.extend(fonts)

        # Filter for language support
        compatible_in_category = [f for f in fonts if f.get('supports_language')]
        compatible_fonts.extend(compatible_in_category)
        print(f"  [OK] Found {len(compatible_in_category)} {args.language}-compatible fonts in this category")

        time.sleep(2)  # Be respectful to the server

    # Results
    print("\n" + "=" * 60)
    print(f"RESULTS:")
    print(f"  Language: {args.language}")
    print(f"  Total fonts scraped: {len(all_fonts)}")
    print(f"  Compatible fonts: {len(compatible_fonts)}")

    if compatible_fonts:
        print(f"\n{args.language.capitalize()}-compatible fonts found:")
        for font in compatible_fonts[:10]:  # Show first 10
            print(f"  • {font['name']}")
            print(f"    {font['url']}")

    # Save results
    scraper.save_results(compatible_fonts, args.output)

    print(f"\n[SUCCESS] Scraping complete!")

if __name__ == "__main__":
    main()
