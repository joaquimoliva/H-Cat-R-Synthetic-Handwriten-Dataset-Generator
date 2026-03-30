#!/usr/bin/env python3
"""
Genera fons de paper sintètics per al dataset.
Crea 9 combinacions: 3 colors (white, grey, beige) × 3 tipus (plain, grid, lined).
Ús: python generate_backgrounds.py -v
"""

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import random
import numpy as np


def add_noise(img, intensity=10):
    """Afegeix soroll de textura al paper"""
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, intensity, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def get_base_color(color_name):
    """Retorna color RGB i intensitat de soroll segons el nom del color"""
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
    Retorna un color de línia amb bon contrast segons el color de fons.
    Les línies han de ser prou diferents del fons per ser visibles.
    """
    if color_name == 'white':
        # Fons blanc (~245-255): línies blaves/grises clares funcionen bé
        return random.choice([
            (180, 210, 230),  # Blau clar
            (200, 215, 230),  # Blau molt clar
            (190, 200, 210),  # Gris blavós
            (175, 205, 175),  # Verd clar
        ])
    elif color_name == 'grey':
        # Fons gris (~195-215): necessitem línies MÉS FOSQUES per contrast
        return random.choice([
            (140, 170, 200),  # Blau mitjà (bon contrast)
            (150, 150, 170),  # Gris blavós fosc
            (130, 160, 190),  # Blau steel
            (145, 175, 145),  # Verd mitjà
        ])
    elif color_name == 'beige':
        # Fons beix (~230-245, ~218-232, ~185-205): línies blaves/grises clares
        return random.choice([
            (170, 195, 220),  # Blau clar
            (180, 190, 200),  # Gris blavós
            (165, 185, 165),  # Verd suau
            (175, 200, 215),  # Blau cel
        ])


def get_lined_line_color(color_name):
    """
    Retorna un color de línia horitzontal amb bon contrast segons el fons.
    """
    if color_name == 'white':
        return random.choice([
            (170, 200, 230),  # Blau clar
            (185, 195, 210),  # Gris blavós
        ])
    elif color_name == 'grey':
        # Necessitem línies més fosques per veure-les sobre gris
        return random.choice([
            (130, 160, 195),  # Blau mitjà
            (140, 150, 165),  # Gris fosc blavós
        ])
    elif color_name == 'beige':
        return random.choice([
            (165, 190, 220),  # Blau clar
            (175, 185, 200),  # Gris blavós
        ])


def add_paper_texture(img, draw, color, color_name, width, height):
    """Afegeix textura de paper segons el color"""
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
    """Fons llis sense patró"""
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
    """Fons quadriculat amb colors de línia adaptats al fons"""
    folder = output_dir / f'grid_{color_name}'
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        color, noise = get_base_color(color_name)
        img = Image.new('RGB', (width, height), color)
        img = add_noise(img, intensity=noise)
        draw = ImageDraw.Draw(img)
        img = add_paper_texture(img, draw, color, color_name, width, height)

        draw = ImageDraw.Draw(img)
        # Mida de quadrícula realista: una lletra ha de cabre en ~1-2 files
        # Text típic ~100-150px, quadrícules de 60-80px són proporcionals
        grid_size = random.choice([60, 70, 80])
        
        # Color de línia adaptat al fons per garantir contrast
        line_color = get_grid_line_color(color_name)
        
        for x in range(0, width, grid_size):
            draw.line([(x, 0), (x, height)], fill=line_color, width=1)
        for y in range(0, height, grid_size):
            draw.line([(0, y), (width, y)], fill=line_color, width=1)

        img.save(folder / f'grid_{color_name}_{i+1:03d}.png')


def generate_lined(width, height, count, output_dir, color_name):
    """Fons pautat amb marge aleatori i colors de línia adaptats"""
    folder = output_dir / f'lined_{color_name}'
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        color, noise = get_base_color(color_name)
        img = Image.new('RGB', (width, height), color)
        img = add_noise(img, intensity=noise)
        draw = ImageDraw.Draw(img)
        img = add_paper_texture(img, draw, color, color_name, width, height)

        draw = ImageDraw.Draw(img)
        # Espai entre línies realista: similar a quadrícules, text ~100-150px
        line_spacing = random.choice([60, 70, 80])
        
        # Color de línia adaptat al fons
        line_color = get_lined_line_color(color_name)
        
        for y in range(line_spacing, height, line_spacing):
            draw.line([(0, y), (width, y)], fill=line_color, width=1)

        if random.random() < 0.5:
            margin_x = random.randint(60, 90)
            draw.line([(margin_x, 0), (margin_x, height)], fill=(220, 100, 100), width=1)

        img.save(folder / f'lined_{color_name}_{i+1:03d}.png')


def main():
    parser = argparse.ArgumentParser(
        description='Genera fons de paper sintètics (3 colors × 3 tipus = 9 combinacions)'
    )
    parser.add_argument('--output-dir', default='backgrounds',
                        help='Directori de sortida (default: backgrounds)')
    parser.add_argument('--width', type=int, default=2000,
                        help='Amplada de les imatges (default: 2000)')
    parser.add_argument('--height', type=int, default=400,
                        help='Alçada de les imatges (default: 400)')
    parser.add_argument('--count', type=int, default=5,
                        help='Nombre d\'imatges per combinació (default: 5)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Mostrar informació detallada')

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    colors = ['white', 'grey', 'beige']
    types_map = {
        'plain': generate_plain,
        'grid': generate_grid,
        'lined': generate_lined,
    }

    print("=" * 60)
    print("  GENERADOR DE FONS DE PAPER")
    print("=" * 60)
    print(f"  Directori: {output_dir}")
    print(f"  Mida: {args.width}x{args.height}")
    print(f"  Imatges per combinació: {args.count}")
    print(f"  Combinacions: {len(colors)} colors × {len(types_map)} tipus = {len(colors) * len(types_map)}")
    print("=" * 60)

    for type_name, gen_func in types_map.items():
        for color_name in colors:
            gen_func(args.width, args.height, args.count, output_dir, color_name)
            if args.verbose:
                print(f"  [OK] {type_name}_{color_name}: {args.count} imatges")

    total = args.count * len(colors) * len(types_map)
    print(f"\n[SUCCESS] {total} fons generats a {output_dir.absolute()}")


if __name__ == "__main__":
    main()
