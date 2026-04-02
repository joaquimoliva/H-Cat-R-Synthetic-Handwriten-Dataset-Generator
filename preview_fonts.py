#!/usr/bin/env python3
"""
Generate a visual catalog of all available fonts.
Allows quick inspection of which fonts look like real handwriting.
Usage: python preview_fonts.py --category Handwritten -v
"""

import os
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math


def generate_font_preview(fonts_dir='fonts', output_file='font_preview.png',
                          category_filter=None, sample_text=None, verbose=False):
    """Generate an image with preview of all fonts"""

    fonts_dir = Path(fonts_dir)

    if sample_text is None:
        sample_text = "El vent satisfà la gent 0123"

    # Collect all fonts
    fonts = []
    for root, dirs, files in os.walk(fonts_dir):
        for file in files:
            if file.lower().endswith(('.ttf', '.otf')):
                font_path = Path(root) / file
                rel_path = font_path.relative_to(fonts_dir)
                parts = rel_path.parts

                # Get category
                category = parts[0] if len(parts) > 1 else 'Unknown'

                # Apply category filter
                if category_filter and category.lower() != category_filter.lower():
                    continue

                # Get font name
                font_name = parts[1] if len(parts) > 1 else parts[0]

                # Avoid duplicates (take only first variant)
                font_key = f"{category}/{font_name}"

                fonts.append({
                    'path': font_path,
                    'name': font_name,
                    'category': category,
                    'key': font_key
                })

    # Remove duplicates by font folder
    seen = set()
    unique_fonts = []
    for f in fonts:
        if f['key'] not in seen:
            seen.add(f['key'])
            unique_fonts.append(f)
    fonts = sorted(unique_fonts, key=lambda x: (x['category'], x['name']))

    if not fonts:
        print("[ERROR] No fonts found")
        return

    print(f"[INFO] {len(fonts)} fonts found")

    # Image configuration
    row_height = 80
    label_width = 300
    sample_width = 800
    img_width = label_width + sample_width
    img_height = row_height * len(fonts) + 40  # +40 per al títol

    # Create image
    img = Image.new('RGB', (img_width, img_height), 'white')
    draw = ImageDraw.Draw(img)

    # Title
    try:
        title_font = ImageFont.truetype("arial.ttf", 20)
        label_font = ImageFont.truetype("arial.ttf", 14)
    except:
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
            label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except:
            title_font = ImageFont.load_default()
            label_font = ImageFont.load_default()

    title = f"Font Catalog"
    if category_filter:
        title += f" - Category: {category_filter}"
    title += f" ({len(fonts)} fonts)"
    draw.text((10, 10), title, font=title_font, fill='black')

    # Render each font
    y_pos = 40
    for idx, font_info in enumerate(fonts):
        # Alternating background
        if idx % 2 == 0:
            draw.rectangle([(0, y_pos), (img_width, y_pos + row_height)], fill='#F8F8F8')

        # Number and font name
        label = f"{idx+1:3d}. [{font_info['category']}] {font_info['name']}"
        draw.text((10, y_pos + 5), label, font=label_font, fill='#333333')

        # Render sample text
        try:
            # Try with size 36
            sample_font = ImageFont.truetype(str(font_info['path']), 36)
            bbox = draw.textbbox((0, 0), sample_text, font=sample_font)
            text_height = bbox[3] - bbox[1]

            # Adjust if too large
            if text_height > row_height * 0.7:
                scale = (row_height * 0.6) / text_height
                sample_font = ImageFont.truetype(str(font_info['path']), int(36 * scale))

            text_y = y_pos + (row_height - text_height) // 2
            draw.text((label_width + 10, text_y), sample_text, font=sample_font, fill='black')

            if verbose:
                print(f"  [OK] {font_info['name']}")

        except Exception as e:
            draw.text((label_width + 10, y_pos + 25), f"[ERROR: {e}]",
                      font=label_font, fill='red')
            if verbose:
                print(f"  [ERROR] {font_info['name']}: {e}")

        # Separator line
        draw.line([(0, y_pos + row_height), (img_width, y_pos + row_height)], fill='#DDDDDD')

        y_pos += row_height

    # Save
    img.save(output_file)
    print(f"\n[SUCCESS] Catalog saved to: {output_file}")
    print(f"  Size: {img_width}x{img_height} pixels")
    print(f"  Fonts shown: {len(fonts)}")
    print(f"\nOpen the image and mark fonts you do NOT want to use.")
    print(f"Then you can delete the corresponding folders from fonts/")


def main():
    parser = argparse.ArgumentParser(
        description='Generate a visual catalog of available fonts'
    )
    parser.add_argument('--fonts-dir', default='fonts',
                        help='Fonts directory (default: fonts)')
    parser.add_argument('--output', '-o', default='font_preview.png',
                        help='Output file (default: font_preview.png)')
    parser.add_argument('--category-filter', default=None,
                        help='Filter by category (ex: Handwritten, Script, Brush)')
    parser.add_argument('--sample-text', default=None,
                        help='Custom sample text')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed information')

    args = parser.parse_args()

    generate_font_preview(
        fonts_dir=args.fonts_dir,
        output_file=args.output,
        category_filter=args.category_filter,
        sample_text=args.sample_text,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
