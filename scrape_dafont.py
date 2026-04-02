#!/usr/bin/env python3
"""
DaFont Scraper for Language-Compatible Fonts
Finds fonts that support language-specific special characters
Supports multiple languages and records which languages each font supports
Includes watermark detection to filter out problematic fonts
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
import warnings
warnings.filterwarnings("ignore", message=".*timestamp seems very low.*")
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont


class DaFontScraper:
    def __init__(self, languages=None, use_accent_filter=True, verbose=False):
        self.base_url = "https://www.dafont.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.verbose = verbose
        self.use_accent_filter = use_accent_filter
        self.filter_params = "&a=on" if self.use_accent_filter else ""
        
        # Load language configurations
        self.language_configs = self._load_language_configs(languages)
        
        if self.verbose:
            print(f"[INFO] Languages loaded: {', '.join(self.language_configs.keys())}")
        
        # Fonts with known issues: logos, watermarks, broken glyphs
        self.font_blacklist = [
            'Loveletter_No._9',
            'Loveletter No. 9',
            'Autograf',
            'Borgers',
            'MN.SG/BORGERS',
            'Xtreem',                    # Watermark "PERSONAL USE ONLY MN.SG/XTREEM"
            'MN.SG/XTREEM',
            'Scripty',                   # Missing comma glyph
            'Barethelly_Signature',      # Watermark "Din Studio"
            'Barethelly Signature',
            'Arsenale_White',            # Watermark "PERSONAL USE ONLY - ZETAFONTS.COM"
            'Arsenale White',
            'Nowyal',                    # Missing glyphs / watermark
            'Vítkova_písanka',           # Watermark "personal use only - fonty.cendik.ca"
            'Vítkova písanka',
            'Cursif',                    # Empty glyphs for ó/ò
            'Ecolier',                   # Empty glyphs for ó/ò
        ]

    def _load_language_configs(self, languages=None):
        """
        Loads configurations for specified languages.
        If languages is None or 'all', loads all available.
        """
        configs = {}
        languages_dir = Path(__file__).parent / 'languages'
        
        if not languages_dir.exists():
            print(f"[WARNING] Languages directory does not exist: {languages_dir}")
            return configs
        
        available_langs = [p.stem for p in languages_dir.glob('*.json')]
        
        # Determine which languages to load
        if languages is None or languages == ['all'] or 'all' in languages:
            langs_to_load = available_langs
        else:
            langs_to_load = languages
        
        for lang in langs_to_load:
            config_path = languages_dir / f'{lang}.json'
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        configs[lang] = {
                            'required_chars': set(config.get('required_chars', [])),
                            'name': config.get('name', lang)
                        }
                except Exception as e:
                    print(f"[WARNING] Error loading {config_path}: {e}")
            else:
                print(f"[WARNING] Language not found: {lang}")
                print(f"  Available: {', '.join(available_langs)}")
        
        return configs

    def _get_base_required_chars(self):
        """Returns base characters required for all fonts."""
        base_chars = set()
        # Numbers
        for cp in range(0x0030, 0x003A):  # 0-9
            base_chars.add(cp)
        # Basic punctuation and common signs
        base_chars.update([
            0x002C,  # , (comma)
            0x002E,  # . (period)
            0x002D,  # - (hyphen)
            0x0027,  # ' (apostrophe)
            0x0021,  # ! (exclamation)
            0x003F,  # ? (question)
            0x003A,  # : (colon)
            0x003B,  # ; (semicolon)
            0x0028,  # ( (left parenthesis)
            0x0029,  # ) (right parenthesis)
            0x0022,  # " (double quote)
        ])
        return base_chars

    def _check_for_watermark(self, font_data):
        """
        Detects if a font has watermark by generating test images.
        Watermarks often appear in spaces, numbers or punctuation.
        Returns (has_watermark, reason).
        """
        try:
            # Load font with PIL
            font_size = 40
            pil_font = ImageFont.truetype(io.BytesIO(font_data), font_size)
            
            # Test 1: Text with spaces (where watermarks often hide)
            test_text = "A B C D E"
            img = Image.new('RGB', (600, 80), 'white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 15), test_text, font=pil_font, fill='black')
            
            gray = img.convert('L')
            pixels = list(gray.getdata())
            dark_pixels = sum(1 for p in pixels if p < 180)
            total_pixels = len(pixels)
            dark_ratio = dark_pixels / total_pixels
            
            if dark_ratio > 0.08:
                return True, f"Test 1 (spaces): too many dark pixels ({dark_ratio:.1%})"
            
            # Test 2: Numbers (many watermarks appear with numbers)
            test_text2 = "1 2 3 4 5 6 7 8 9 0"
            img2 = Image.new('RGB', (800, 80), 'white')
            draw2 = ImageDraw.Draw(img2)
            draw2.text((10, 15), test_text2, font=pil_font, fill='black')
            
            gray2 = img2.convert('L')
            pixels2 = list(gray2.getdata())
            dark_pixels2 = sum(1 for p in pixels2 if p < 180)
            dark_ratio2 = dark_pixels2 / len(pixels2)
            
            if dark_ratio2 > 0.10:
                return True, f"Test 2 (numbers): too many dark pixels ({dark_ratio2:.1%})"
            
            # Test 3: Long spaces (detect repetitive watermarks)
            test_text3 = "A          B          C"
            img3 = Image.new('RGB', (900, 80), 'white')
            draw3 = ImageDraw.Draw(img3)
            draw3.text((10, 15), test_text3, font=pil_font, fill='black')
            
            gray3 = img3.convert('L')
            pixels3 = list(gray3.getdata())
            dark_pixels3 = sum(1 for p in pixels3 if p < 180)
            dark_ratio3 = dark_pixels3 / len(pixels3)
            
            # With only 3 letters and many spaces, should have very few dark pixels
            if dark_ratio3 > 0.04:
                return True, f"Test 3 (long spaces): content in spaces ({dark_ratio3:.1%})"
            
            # Test 4: Long text to detect small repetitive watermarks
            test_text4 = "Hello, World! Test 123. The quick brown fox."
            img4 = Image.new('RGB', (1200, 80), 'white')
            draw4 = ImageDraw.Draw(img4)
            draw4.text((10, 15), test_text4, font=pil_font, fill='black')
            
            gray4 = img4.convert('L')
            pixels4 = list(gray4.getdata())
            dark_pixels4 = sum(1 for p in pixels4 if p < 180)
            dark_ratio4 = dark_pixels4 / len(pixels4)
            
            if dark_ratio4 > 0.12:
                return True, f"Test 4 (long text): extra content ({dark_ratio4:.1%})"
            
            return False, "OK"
            
        except Exception as e:
            # If we can't check, assume OK
            return False, f"Not verified: {e}"

    def _glyph_renders_correctly(self, font_data, char, font_size=40):
        """
        Verifies that a character renders correctly (not an empty glyph).
        Some fonts declare support for a character in cmap but the glyph is empty.
        """
        try:
            pil_font = ImageFont.truetype(io.BytesIO(font_data), font_size)
            
            # Create small image to render character
            img = Image.new('L', (60, 60), 255)  # White background
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), char, font=pil_font, fill=0)  # Black text
            
            # Count dark pixels
            dark_pixels = sum(1 for p in img.getdata() if p < 200)
            
            # If less than 5 dark pixels, glyph is empty or nearly invisible
            return dark_pixels >= 5
            
        except Exception:
            return False

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
                if '?' in category_url:
                    url = f"{category_url}{self.filter_params}&page={page}"
                else:
                    url = f"{category_url}?psize=m{self.filter_params}&page={page}"
            else:
                if '?' in category_url:
                    url = f"{category_url}{self.filter_params}&page={page}"
                else:
                    url = f"{category_url}?psize=m{self.filter_params}&page={page}"

            print(f"  Scraping: {url}")
            html = self.get_page(url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')

            font_divs = soup.find_all('div', class_='lv1left')
            if not font_divs:
                font_divs = soup.find_all('div', style=lambda x: x and 'font-size' in x)

            for font_div in font_divs:
                font_link = font_div.find('a', href=True)
                if font_link:
                    font_name = font_link.get_text(strip=True)
                    if any(bl.lower() in font_name.lower() for bl in self.font_blacklist):
                        if self.verbose:
                            print(f"  [SKIP] Blacklisted font: {font_name}")
                        continue
                    font_url = urljoin(self.base_url, font_link['href'])

                    font_info = self.get_font_details(font_url)
                    if font_info:
                        font_info['name'] = font_name
                        font_info['url'] = font_url
                        font_info['category'] = category_name
                        fonts.append(font_info)

            time.sleep(1)

        return fonts

    def get_font_details(self, font_url):
        """Get detailed information about a font"""
        html = self.get_page(font_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        info = {
            'supported_languages': [],
            'download_url': None
        }

        for link in soup.find_all('a', href=True):
            if link.get_text(strip=True).lower() == 'download':
                info['download_url'] = urljoin(self.base_url, link['href'])
                break

        if info['download_url']:
            supported = self.check_language_support(info['download_url'])
            info['supported_languages'] = supported

        return info

    def check_language_support(self, download_url):
        """
        Checks which languages a font supports by downloading and inspecting it.
        Returns a list of supported languages.
        """
        if not download_url:
            return []

        try:
            response = requests.get(download_url, headers=self.headers, timeout=30)
            response.raise_for_status()
        except Exception as e:
            if self.verbose:
                print(f"      [X] Failed to download: {e}")
            return []

        # Extract font from ZIP
        content_type = response.headers.get('Content-Type', '')
        if 'zip' in content_type or download_url.endswith('.zip') or response.content[:2] == b'PK':
            try:
                with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                    font_files = [
                        name for name in zf.namelist()
                        if name.lower().endswith(('.ttf', '.otf'))
                        and not name.startswith('__MACOSX')
                    ]

                    if not font_files:
                        if self.verbose:
                            print("      [X] No font files found in ZIP")
                        return []

                    font_filename = font_files[0]
                    font_data = zf.read(font_filename)

            except Exception as e:
                if self.verbose:
                    print(f"      [X] Failed to extract ZIP: {e}")
                return []
        else:
            font_data = response.content

        # Load font and get cmap
        try:
            font = TTFont(io.BytesIO(font_data))
            cmap = font.getBestCmap()

            if not cmap:
                if self.verbose:
                    print("      [X] No character map found in font")
                return []

        except Exception as e:
            if self.verbose:
                print(f"      [X] Failed to load font: {e}")
            return []

        # First, verify base characters (numbers, punctuation)
        base_chars = self._get_base_required_chars()
        for cp in base_chars:
            if cp not in cmap:
                if self.verbose:
                    print(f"      [X] Missing base char U+{cp:04X}")
                return []

        # Now, check each language
        supported_languages = []
        
        for lang, config in self.language_configs.items():
            required_chars = config['required_chars']
            
            if not required_chars:
                # Language without special characters (e.g. English)
                supported_languages.append(lang)
                continue
            
            all_present = True
            missing = []
            empty_glyphs = []
            
            for char in required_chars:
                cp = ord(char)
                if cp not in cmap:
                    all_present = False
                    missing.append(char)
                else:
                    # Verify glyph renders (not empty)
                    if not self._glyph_renders_correctly(font_data, char):
                        all_present = False
                        empty_glyphs.append(char)
            
            if all_present:
                supported_languages.append(lang)
                if self.verbose:
                    print(f"      [OK] Supports {lang}")
            else:
                if self.verbose:
                    if missing:
                        print(f"      [X] {lang}: missing {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")
                    if empty_glyphs:
                        print(f"      [X] {lang}: empty glyphs {', '.join(empty_glyphs[:5])}{'...' if len(empty_glyphs) > 5 else ''}")

        # If font supports any language, check watermarks
        if supported_languages:
            has_watermark, reason = self._check_for_watermark(font_data)
            if has_watermark:
                if self.verbose:
                    print(f"      [WATERMARK] {reason}")
                return []  # Discard font

        return supported_languages

    def save_results(self, fonts, filename='compatible_fonts.csv'):
        """Save results to CSV with supported_languages column"""
        if not fonts:
            print("No fonts to save")
            return

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'name', 'category', 'url', 'download_url', 'supported_languages'
            ])
            writer.writeheader()
            
            for font in fonts:
                row = {
                    'name': font['name'],
                    'category': font['category'],
                    'url': font['url'],
                    'download_url': font['download_url'],
                    'supported_languages': ','.join(font.get('supported_languages', []))
                }
                writer.writerow(row)

        print(f"\n[OK] Results saved to {filename}")


def main():
    parser = argparse.ArgumentParser(description='Scrape DaFont for language-compatible fonts')
    parser.add_argument('--language', default='all',
                        help='Languages to check, comma-separated (default: all). '
                             'Ex: --language catalan,spanish,romanian or --language all')
    parser.add_argument('--categories', type=int, default=3, help='Number of categories to scrape')
    parser.add_argument('--category-filter', type=str, default=None,
                        help='Filter by category name(s), comma-separated (e.g., "Handwritten,Script,Brush")')
    parser.add_argument('--pages', type=int, default=2, help='Number of pages per category')
    parser.add_argument('--output', default='compatible_fonts.csv', help='Output CSV file')
    parser.add_argument('--no-accent-filter', action='store_true',
                        help='Disable DaFont accent filter (include all fonts)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed character detection information')
    parser.add_argument('--min-languages', type=int, default=1,
                        help='Minimum languages a font must support to be included (default: 1)')

    args = parser.parse_args()

    # Parse languages
    if args.language.lower() == 'all':
        languages = ['all']
    else:
        languages = [l.strip() for l in args.language.split(',')]

    scraper = DaFontScraper(
        languages=languages,
        use_accent_filter=not args.no_accent_filter,
        verbose=args.verbose
    )

    print(f"Starting DaFont scraper...")
    print(f"  Languages to check: {', '.join(scraper.language_configs.keys())}")
    print(f"  Minimum languages per font: {args.min_languages}")
    print("=" * 60)
    
    if scraper.use_accent_filter:
        print("[OK] Using DaFont's accent filter (&a=on)")
    else:
        print("[WARNING] Accent filter disabled - checking all fonts")

    print("\nFetching font categories...")
    categories = scraper.get_font_categories()
    print(f"Found {len(categories)} categories")

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

    for i, (cat_name, cat_url) in enumerate(categories_to_scrape, 1):
        print(f"\n[{i}/{len(categories_to_scrape)}] Scraping category: {cat_name}")
        fonts = scraper.scrape_category(cat_url, cat_name, max_pages=args.pages)
        all_fonts.extend(fonts)
        time.sleep(2)

    # Filter fonts that support at least N languages
    compatible_fonts = [
        f for f in all_fonts 
        if len(f.get('supported_languages', [])) >= args.min_languages
    ]

    # Statistics per language
    lang_stats = {}
    for lang in scraper.language_configs.keys():
        count = sum(1 for f in compatible_fonts if lang in f.get('supported_languages', []))
        lang_stats[lang] = count

    # Results
    print("\n" + "=" * 60)
    print(f"RESULTS:")
    print(f"  Total fonts scanned: {len(all_fonts)}")
    print(f"  Compatible fonts (≥{args.min_languages} language): {len(compatible_fonts)}")
    
    print(f"\n  Fonts per language:")
    for lang, count in sorted(lang_stats.items(), key=lambda x: -x[1]):
        print(f"    {lang}: {count}")

    if compatible_fonts:
        print(f"\nFirst 10 compatible fonts:")
        for font in compatible_fonts[:10]:
            langs = ', '.join(font.get('supported_languages', []))
            print(f"  • {font['name']}")
            print(f"    Languages: {langs}")

    scraper.save_results(compatible_fonts, args.output)

    print(f"\n[SUCCESS] Scraping complete!")
    print(f"  CSV: {args.output}")
    print(f"  Format: name,category,url,download_url,supported_languages")


if __name__ == "__main__":
    main()
