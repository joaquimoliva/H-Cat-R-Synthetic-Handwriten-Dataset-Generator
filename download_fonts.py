#!/usr/bin/env python3
"""
Script to download fonts from CSV and organize by category
Usage: python download_fonts.py <archivo_csv> [--output-dir fonts]
"""

import csv
import requests
import os
import sys
import time
import argparse
from pathlib import Path
import re
import zipfile
import io

def sanitize_filename(filename):
    """Sanitize filename by removing invalid characters"""
    # Replace invalid characters for Windows/Linux
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove multiple spaces
    filename = re.sub(r'\s+', '_', filename)
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename

def download_font(download_url, font_folder, font_name):
    """Download a font, extract it and save files to folder"""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        print(f"  Downloading: {font_name}...", end=' ')
        response = requests.get(download_url, headers=headers, timeout=30)
        response.raise_for_status()

        file_size = len(response.content) / 1024  # KB

        # Verificar si es un ZIP
        if response.content[:2] == b'PK':  # ZIP file magic number
            try:
                # Descomprimir el ZIP
                with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                    # Extraer todos los archivos a la carpeta de la fuente
                    zf.extractall(font_folder)
                    num_files = len(zf.namelist())
                    print(f"[OK] ({file_size:.1f} KB, {num_files} files extracted)")
                    return True
            except zipfile.BadZipFile:
                print(f"[ERROR] Corrupt ZIP file")
                return False
        else:
            # Si no es ZIP, guardar el archivo directamente (TTF/OTF)
            # Intentar determinar la extensión
            if b'OTTO' in response.content[:4]:
                ext = '.otf'
            elif b'\x00\x01\x00\x00' in response.content[:4] or b'true' in response.content[:4]:
                ext = '.ttf'
            else:
                ext = '.font'  # Generic extension

            output_file = font_folder / f"{font_name}{ext}"
            with open(output_file, 'wb') as f:
                f.write(response.content)

            print(f"[OK] ({file_size:.1f} KB, direct file)")
            return True

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] {e}")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Download fonts and organize by category')
    parser.add_argument('csv_file', help='CSV file with fonts to download')
    parser.add_argument('--output-dir', default='fonts', help='Base directory to save fonts (default: fonts)')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay in seconds between downloads (default: 1.0)')
    parser.add_argument('--skip-existing', action='store_true', help='Skip existing fonts')

    args = parser.parse_args()

    # Verificar que el CSV existe
    if not os.path.exists(args.csv_file):
        print(f"[ERROR] CSV file not found: {args.csv_file}")
        sys.exit(1)

    # Create base directory if not exists
    base_dir = Path(args.output_dir)
    base_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("FONT DOWNLOAD")
    print("=" * 60)
    print(f"CSV: {args.csv_file}")
    print(f"Output directory: {args.output_dir}")
    print(f"Delay between downloads: {args.delay}s")
    print("=" * 60)
    print()

    # Read CSV
    fonts_to_download = []
    categories = set()

    try:
        with open(args.csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Support both old format (supports_language=True) 
                # and new format (supported_languages="catalan,polish,...")
                supported_langs = row.get('supported_languages', '').strip()
                supports_old = row.get('supports_language') == 'True' or row.get('supports_catalan') == 'True'
                
                if supported_langs or supports_old:
                    fonts_to_download.append(row)
                    categories.add(row['category'])
    except Exception as e:
        print(f"[ERROR] Error reading CSV: {e}")
        sys.exit(1)

    print(f"Total fonts to download: {len(fonts_to_download)}")
    print(f"Categories: {', '.join(sorted(categories))}")
    print()

    # Create folders for each category
    for category in categories:
        category_dir = base_dir / category
        category_dir.mkdir(exist_ok=True)
        print(f"[OK] Folder created/verified: {category_dir}")

    print()
    print("Starting download...")
    print("=" * 60)

    # Statistics
    stats = {
        'downloaded': 0,
        'skipped': 0,
        'failed': 0
    }

    # Download each font
    for i, font in enumerate(fonts_to_download, 1):
        font_name = font['name']
        category = font['category']
        download_url = font['download_url']

        print(f"\n[{i}/{len(fonts_to_download)}] {category} / {font_name}")

        # Sanitize name and create folder for font
        safe_name = sanitize_filename(font_name)
        font_folder = base_dir / category / safe_name

        # Check if already exists
        if args.skip_existing and font_folder.exists():
            print(f"  [SKIP] Already exists: {font_folder}")
            stats['skipped'] += 1
            continue

        # Create folder for font
        font_folder.mkdir(parents=True, exist_ok=True)

        # Download and extract
        success = download_font(download_url, font_folder, font_name)

        if success:
            stats['downloaded'] += 1
        else:
            stats['failed'] += 1
            # If fails, remove empty folder
            try:
                if font_folder.exists() and not any(font_folder.iterdir()):
                    font_folder.rmdir()
            except:
                pass

        # Delay between downloads para ser respetuosos con el servidor
        if i < len(fonts_to_download):
            time.sleep(args.delay)

    # Final results
    print()
    print("=" * 60)
    print("RESULTS:")
    print("=" * 60)
    print(f"  Downloaded: {stats['downloaded']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Errors: {stats['failed']}")
    print(f"  Total processed: {len(fonts_to_download)}")
    print()

    # Show summary by category
    print("Summary by category:")
    for category in sorted(categories):
        category_dir = base_dir / category
        num_fonts = len([d for d in category_dir.iterdir() if d.is_dir()])
        print(f"  {category}: {num_fonts} font(s)")

    print()
    print("[SUCCESS] Download completed!")
    print(f"Fonts are organized in: {base_dir.absolute()}")

if __name__ == "__main__":
    main()
