#!/usr/bin/env python3
"""
Generate synthetic paper backgrounds for the dataset.
Creates 9 combinations: 3 colors (white, grey, beige) × 3 types (plain, grid, lined).
Usage: python generate_backgrounds.py -v
"""

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import random
import numpy as np


def add_noise(img, intensity=10):
    """Add texture noise to paper"""
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, intensity, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def get_base_color(color_name):
    """Return RGB color and noise intensity based on color name"""
    if color_name == 'white':
        base = random.randint(245, 255)
        return (base, base, base), 3
    elif color_name == 'grey':
        base = random.randint(195, 215)
        return (base + random.randint(-3, 3),
                base + random.randint(-3, 3),
                base + random.randint(-2, 4)), 6
    elif color_name == 'beige':
        return (random.randint(230, 245),
                random.randint(218, 232),
                random.randint(185, 205)), 5


def get_grid_line_color(color_name):
    """
    Return a line color with good contrast based on background color.
    Lines must be sufficiently different from background to be visible.
    """
    if color_name == 'white':
        # White background (~245-255): light blue/gray lines work well
        return random.choice([
            (180, 210, 230),  # Light blue
            (200, 215, 230),  # Very light blue
            (190, 200, 210),  # Bluish gray
            (175, 205, 175),  # Light green
        ])
    elif color_name == 'grey':
        # Gray background (~195-215): we need DARKER lines for contrast
        return random.choice([
            (140, 170, 200),  # Medium blue (good contrast)
            (150, 150, 170),  # Bluish gray fosc
            (130, 160, 190),  # Steel blue
            (145, 175, 145),  # Medium green
        ])
    elif color_name == 'beige':
        # Beige background (~230-245, ~218-232, ~185-205): línies blaves/grises clares
        return random.choice([
            (170, 195, 220),  # Light blue
            (180, 190, 200),  # Bluish gray
            (165, 185, 165),  # Soft green
            (175, 200, 215),  # Sky blue
        ])


def get_lined_line_color(color_name):
    """
    Return a horizontal line color with good contrast based on background.
    """
    if color_name == 'white':
        return random.choice([
            (170, 200, 230),  # Light blue
            (185, 195, 210),  # Bluish gray
        ])
    elif color_name == 'grey':
        # We need darker lines to see them on gray
        return random.choice([
            (130, 160, 195),  # Blau mitjà
            (140, 150, 165),  # Dark bluish gray
        ])
    elif color_name == 'beige':
        return random.choice([
            (165, 190, 220),  # Light blue
            (175, 185, 200),  # Bluish gray
        ])


def add_paper_texture(img, draw, color, color_name, width, height):
    """Add paper texture based on color"""
    if color_name == 'grey':
        for _ in range(random.randint(15, 40)):
            x = random.randint(0, width)
            y = random.randint(0, height)
            size = random.randint(1, 3)
            cv = random.randint(-10, 10)
            spot = tuple(max(0, min(255, c + cv)) for c in color)
            draw.ellipse([x, y, x + size, y + size], fill=spot)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    elif color_name == 'beige':
        for _ in range(random.randint(5, 15)):
            x = random.randint(0, width - 30)
            y = random.randint(0, height - 15)
            size = random.randint(8, 25)
            spot = (max(0, color[0] - random.randint(8, 20)),
                    max(0, color[1] - random.randint(10, 25)),
                    max(0, color[2] - random.randint(15, 30)))
            draw.ellipse([x, y, x + size, y + size], fill=spot)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
    return img


def generate_plain(width, height, count, output_dir, color_name):
    """Plain background without pattern"""
    folder = output_dir / f'plain_{color_name}'
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        color, noise = get_base_color(color_name)
        img = Image.new('RGB', (width, height), color)
        img = add_noise(img, intensity=noise)
        draw = ImageDraw.Draw(img)
        img = add_paper_texture(img, draw, color, color_name, width, height)
        img.save(folder / f'plain_{color_name}_{i+1:03d}.png')


def generate_grid(width, height, count, output_dir, color_name):
    """Grid background with line colors adapted to background"""
    folder = output_dir / f'grid_{color_name}'
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        color, noise = get_base_color(color_name)
        img = Image.new('RGB', (width, height), color)
        img = add_noise(img, intensity=noise)
        draw = ImageDraw.Draw(img)
        img = add_paper_texture(img, draw, color, color_name, width, height)

        draw = ImageDraw.Draw(img)
        # Realistic grid size: a letter should fit in ~1-2 rows
        # Typical text ~100-150px, 60-80px grids are proportional
        grid_size = random.choice([60, 70, 80])
        
        # Line color adapted to background to ensure contrast
        line_color = get_grid_line_color(color_name)
        
        for x in range(0, width, grid_size):
            draw.line([(x, 0), (x, height)], fill=line_color, width=1)
        for y in range(0, height, grid_size):
            draw.line([(0, y), (width, y)], fill=line_color, width=1)

        img.save(folder / f'grid_{color_name}_{i+1:03d}.png')


def generate_lined(width, height, count, output_dir, color_name):
    """Lined background with random margin and adapted line colors"""
    folder = output_dir / f'lined_{color_name}'
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        color, noise = get_base_color(color_name)
        img = Image.new('RGB', (width, height), color)
        img = add_noise(img, intensity=noise)
        draw = ImageDraw.Draw(img)
        img = add_paper_texture(img, draw, color, color_name, width, height)

        draw = ImageDraw.Draw(img)
        # Realistic line spacing: similar to grids, text ~100-150px
        line_spacing = random.choice([60, 70, 80])
        
        # Line color adapted to background
        line_color = get_lined_line_color(color_name)
        
        for y in range(line_spacing, height, line_spacing):
            draw.line([(0, y), (width, y)], fill=line_color, width=1)

        if random.random() < 0.5:
            margin_x = random.randint(60, 90)
            draw.line([(margin_x, 0), (margin_x, height)], fill=(220, 100, 100), width=1)

        img.save(folder / f'lined_{color_name}_{i+1:03d}.png')


def main():
    parser = argparse.ArgumentParser(
        description='Generate synthetic paper backgrounds (3 colors × 3 types = 9 combinations)'
    )
    parser.add_argument('--output-dir', default='backgrounds',
                        help='Output directory (default: backgrounds)')
    parser.add_argument('--width', type=int, default=2000,
                        help='Image width (default: 2000)')
    parser.add_argument('--height', type=int, default=400,
                        help='Image height (default: 400)')
    parser.add_argument('--count', type=int, default=5,
                        help='Nombre d\'images per combinació (default: 5)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed information')

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    colors = ['white', 'grey', 'beige']
    types_map = {
        'plain': generate_plain,
        'grid': generate_grid,
        'lined': generate_lined,
    }

    print("=" * 60)
    print("  PAPER BACKGROUND GENERATOR")
    print("=" * 60)
    print(f"  Directory: {output_dir}")
    print(f"  Size: {args.width}x{args.height}")
    print(f"  Images per combination: {args.count}")
    print(f"  Combinations: {len(colors)} colors × {len(types_map)} types = {len(colors) * len(types_map)}")
    print("=" * 60)

    for type_name, gen_func in types_map.items():
        for color_name in colors:
            gen_func(args.width, args.height, args.count, output_dir, color_name)
            if args.verbose:
                print(f"  [OK] {type_name}_{color_name}: {args.count} images")

    total = args.count * len(colors) * len(types_map)
    print(f"\n[SUCCESS] {total} backgrounds generated in {output_dir.absolute()}")


if __name__ == "__main__":
    main()
