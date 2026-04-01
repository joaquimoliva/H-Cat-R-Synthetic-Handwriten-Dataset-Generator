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
        
        # Carregar configuracions d'idiomes
        self.language_configs = self._load_language_configs(languages)
        
        if self.verbose:
            print(f"[INFO] Idiomes carregats: {', '.join(self.language_configs.keys())}")
        
        # Fonts amb problemes coneguts: logos, watermarks, glifs trencats
        self.font_blacklist = [
            'Loveletter_No._9',
            'Loveletter No. 9',
            'Autograf',
            'Borgers',
            'MN.SG/BORGERS',
            'Xtreem',                    # Watermark "PERSONAL USE ONLY MN.SG/XTREEM"
            'MN.SG/XTREEM',
            'Scripty',                   # Falta glif coma
            'Barethelly_Signature',      # Watermark "Din Studio"
            'Barethelly Signature',
        ]

    def _load_language_configs(self, languages=None):
        """
        Carrega les configuracions dels idiomes especificats.
        Si languages és None o 'all', carrega tots els disponibles.
        """
        configs = {}
        languages_dir = Path(__file__).parent / 'languages'
        
        if not languages_dir.exists():
            print(f"[WARNING] Directori languages/ no existeix: {languages_dir}")
            return configs
        
        available_langs = [p.stem for p in languages_dir.glob('*.json')]
        
        # Determinar quins idiomes carregar
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
                    print(f"[WARNING] Error carregant {config_path}: {e}")
            else:
                print(f"[WARNING] Idioma no trobat: {lang}")
                print(f"  Disponibles: {', '.join(available_langs)}")
        
        return configs

    def _get_base_required_chars(self):
        """Retorna els caràcters base requerits per totes les fonts."""
        base_chars = set()
        # Números
        for cp in range(0x0030, 0x003A):  # 0-9
            base_chars.add(cp)
        # Puntuació bàsica i signes comuns
        base_chars.update([
            0x002C,  # , (coma)
            0x002E,  # . (punt)
            0x002D,  # - (guió)
            0x0027,  # ' (apòstrof)
            0x0021,  # ! (exclamació)
            0x003F,  # ? (interrogació)
            0x003A,  # : (dos punts)
            0x003B,  # ; (punt i coma)
            0x0028,  # ( (parèntesi esquerre)
            0x0029,  # ) (parèntesi dret)
            0x0022,  # " (cometes dobles)
        ])
        return base_chars

    def _check_for_watermark(self, font_data):
        """
        Detecta si una font té watermark generant una imatge de prova.
        Els watermarks sovint apareixen als espais o puntuació.
        Retorna (has_watermark, reason).
        """
        try:
            # Carregar font amb PIL
            font_size = 40
            pil_font = ImageFont.truetype(io.BytesIO(font_data), font_size)
            
            # Text de prova amb espais (on sovint s'amaguen watermarks)
            test_text = "A B C D E"
            
            # Crear imatge
            img = Image.new('RGB', (600, 80), 'white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 15), test_text, font=pil_font, fill='black')
            
            # Analitzar: comptar píxels foscos
            gray = img.convert('L')
            pixels = list(gray.getdata())
            dark_pixels = sum(1 for p in pixels if p < 180)
            
            # Calcular ràtio
            # "A B C D E" té 5 lletres, els espais no haurien de tenir píxels
            # Si hi ha masses píxels foscos, probablement hi ha watermark als espais
            expected_chars = 5
            total_pixels = len(pixels)
            dark_ratio = dark_pixels / total_pixels
            
            # Threshold: si el ràtio és molt alt pel nombre de caràcters
            # Una font normal amb 5 lletres tindria ~1-3% píxels foscos
            # Si en té >8%, sospitós (watermark als espais)
            if dark_ratio > 0.08:
                return True, f"Massa píxels foscos ({dark_ratio:.1%}), possible watermark"
            
            # Segon test: text més llarg per detectar watermarks repetitius
            test_text2 = "Hello, World! Test 123."
            img2 = Image.new('RGB', (800, 80), 'white')
            draw2 = ImageDraw.Draw(img2)
            draw2.text((10, 15), test_text2, font=pil_font, fill='black')
            
            gray2 = img2.convert('L')
            pixels2 = list(gray2.getdata())
            dark_pixels2 = sum(1 for p in pixels2 if p < 180)
            dark_ratio2 = dark_pixels2 / len(pixels2)
            
            # Amb més text, el ràtio hauria de ser similar o lleugerament més alt
            # Si és molt més alt, hi ha contingut extra (watermark)
            if dark_ratio2 > 0.12:
                return True, f"Contingut extra detectat ({dark_ratio2:.1%})"
            
            return False, "OK"
            
        except Exception as e:
            # Si no podem comprovar, assumim OK (millor falsos negatius que rebutjar bones fonts)
            return False, f"No verificat: {e}"

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
        Comprova quins idiomes suporta una font descarregant-la i inspeccionant-la.
        Retorna una llista d'idiomes suportats.
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

        # Extreure font del ZIP
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

        # Carregar font i obtenir cmap
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

        # Primer, verificar caràcters base (números, puntuació)
        base_chars = self._get_base_required_chars()
        for cp in base_chars:
            if cp not in cmap:
                if self.verbose:
                    print(f"      [X] Missing base char U+{cp:04X}")
                return []

        # Ara, comprovar cada idioma
        supported_languages = []
        
        for lang, config in self.language_configs.items():
            required_chars = config['required_chars']
            
            if not required_chars:
                # Idioma sense caràcters especials (ex: anglès)
                supported_languages.append(lang)
                continue
            
            all_present = True
            missing = []
            
            for char in required_chars:
                cp = ord(char)
                if cp not in cmap:
                    all_present = False
                    missing.append(char)
            
            if all_present:
                supported_languages.append(lang)
                if self.verbose:
                    print(f"      [OK] Suporta {lang}")
            else:
                if self.verbose:
                    print(f"      [X] {lang}: falten {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")

        # Si la font suporta algun idioma, comprovar watermarks
        if supported_languages:
            has_watermark, reason = self._check_for_watermark(font_data)
            if has_watermark:
                if self.verbose:
                    print(f"      [WATERMARK] {reason}")
                return []  # Descartar font

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
                        help='Idiomes a comprovar, separats per comes (default: all). '
                             'Ex: --language catalan,spanish,romanian o --language all')
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
                        help='Mínim d\'idiomes que ha de suportar una font per ser inclosa (default: 1)')

    args = parser.parse_args()

    # Parsejar idiomes
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
    print(f"  Idiomes a comprovar: {', '.join(scraper.language_configs.keys())}")
    print(f"  Mínim idiomes per font: {args.min_languages}")
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

    # Filtrar fonts que suporten mínim N idiomes
    compatible_fonts = [
        f for f in all_fonts 
        if len(f.get('supported_languages', [])) >= args.min_languages
    ]

    # Estadístiques per idioma
    lang_stats = {}
    for lang in scraper.language_configs.keys():
        count = sum(1 for f in compatible_fonts if lang in f.get('supported_languages', []))
        lang_stats[lang] = count

    # Results
    print("\n" + "=" * 60)
    print(f"RESULTATS:")
    print(f"  Total fonts escanejades: {len(all_fonts)}")
    print(f"  Fonts compatibles (≥{args.min_languages} idioma): {len(compatible_fonts)}")
    
    print(f"\n  Fonts per idioma:")
    for lang, count in sorted(lang_stats.items(), key=lambda x: -x[1]):
        print(f"    {lang}: {count}")

    if compatible_fonts:
        print(f"\nPrimeres 10 fonts compatibles:")
        for font in compatible_fonts[:10]:
            langs = ', '.join(font.get('supported_languages', []))
            print(f"  • {font['name']}")
            print(f"    Idiomes: {langs}")

    scraper.save_results(compatible_fonts, args.output)

    print(f"\n[SUCCESS] Scraping complete!")
    print(f"  CSV: {args.output}")
    print(f"  Format: name,category,url,download_url,supported_languages")


if __name__ == "__main__":
    main()
