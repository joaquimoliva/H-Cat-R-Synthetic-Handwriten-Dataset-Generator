#!/usr/bin/env python3
"""
Script para descargar textos de Wikipedia en cualquier idioma
mediante la API de MediaWiki.
Objetivo: Crear corpus de texto para dataset sintético de escritura manuscrita.
Compatible con el pipeline de build_dataset.py
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

        # Crear directorio de salida
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_random_articles(self, count=20):
        """Obtiene una lista de artículos aleatorios"""
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'random',
            'rnnamespace': 0,  # Solo artículos (namespace 0)
            'rnlimit': min(count, 20)  # API limita a 20 por petición
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
        """Obtiene artículos de una categoría específica"""
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

                # Comprobar si hay más páginas
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
        """Extrae el texto limpio de un artículo usando la API"""
        params = {
            'action': 'query',
            'format': 'json',
            'titles': title,
            'prop': 'extracts',
            'explaintext': True,  # Texto plano, sin HTML
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

                # Limpiar texto
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
        """Limpia el texto extraído de Wikipedia"""
        # Eliminar secciones no deseadas
        sections_to_remove = [
            'Referències', 'References', 'Bibliografía', 'Bibliography',
            'Enllaços externs', 'External links', 'Enlaces externos',
            'Vegeu també', 'See also', 'Véase también',
            'Notes', 'Notas', 'Footnotes',
            'Fonts', 'Sources', 'Fuentes',
            'Lectura addicional', 'Further reading', 'Lectura adicional'
        ]

        for section in sections_to_remove:
            pattern = rf'==\s*{re.escape(section)}\s*==.*'
            text = re.split(pattern, text, flags=re.IGNORECASE)[0]

        # Eliminar encabezados de sección (== Título ==)
        text = re.sub(r'={2,}.*?={2,}', '', text)

        # Eliminar contenido entre llaves (plantillas residuales)
        text = re.sub(r'\{[^}]*\}', '', text)

        # Eliminar contenido entre corchetes (coordenadas, refs)
        text = re.sub(r'\[[^\]]*\]', '', text)

        # Eliminar URLs
        text = re.sub(r'https?://\S+', '', text)

        # Eliminar líneas que sean solo números (tablas residuales)
        text = re.sub(r'^[\d\s.,]+$', '', text, flags=re.MULTILINE)

        # Eliminar líneas muy cortas (< 10 caracteres) que suelen ser residuos
        lines = text.split('\n')
        lines = [line.strip() for line in lines if len(line.strip()) >= 10]

        # Eliminar líneas duplicadas consecutivas
        cleaned_lines = []
        for line in lines:
            if not cleaned_lines or line != cleaned_lines[-1]:
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def sanitize_filename(self, filename):
        """Sanitiza el nombre del archivo"""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'\s+', '_', filename)
        if len(filename) > 200:
            filename = filename[:200]
        return filename

    def save_content(self, article_title, content, article_index):
        """Guarda el contenido extraído en el mismo formato que scrape_wikisource"""
        safe_name = self.sanitize_filename(article_title)

        # Guardar como texto plano
        txt_file = self.output_dir / f"{article_index:04d}_{safe_name}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(content['text'])

        # Guardar metadatos como JSON
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
            print(f"    [SAVED] {txt_file.name} ({content['num_lines']} líneas, {content['num_words']} palabras)")

    def scrape_all(self, max_articles=100, category=None):
        """Scraping completo de Wikipedia"""
        print("=" * 60)
        print(f"WIKIPEDIA ({self.language.upper()}) - SCRAPER DE ARTÍCULOS")
        print("=" * 60)
        print(f"  Idioma: {self.language}")
        print(f"  Artículos máximos: {max_articles}")
        if category:
            print(f"  Categoría: {category}")
        print()

        # Obtener lista de artículos
        if category:
            print(f"[1] Obteniendo artículos de la categoría '{category}'...")
            articles = self.get_articles_from_category(category, max_articles)
        else:
            print(f"[1] Obteniendo {max_articles} artículos aleatorios...")
            articles = self.get_random_articles(max_articles)

        if not articles:
            print("[ERROR] No se encontraron artículos")
            return

        print(f"  [OK] Encontrados {len(articles)} artículos")

        print(f"\n[2] Procesando artículos...")
        print("=" * 60)

        total_articles = 0
        total_lines = 0
        total_words = 0

        for idx, article in enumerate(articles, 1):
            print(f"\n[{idx}/{len(articles)}] Artículo: {article['title']}")

            # Extraer contenido
            content = self.get_article_text(article['title'])

            if content and content['num_lines'] > 0 and content['num_words'] >= 20:
                self.save_content(article['title'], content, idx)

                total_articles += 1
                total_lines += content['num_lines']
                total_words += content['num_words']
            else:
                if self.verbose:
                    print(f"    [SKIP] Sin contenido suficiente")

            # Delay entre peticiones
            time.sleep(self.delay)

        # Resumen final
        print("\n" + "=" * 60)
        print("RESUMEN FINAL")
        print("=" * 60)
        print(f"  Idioma: {self.language}")
        print(f"  Artículos guardados: {total_articles}")
        print(f"  Total líneas: {total_lines:,}")
        print(f"  Total palabras: {total_words:,}")
        print(f"\n[SUCCESS] Textos guardados en: {self.output_dir.absolute()}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Scraper de Wikipedia para crear corpus de texto multilingüe'
    )
    parser.add_argument('--language', '-l', default='ca',
                        help='Código de idioma (default: ca). Ejemplos: ca, es, eu, gl, en, fr, de, it')
    parser.add_argument('--output-dir', default='data',
                        help='Directorio base de salida (default: data). Se crea subcarpeta wikipedia_[idioma]/')
    parser.add_argument('--max-articles', type=int, default=100,
                        help='Número máximo de artículos a descargar (default: 100)')
    parser.add_argument('--category', type=str, default=None,
                        help='Categoría de Wikipedia de la que obtener artículos (opcional)')
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Delay entre requests en segundos (default: 1.0)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Mostrar información detallada')

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
