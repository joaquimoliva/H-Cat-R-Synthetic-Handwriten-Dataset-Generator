#!/usr/bin/env python3
"""
Multilingual synthetic handwritten text dataset generator
Uses texts from /data/ and fonts from /fonts/ to create line and word images
Supports realistic paper backgrounds from /backgrounds/
Backgrounds organized by type (plain, grid, lined) and color (white, grey, beige)
Supports realistic perturbations to simulate scanned/photographed documents
"""

import os
import json
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random
from collections import defaultdict
import re
from tqdm import tqdm
import multiprocessing as mp
from functools import partial
import platform
import warnings
import logging
from fontTools.ttLib import TTFont

# Suppress fontTools timestamp warnings (uses logging, not warnings)
logging.getLogger('fontTools').setLevel(logging.ERROR)

# Import perturbation module
from apply_perturbations import PerturbationPipeline, QualityLevel


# ============================================================================
# FONT VERIFICATION FUNCTIONS
# ============================================================================

def _glyph_exists_in_font(font_path, char):
    """
    Verifies that a character has a REAL glyph in the font (not .notdef/rectangle placeholder).
    Checks directly in cmap and glyf without needing to render.
    """
    try:
        font = TTFont(font_path)
        cmap = font.getBestCmap()
        
        if cmap is None:
            return False
        
        codepoint = ord(char)
        
        # Check if codepoint exists in cmap
        if codepoint not in cmap:
            return False
        
        # Get glyph name associated with this codepoint
        glyph_name = cmap[codepoint]
        
        # If glyph is .notdef, it doesn't really exist
        if glyph_name == '.notdef':
            return False
        
        # Verify glyph has contours (not empty)
        if 'glyf' in font:
            # TrueType font
            glyf_table = font['glyf']
            if glyph_name in glyf_table:
                glyph = glyf_table[glyph_name]
                # An empty glyph has no contours (numberOfContours = 0 or -1 for empty composites)
                if hasattr(glyph, 'numberOfContours'):
                    if glyph.numberOfContours == 0:
                        return False
                    # Composite glyphs (numberOfContours = -1) can be valid
                    if glyph.numberOfContours == -1:
                        # Verify it has components
                        if not hasattr(glyph, 'components') or not glyph.components:
                            return False
        elif 'CFF ' in font:
            # OpenType/CFF font
            cff = font['CFF ']
            if hasattr(cff, 'cff') and len(cff.cff) > 0:
                top_dict = cff.cff[0]
                if hasattr(top_dict, 'CharStrings'):
                    if glyph_name not in top_dict.CharStrings:
                        return False
        
        return True
        
    except Exception:
        return False


# Cache for glyph verification
_glyph_exists_cache = {}

def _check_glyph_exists_cached(font_path, char):
    """Cached version of glyph verification."""
    cache_key = (str(font_path), char)
    if cache_key not in _glyph_exists_cache:
        _glyph_exists_cache[cache_key] = _glyph_exists_in_font(font_path, char)
    return _glyph_exists_cache[cache_key]


def _font_supports_text(font_path, text):
    """
    Verifies if a font supports all characters in a text.
    Checks that glyphs really exist (not .notdef/rectangles).
    Returns True if all supported, False if any missing.
    """
    try:
        for char in text:
            if char.isspace():
                continue
            
            # Verify glyph really exists (not .notdef)
            if not _check_glyph_exists_cached(font_path, char):
                return False
                    
        return True
    except Exception:
        return False


# Global cache to avoid reloading fonts
_font_support_cache = {}

def _check_font_supports_text_cached(font_path, text):
    """
    Cached version of character support verification.
    """
    # Create a unique key for the unique character set in text
    unique_chars = ''.join(sorted(set(c for c in text if not c.isspace())))
    cache_key = (font_path, unique_chars)
    
    if cache_key not in _font_support_cache:
        _font_support_cache[cache_key] = _font_supports_text(font_path, unique_chars)
    
    return _font_support_cache[cache_key]


# ============================================================================
# GLOBAL FUNCTIONS FOR MULTIPROCESSING
# ============================================================================

def _init_worker():
    """Initialize worker process - suppress fontTools warnings"""
    import logging
    logging.getLogger('fontTools').setLevel(logging.ERROR)


def _generate_single_image(task, target_height=128):
    """
    Worker function to generate an image (compatible with multiprocessing)
    """
    # Margins (pixels on each side)
    HORIZONTAL_MARGIN = 20
    VERTICAL_MARGIN = 10
    
    try:
        text = task['text']
        font_path = task['font_path']
        split_dir = Path(task['split_dir'])
        img_filename = task['img_filename']
        
        # Verify font supports all characters in text
        if not _check_font_supports_text_cached(font_path, text):
            return None  # Skip this combination
        
        # Generate image
        font_size = int(target_height * 0.7)
        font = ImageFont.truetype(str(font_path), font_size)

        # Measure text
        temp_img = Image.new('RGB', (1, 1), 'white')
        temp_draw = ImageDraw.Draw(temp_img)
        bbox = temp_draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Adjust font_size to reach target_height (leaving space for margins)
        available_height = target_height - 2 * VERTICAL_MARGIN
        if text_height > 0:
            scale_factor = (available_height * 0.9) / text_height
            font_size = int(font_size * scale_factor)
            font = ImageFont.truetype(str(font_path), font_size)
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

        # Create image: fixed height, variable width + margins
        img_width = max(text_width, 10) + 2 * HORIZONTAL_MARGIN
        img_height = target_height

        # Create image with background or white
        bg_info = task.get('background')
        if bg_info and bg_info.get('path'):
            try:
                bg_img = Image.open(bg_info['path']).convert('RGB')
                if bg_img.width < img_width or bg_img.height < img_height:
                    tiled = Image.new('RGB', (img_width, img_height))
                    for tx in range(0, img_width, bg_img.width):
                        for ty in range(0, img_height, bg_img.height):
                            tiled.paste(bg_img, (tx, ty))
                    img = tiled
                else:
                    max_x = bg_img.width - img_width
                    max_y = bg_img.height - img_height
                    crop_x = random.randint(0, max_x)
                    crop_y = random.randint(0, max_y)
                    img = bg_img.crop((crop_x, crop_y, crop_x + img_width, crop_y + img_height))
                bg_type = bg_info['type']
                bg_color = bg_info['color']
            except Exception:
                img = Image.new('RGB', (img_width, img_height), 'white')
                bg_type = 'plain'
                bg_color = 'white'
        else:
            img = Image.new('RGB', (img_width, img_height), 'white')
            bg_type = 'plain'
            bg_color = 'white'

        draw = ImageDraw.Draw(img)

        # Center text vertically
        y = (target_height - text_height) // 2 - bbox[1]

        # Ink color with slight variation
        ink_r = random.randint(0, 30)
        ink_g = random.randint(0, 30)
        ink_b = random.randint(0, 40)
        draw.text((HORIZONTAL_MARGIN, y), text, font=font, fill=(ink_r, ink_g, ink_b))

        # Apply perturbations if enabled
        perturb_metadata = {'quality': 'clean'}
        perturbation_config = task.get('perturbation_config')
        if perturbation_config and perturbation_config.get('enabled'):
            quality_dist = perturbation_config.get('quality_distribution', (40, 40, 20))
            pipeline = PerturbationPipeline(quality_distribution=quality_dist)
            img, perturb_params = pipeline.apply(img)
            perturb_metadata = perturb_params.to_dict()

        # Save image
        img_path = split_dir / img_filename
        img.save(img_path)

        # Create metadata
        metadata_entry = {
            'file_name': img_filename,
            'text': text,
            'text_length': len(text),
            'char_count': len(text),
            'word_count': len(text.split()),
            'language': task.get('language', 'unknown'),
            'font_name': task['font_info']['name'],
            'font_category': task['font_info']['category'],
            'font_style': task['font_info']['style'],
            'source_book': task['text_data']['book'],
            'background_type': bg_type,
            'background_color': bg_color,
            'mode': task['mode'],
            'split_name': task['split_name'],
            'quality': perturb_metadata.get('quality', 'clean'),
        }
        
        # Add perturbation parameters if any
        perturbation_params = {k: v for k, v in perturb_metadata.items() if k != 'quality' and v is not None}
        if perturbation_params:
            metadata_entry['perturbations'] = perturbation_params

        return metadata_entry

    except Exception as e:
        import sys
        print(f"\n[ERROR] Worker failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None


def _load_required_chars_for_languages(languages_str):
    """
    Loads required characters for all specified languages.
    Returns a set with all unique required characters.
    """
    required_chars = set()
    
    # Base characters (common to all languages)
    base_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
    base_chars.update('.,;:!?\'"-()[]{}')
    required_chars.update(base_chars)
    
    # Parse languages
    if ',' in languages_str:
        languages = [l.strip() for l in languages_str.split(',')]
    else:
        languages = [languages_str]
    
    # Load language-specific characters
    for lang in languages:
        lang_file = Path('languages') / f'{lang}.json'
        if lang_file.exists():
            try:
                with open(lang_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    lang_chars = config.get('required_chars', [])
                    required_chars.update(lang_chars)
            except Exception:
                pass
    
    return required_chars


def _font_supports_chars(font_path, required_chars):
    """
    Verifies if a font supports all required characters.
    """
    try:
        font = TTFont(font_path)
        cmap = font.getBestCmap()
        if cmap is None:
            return False
        
        for char in required_chars:
            if char.isspace():
                continue
            codepoint = ord(char)
            if codepoint not in cmap:
                return False
        return True
    except Exception:
        return False


class SyntheticDatasetBuilder:
    def __init__(self, data_dir='data', fonts_dir='fonts', output_dir='output',
                 mode='lines', mode_distribution=None, style='normal', verbose=False,
                 train_split=0.8, val_split=0.1, num_workers=1, max_fonts_per_category=None,
                 category_filter=None, backgrounds_dir=None,
                 background_color=None, background_type=None,
                 perturbations=False, quality_distribution=(40, 40, 20),
                 language='unknown'):
        # Store data_dir as string (may contain multiple directories comma-separated)
        self.data_dir = data_dir
        self.fonts_dir = Path(fonts_dir)
        self.output_dir = Path(output_dir)
        
        # Process modes (can be 'lines', 'words', or 'lines,words')
        self.modes = [m.strip() for m in mode.split(',')]
        if len(self.modes) == 1:
            self.mode_distribution = [100]
        elif mode_distribution:
            self.mode_distribution = [int(x) for x in mode_distribution.split(',')]
        else:
            # Default 50/50 if two modes
            self.mode_distribution = [50] * len(self.modes)
        
        # Normalize distribution to ensure sum is 100
        total = sum(self.mode_distribution)
        self.mode_distribution = [d / total for d in self.mode_distribution]
        
        # For compatibility with existing code
        self.mode = self.modes[0]
        
        self.style = style
        self.verbose = verbose
        self.num_workers = num_workers
        self.max_fonts_per_category = max_fonts_per_category
        self.category_filter = category_filter
        self.background_color = background_color
        self.background_type = background_type
        self.language = language
        
        # Parse languages
        if ',' in language:
            self.languages = [l.strip() for l in language.split(',')]
        else:
            self.languages = [language]
        
        # Load required characters FOR EACH language (not combined)
        self.required_chars_by_lang = {}
        for lang in self.languages:
            self.required_chars_by_lang[lang] = _load_required_chars_for_languages(lang)
        
        # Perturbation settings
        self.perturbations_enabled = perturbations
        self.quality_distribution = quality_distribution
        if self.perturbations_enabled:
            self.perturbation_pipeline = PerturbationPipeline(
                quality_distribution=quality_distribution
            )

        # Load backgrounds
        self.backgrounds_dir = Path(backgrounds_dir) if backgrounds_dir else None
        self.backgrounds = []
        if self.backgrounds_dir and self.backgrounds_dir.exists():
            self._load_backgrounds()

        # Split proportions
        self.train_split = train_split
        self.val_split = val_split
        self.test_split = 1.0 - train_split - val_split

        # Create HuggingFace structure
        self.train_dir = self.output_dir / 'train'
        self.val_dir = self.output_dir / 'validation'
        self.test_dir = self.output_dir / 'test'

        for split_dir in [self.train_dir, self.val_dir, self.test_dir]:
            split_dir.mkdir(parents=True, exist_ok=True)

        # Statistics
        self.stats = {
            'fonts_with_bold': 0,
            'fonts_without_bold': 0,
            'fonts_used': 0,
            'fonts_skipped': 0,
            'fonts_incompatible': 0,  # Fonts that don't support required characters
            'images_generated': 0,
            'images_skipped_unsupported': 0,  # Images skipped due to lack of character support
            'lines_generated': 0,
            'words_generated': 0,
            'train_samples': 0,
            'val_samples': 0,
            'test_samples': 0,
            'quality_clean': 0,
            'quality_degraded': 0,
            'quality_severe': 0,
        }

        self.fonts = []
        self.texts = []

    def _select_mode_for_item(self, num_fonts=1, num_words=1):
        """
        Selects mode for a text based on configured distribution.
        Controls distribution by NUMBER OF IMAGES, not number of texts.
        
        Simulates the impact of each selection and chooses the one
        that brings the distribution closer to the target.
        
        Args:
            num_fonts: Number of fonts that will be used (images per line)
            num_words: Number of words in the text (for words mode)
        """
        if len(self.modes) == 1:
            return self.modes[0]
        
        # Initialize counters if not exist
        if not hasattr(self, '_mode_image_counts'):
            self._mode_image_counts = {mode: 0 for mode in self.modes}
        
        total_images = sum(self._mode_image_counts.values())
        
        # Get target distribution
        target_dist = {mode: prob for mode, prob in zip(self.modes, self.mode_distribution)}
        
        # Calculate images each selection would add
        images_if_selected = {}
        for mode in self.modes:
            if mode == 'words':
                images_if_selected[mode] = num_words * num_fonts
            else:
                images_if_selected[mode] = num_fonts
        
        # Find mode that minimizes distribution error after selection
        best_mode = self.modes[0]
        best_error = float('inf')
        
        for candidate_mode in self.modes:
            # Simulate selecting this mode
            new_total = total_images + images_if_selected[candidate_mode]
            
            if new_total == 0:
                continue
            
            # Calculate what distribution would be after this selection
            total_error = 0
            for mode in self.modes:
                new_count = self._mode_image_counts.get(mode, 0)
                if mode == candidate_mode:
                    new_count += images_if_selected[candidate_mode]
                new_pct = new_count / new_total
                total_error += abs(new_pct - target_dist[mode])
            
            if total_error < best_error:
                best_error = total_error
                best_mode = candidate_mode
        
        # Update counter with selected mode's images
        self._mode_image_counts[best_mode] += images_if_selected[best_mode]
        
        return best_mode
    
    def _reset_mode_counters(self):
        """Reset mode image counters (call before each dataset generation)"""
        self._mode_image_counts = {mode: 0 for mode in self.modes}

    def _load_backgrounds(self):
        """Loads available background images filtering by color and type"""
        print("[0] Loading paper backgrounds...")

        # Parse filters
        color_filter = None
        type_filter = None
        if self.background_color:
            color_filter = [c.strip() for c in self.background_color.split(',')]
            print(f"  [FILTER] Colors: {', '.join(color_filter)}")
        if self.background_type:
            type_filter = [t.strip() for t in self.background_type.split(',')]
            print(f"  [FILTER] Types: {', '.join(type_filter)}")

        for bg_dir in self.backgrounds_dir.iterdir():
            if not bg_dir.is_dir():
                continue

            # Folder name is "type_color" (e.g. grid_white, lined_grey)
            parts = bg_dir.name.split('_', 1)
            if len(parts) != 2:
                continue

            bg_type, bg_color = parts[0], parts[1]

            # Apply filters
            if color_filter and bg_color not in color_filter:
                if self.verbose:
                    print(f"  [SKIP] {bg_dir.name} (color filtered)")
                continue
            if type_filter and bg_type not in type_filter:
                if self.verbose:
                    print(f"  [SKIP] {bg_dir.name} (type filtered)")
                continue

            for bg_file in bg_dir.glob('*.png'):
                self.backgrounds.append({
                    'path': str(bg_file),
                    'type': bg_type,
                    'color': bg_color
                })

        # Show summary
        bg_summary = defaultdict(int)
        for bg in self.backgrounds:
            bg_summary[f"{bg['type']}_{bg['color']}"] += 1

        print(f"  [OK] {len(self.backgrounds)} backgrounds loaded")
        for name in sorted(bg_summary.keys()):
            print(f"    {name}: {bg_summary[name]}")

    def scan_fonts(self):
        """Scans font directory and filters by compatibility with each language"""
        print("[1] Scanning fonts...")

        if self.category_filter:
            self.category_filter_list = [c.strip() for c in self.category_filter.split(',')]
            print(f"  [FILTER] Only using categories: {', '.join(self.category_filter_list)}")
        else:
            self.category_filter_list = None

        # First, collect all available fonts
        all_fonts = []

        for category_dir in self.fonts_dir.iterdir():
            if not category_dir.is_dir():
                continue

            if self.category_filter_list and category_dir.name not in self.category_filter_list:
                if self.verbose:
                    print(f"  [SKIP] Category {category_dir.name} (filtered)")
                continue

            for font_dir in category_dir.iterdir():
                if not font_dir.is_dir():
                    continue

                font_files = list(font_dir.glob('*.ttf')) + list(font_dir.glob('*.otf'))
                if not font_files:
                    continue

                normal_fonts = []
                bold_fonts = []

                for font_file in font_files:
                    font_name_lower = font_file.name.lower()
                    if any(keyword in font_name_lower for keyword in ['bold', 'bd', 'heavy', 'black']):
                        if 'italic' not in font_name_lower and 'oblique' not in font_name_lower:
                            bold_fonts.append(font_file)
                    elif not any(keyword in font_name_lower for keyword in ['italic', 'oblique', 'bold', 'bd', 'heavy', 'black']):
                        normal_fonts.append(font_file)

                has_bold = len(bold_fonts) > 0
                if has_bold:
                    self.stats['fonts_with_bold'] += 1
                else:
                    self.stats['fonts_without_bold'] += 1

                font_info = None
                if self.style == 'bold':
                    if has_bold:
                        font_info = {
                            'path': bold_fonts[0],
                            'name': font_dir.name,
                            'category': category_dir.name,
                            'style': 'bold'
                        }
                    else:
                        self.stats['fonts_skipped'] += 1
                        if self.verbose:
                            print(f"  [SKIP] {category_dir.name}/{font_dir.name} - No bold")
                elif self.style == 'normal':
                    if normal_fonts:
                        font_info = {
                            'path': normal_fonts[0],
                            'name': font_dir.name,
                            'category': category_dir.name,
                            'style': 'normal'
                        }
                    else:
                        self.stats['fonts_skipped'] += 1
                        if self.verbose:
                            print(f"  [SKIP] {category_dir.name}/{font_dir.name} - No normal")

                if font_info:
                    all_fonts.append(font_info)

        # Now filter fonts for each language
        self.fonts_by_lang = {}
        self.stats['fonts_by_lang'] = {}
        
        for lang in self.languages:
            required_chars = self.required_chars_by_lang[lang]
            compatible_fonts = []
            
            for font_info in all_fonts:
                if _font_supports_chars(font_info['path'], required_chars):
                    compatible_fonts.append(font_info.copy())
            
            # Apply category limit if needed
            if self.max_fonts_per_category is not None:
                fonts_by_cat = defaultdict(list)
                for f in compatible_fonts:
                    fonts_by_cat[f['category']].append(f)
                
                limited_fonts = []
                for cat_fonts in fonts_by_cat.values():
                    random.shuffle(cat_fonts)
                    limited_fonts.extend(cat_fonts[:self.max_fonts_per_category])
                compatible_fonts = limited_fonts
            
            self.fonts_by_lang[lang] = compatible_fonts
            self.stats['fonts_by_lang'][lang] = len(compatible_fonts)
        
        # self.fonts keeps all fonts for compatibility
        # (use union of all fonts compatible with some language)
        all_compatible = {}
        for lang_fonts in self.fonts_by_lang.values():
            for f in lang_fonts:
                all_compatible[f['name']] = f
        self.fonts = list(all_compatible.values())
        
        self.stats['fonts_used'] = len(self.fonts)
        self.stats['fonts_incompatible'] = len(all_fonts) - len(self.fonts)

        print(f"  [OK] Fonts scanned:")
        print(f"    With bold: {self.stats['fonts_with_bold']}")
        print(f"    Without bold: {self.stats['fonts_without_bold']}")
        print(f"    Total fonts found: {len(all_fonts)}")
        
        print(f"\n  [FILTER BY LANGUAGE]")
        for lang in self.languages:
            print(f"    {lang}: {self.stats['fonts_by_lang'][lang]} compatible fonts")
        
        if len(self.languages) > 1:
            min_fonts = min(self.stats['fonts_by_lang'].values())
            max_fonts = max(self.stats['fonts_by_lang'].values())
            print(f"    (range: {min_fonts} - {max_fonts} fonts)")

        if self.max_fonts_per_category is not None:
            print(f"\n  [INFO] Limit per category: {self.max_fonts_per_category}")

    def load_texts(self):
        """Loads all texts from data directory (or multiple directories)"""
        print("\n[2] Loading texts...")
        
        # Support multiple directories comma-separated
        if isinstance(self.data_dir, str) and ',' in self.data_dir:
            data_dirs = [Path(d.strip()) for d in self.data_dir.split(',')]
        else:
            data_dirs = [Path(self.data_dir)]
        
        # Support multiple languages comma-separated
        if isinstance(self.language, str) and ',' in self.language:
            languages = [l.strip() for l in self.language.split(',')]
        else:
            languages = [self.language] * len(data_dirs)
        
        # Ensure we have same number of languages as directories
        if len(languages) == 1 and len(data_dirs) > 1:
            languages = languages * len(data_dirs)
        elif len(languages) != len(data_dirs):
            print(f"  [WARNING] Number of languages ({len(languages)}) != directories ({len(data_dirs)})")
            languages = languages[:len(data_dirs)] if len(languages) > len(data_dirs) else languages + [languages[-1]] * (len(data_dirs) - len(languages))
        
        for data_dir, lang in zip(data_dirs, languages):
            if not data_dir.exists():
                print(f"  [WARNING] Directory does not exist: {data_dir}")
                continue
                
            txt_sources = []
            for txt_file in data_dir.glob('*.txt'):
                txt_sources.append((txt_file, data_dir.name))
            for book_dir in data_dir.iterdir():
                if not book_dir.is_dir():
                    continue
                for txt_file in book_dir.glob('*.txt'):
                    txt_sources.append((txt_file, book_dir.name))
            
            texts_loaded = 0
            for txt_file, book_name in txt_sources:
                try:
                    with open(txt_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content = content.replace('\n', ' ')
                    content = re.sub(r'\s+', ' ', content)
                    sentences = re.split(r'(?<=[.!?;:])\s+', content)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        words = sentence.split()
                        if 3 <= len(words) <= 15 and any(c.isalpha() for c in sentence):
                            self.texts.append({
                                'text': sentence,
                                'book': book_name,
                                'file': txt_file.name,
                                'language': lang
                            })
                            texts_loaded += 1
                        elif len(words) > 15:
                            subparts = re.split(r'(?<=[,;])\s+', sentence)
                            for part in subparts:
                                part = part.strip()
                                part_words = part.split()
                                if 3 <= len(part_words) <= 15 and any(c.isalpha() for c in part):
                                    self.texts.append({
                                        'text': part,
                                        'book': book_name,
                                        'file': txt_file.name,
                                        'language': lang
                                    })
                                    texts_loaded += 1
                except Exception as e:
                    if self.verbose:
                        print(f"  [ERROR] Error reading {txt_file}: {e}")
            
            print(f"  [OK] {lang}: {texts_loaded} sentences loaded from {data_dir}")
        
        print(f"  [OK] Total: {len(self.texts)} sentences loaded")

    def generate_image(self, text, font_info, target_height=128):
        """Generates an image with specified text and font"""
        # Margins (pixels on each side)
        HORIZONTAL_MARGIN = 20
        VERTICAL_MARGIN = 10
        
        try:
            font_path = font_info['path']
            
            # Verify font supports all characters in text
            if not _check_font_supports_text_cached(str(font_path), text):
                return None, 'plain', 'white'  # Font doesn't support text
            
            font_size = int(target_height * 0.7)
            font = ImageFont.truetype(str(font_path), font_size)

            # Measure text
            temp_img = Image.new('RGB', (1, 1), 'white')
            temp_draw = ImageDraw.Draw(temp_img)
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Adjust font_size to reach target_height (leaving space for margins)
            available_height = target_height - 2 * VERTICAL_MARGIN
            if text_height > 0:
                scale_factor = (available_height * 0.9) / text_height
                font_size = int(font_size * scale_factor)
                font = ImageFont.truetype(str(font_path), font_size)
                bbox = temp_draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

            # Create image: fixed height, variable width + margins
            img_width = max(text_width, 10) + 2 * HORIZONTAL_MARGIN
            img_height = target_height

            # Create image with background or white
            if self.backgrounds:
                bg_info = random.choice(self.backgrounds)
                try:
                    bg_img = Image.open(bg_info['path']).convert('RGB')
                    if bg_img.width < img_width or bg_img.height < img_height:
                        tiled = Image.new('RGB', (img_width, img_height))
                        for tx in range(0, img_width, bg_img.width):
                            for ty in range(0, img_height, bg_img.height):
                                tiled.paste(bg_img, (tx, ty))
                        img = tiled
                    else:
                        max_x = bg_img.width - img_width
                        max_y = bg_img.height - img_height
                        crop_x = random.randint(0, max_x)
                        crop_y = random.randint(0, max_y)
                        img = bg_img.crop((crop_x, crop_y, crop_x + img_width, crop_y + img_height))
                    bg_type = bg_info['type']
                    bg_color = bg_info['color']
                except Exception:
                    img = Image.new('RGB', (img_width, img_height), 'white')
                    bg_type = 'plain'
                    bg_color = 'white'
            else:
                img = Image.new('RGB', (img_width, img_height), 'white')
                bg_type = 'plain'
                bg_color = 'white'

            draw = ImageDraw.Draw(img)

            # Center text vertically
            y = (target_height - text_height) // 2 - bbox[1]

            # Ink color with slight variation
            ink_r = random.randint(0, 30)
            ink_g = random.randint(0, 30)
            ink_b = random.randint(0, 40)
            draw.text((HORIZONTAL_MARGIN, y), text, font=font, fill=(ink_r, ink_g, ink_b))

            return img, bg_type, bg_color

        except Exception as e:
            if self.verbose:
                print(f"  [ERROR] Error generating image: {e}")
            return None, 'plain', 'white'

    def generate_dataset(self, max_texts=None, total_images=None, balanced=False, target_height=128):
        """Generates synthetic dataset in HuggingFace format"""
        print(f"\n[3] Generating dataset ({self.mode})...")

        if not self.fonts:
            print("  [ERROR] No fonts available")
            return

        if not self.texts:
            print("  [ERROR] No texts available")
            return

        # Reset mode counters for correct distribution
        self._reset_mode_counters()
        
        num_fonts = len(self.fonts)
        
        # Count languages first (needed for correct calculation)
        texts_by_lang = {}
        for t in self.texts:
            lang = t.get('language', 'unknown')
            if lang not in texts_by_lang:
                texts_by_lang[lang] = []
            texts_by_lang[lang].append(t)
        num_languages = len(texts_by_lang)
        
        # Get minimum fonts across all languages (to ensure balance)
        if hasattr(self, 'fonts_by_lang') and self.fonts_by_lang:
            min_fonts_per_lang = min(len(f) for f in self.fonts_by_lang.values()) if self.fonts_by_lang else num_fonts
        else:
            min_fonts_per_lang = num_fonts
        
        # If total_images specified, calculate texts and fonts PER LANGUAGE
        # Each language may have different number of available fonts
        self.texts_per_lang_limit = {}  # Text limit per language
        self.fonts_per_lang_limit = {}  # Font limit per language
        
        if total_images:
            if balanced and num_languages > 1 and hasattr(self, 'fonts_by_lang') and self.fonts_by_lang:
                # DYNAMIC calculation per language
                images_per_lang = total_images // num_languages
                MIN_TEXTS_PER_LANG = 5  # Minimum texts for linguistic variety
                
                # Store limit for use during generation
                self.images_per_lang_limit = {lang: images_per_lang for lang in self.fonts_by_lang}
                
                print(f"  [INFO] Target: {total_images} images ({images_per_lang}/language)")
                print(f"  [DYNAMIC CALCULATION PER LANGUAGE]")
                
                total_expected = 0
                for lang in self.fonts_by_lang:
                    fonts_available = len(self.fonts_by_lang[lang])
                    
                    if fonts_available == 0:
                        self.texts_per_lang_limit[lang] = 0
                        self.fonts_per_lang_limit[lang] = 0
                        continue
                    
                    # Calculate fonts to use: limit if too many to ensure minimum texts
                    max_fonts_for_min_texts = images_per_lang // MIN_TEXTS_PER_LANG
                    if max_fonts_for_min_texts < 1:
                        max_fonts_for_min_texts = 1
                    
                    fonts_to_use = min(fonts_available, max_fonts_for_min_texts)
                    
                    # Calculate texts needed to reach target
                    texts_needed = images_per_lang // fonts_to_use
                    if texts_needed < MIN_TEXTS_PER_LANG:
                        texts_needed = MIN_TEXTS_PER_LANG
                    
                    # Limit fonts for this language
                    if fonts_to_use < fonts_available:
                        random.shuffle(self.fonts_by_lang[lang])
                        self.fonts_by_lang[lang] = self.fonts_by_lang[lang][:fonts_to_use]
                    
                    self.texts_per_lang_limit[lang] = texts_needed
                    self.fonts_per_lang_limit[lang] = fonts_to_use
                    
                    expected = texts_needed * fonts_to_use
                    total_expected += expected
                    print(f"    {lang}: {texts_needed} texts × {fonts_to_use} fonts = {expected} images")
                
                print(f"  [INFO] Total expected: {total_expected} images (target: {total_images})")
                
                # max_texts will be calculated in balanced sampling
                max_texts = None
            else:
                # Single language or not balanced
                max_texts = total_images // min_fonts_per_lang
                if max_texts < 1:
                    max_texts = 1
                print(f"  [INFO] total_images={total_images} → max_texts={max_texts} (with {min_fonts_per_lang} fonts)")
        
        # Balanced sampling by language
        if balanced and num_languages > 1:
            # Select texts per language according to calculated limits
            texts_to_use = []
            for lang, texts in texts_by_lang.items():
                random.shuffle(texts)
                
                # Use specific limit per language if exists, otherwise calculate
                if lang in self.texts_per_lang_limit:
                    texts_needed = self.texts_per_lang_limit[lang]
                elif max_texts:
                    texts_needed = max_texts // num_languages
                    if texts_needed < 1:
                        texts_needed = 1
                else:
                    texts_needed = len(texts)
                
                selected = min(texts_needed, len(texts))
                texts_to_use.extend(texts[:selected])
                
                fonts_for_lang = len(self.fonts_by_lang.get(lang, self.fonts))
                expected_imgs = selected * fonts_for_lang
                print(f"  [BALANCED] {lang}: {selected} texts × {fonts_for_lang} fonts = {expected_imgs} images")
            
            random.shuffle(texts_to_use)
            print(f"  [BALANCED] Total texts: {len(texts_to_use)}")
        else:
            # IMPORTANT: Shuffle BEFORE selecting to ensure language mixing
            random.shuffle(self.texts)
            texts_to_use = self.texts[:max_texts] if max_texts else self.texts

        # Show language distribution
        lang_counts = {}
        for t in texts_to_use:
            lang = t.get('language', 'unknown')
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        if len(lang_counts) > 1:
            print(f"  [INFO] Text distribution: {lang_counts}")

        # Calculate total expected images (considering fonts per language)
        total_expected_images = 0
        for lang, count in lang_counts.items():
            fonts_for_lang = len(self.fonts_by_lang.get(lang, self.fonts))
            total_expected_images += count * fonts_for_lang
        
        print(f"  [INFO] Total expected images: {total_expected_images}")
        if self.backgrounds:
            print(f"  [INFO] Backgrounds: {len(self.backgrounds)} available")
        else:
            print(f"  [INFO] Backgrounds: white (no backgrounds/)")
        print(f"  [INFO] Splits: train={self.train_split:.0%}, val={self.val_split:.0%}, test={self.test_split:.0%}")
        if self.perturbations_enabled:
            print(f"  [INFO] Perturbations: ON (distribution: {self.quality_distribution[0]}% clean, {self.quality_distribution[1]}% degraded, {self.quality_distribution[2]}% severe)")
        else:
            print(f"  [INFO] Perturbations: OFF")
        if self.num_workers > 1:
            print(f"  [INFO] Using {self.num_workers} workers in parallel")

        n_texts = len(texts_to_use)
        
        # If multiple languages, do split PER LANGUAGE to ensure balance
        if len(lang_counts) > 1:
            # Group texts by language
            texts_by_lang_to_split = {}
            for t in texts_to_use:
                lang = t.get('language', 'unknown')
                if lang not in texts_by_lang_to_split:
                    texts_by_lang_to_split[lang] = []
                texts_by_lang_to_split[lang].append(t)
            
            train_texts = []
            val_texts = []
            test_texts = []
            
            for lang, lang_texts in texts_by_lang_to_split.items():
                n = len(lang_texts)
                if n == 1:
                    # Only 1 text: all goes to train
                    train_texts.extend(lang_texts)
                elif n == 2:
                    # 2 texts: 1 train, 1 test
                    train_texts.append(lang_texts[0])
                    test_texts.append(lang_texts[1])
                else:
                    # 3+ texts: normal split
                    train_end_lang = max(1, int(n * self.train_split))
                    val_end_lang = train_end_lang + max(1, int(n * self.val_split))
                    if val_end_lang >= n:
                        val_end_lang = n - 1
                    
                    train_texts.extend(lang_texts[:train_end_lang])
                    val_texts.extend(lang_texts[train_end_lang:val_end_lang])
                    test_texts.extend(lang_texts[val_end_lang:])
            
            # Shuffle within each split
            random.shuffle(train_texts)
            random.shuffle(val_texts)
            random.shuffle(test_texts)
            
            # Show distribution per split
            for split_name, split_texts in [('train', train_texts), ('val', val_texts), ('test', test_texts)]:
                if split_texts:
                    split_langs = {}
                    for t in split_texts:
                        l = t.get('language', 'unknown')
                        split_langs[l] = split_langs.get(l, 0) + 1
                    print(f"  [SPLIT] {split_name}: {split_langs}")
        else:
            # Single language: normal split
            train_end = int(n_texts * self.train_split)
            val_end = train_end + int(n_texts * self.val_split)

            train_texts = texts_to_use[:train_end]
            val_texts = texts_to_use[train_end:val_end]
            test_texts = texts_to_use[val_end:]

        train_metadata = []
        val_metadata = []
        test_metadata = []

        # Calculate total_items considering fonts per language and mixed modes
        total_items = 0
        
        # Determine probability of 'words' mode
        words_prob = 0
        for mode, prob in zip(self.modes, self.mode_distribution):
            if mode == 'words':
                words_prob = prob
                break
        
        for td in texts_to_use:
            text_lang = td.get('language', self.languages[0] if self.languages else 'unknown')
            num_fonts = len(self.fonts_by_lang.get(text_lang, self.fonts))
            
            if len(self.modes) == 1:
                # Single mode
                if self.modes[0] == 'words':
                    total_items += len(td['text'].split()) * num_fonts
                else:
                    total_items += num_fonts
            else:
                # Mixed modes: estimate based on distribution
                num_words = len(td['text'].split())
                lines_contrib = (1 - words_prob) * num_fonts
                words_contrib = words_prob * num_words * num_fonts
                total_items += int(lines_contrib + words_contrib)

        print(f"  Total expected images: {total_items:,} (estimated)")

        if self.num_workers > 1:
            self._generate_dataset_parallel(
                train_texts, val_texts, test_texts,
                train_metadata, val_metadata, test_metadata,
                target_height, total_items
            )
        else:
            self._generate_dataset_sequential(
                train_texts, val_texts, test_texts,
                train_metadata, val_metadata, test_metadata,
                target_height, total_items
            )

        self._save_metadata_jsonl(self.train_dir / 'metadata.jsonl', train_metadata)
        self._save_metadata_jsonl(self.val_dir / 'metadata.jsonl', val_metadata)
        self._save_metadata_jsonl(self.test_dir / 'metadata.jsonl', test_metadata)
        self._create_dataset_info()

        print(f"  [OK] {self.stats['images_generated']:,} images generated")
        print(f"    Train: {self.stats['train_samples']:,}")
        print(f"    Validation: {self.stats['val_samples']:,}")
        print(f"    Test: {self.stats['test_samples']:,}")
        
        if self.perturbations_enabled:
            print(f"\n  Quality distribution:")
            print(f"    Clean: {self.stats['quality_clean']:,}")
            print(f"    Degraded: {self.stats['quality_degraded']:,}")
            print(f"    Severe: {self.stats['quality_severe']:,}")

    def _generate_dataset_parallel(self, train_texts, val_texts, test_texts,
                                    train_metadata, val_metadata, test_metadata,
                                    target_height, total_items):
        """Generate dataset using multiprocessing"""
        tasks = []
        counters = {'train': 0, 'validation': 0, 'test': 0}
        
        # Image counters per language for balanced generation
        lang_image_counts = {lang: 0 for lang in self.languages} if hasattr(self, 'languages') else {}
        
        # Perturbation config to pass to workers
        perturbation_config = {
            'enabled': self.perturbations_enabled,
            'quality_distribution': self.quality_distribution
        } if self.perturbations_enabled else None

        for split_name, split_texts, split_dir in [
            ('train', train_texts, self.train_dir),
            ('validation', val_texts, self.val_dir),
            ('test', test_texts, self.test_dir)
        ]:
            for text_data in split_texts:
                text = text_data['text']
                text_lang = text_data.get('language', self.languages[0] if self.languages else 'unknown')
                
                # Check if this language has reached its image limit
                if hasattr(self, 'images_per_lang_limit') and text_lang in self.images_per_lang_limit:
                    if lang_image_counts.get(text_lang, 0) >= self.images_per_lang_limit[text_lang]:
                        continue  # Skip this text, language quota reached
                
                # Get compatible fonts for this language
                if text_lang in self.fonts_by_lang:
                    compatible_fonts = self.fonts_by_lang[text_lang]
                else:
                    compatible_fonts = self.fonts  # Fallback
                
                if not compatible_fonts:
                    continue
                
                # Select mode for this text (based on image count distribution)
                num_words = len(text.split())
                current_mode = self._select_mode_for_item(
                    num_fonts=len(compatible_fonts),
                    num_words=num_words
                )
                
                if current_mode == 'words':
                    words = text.split()
                    if not words:
                        continue
                    words_to_render = words
                else:
                    words_to_render = [text]

                # Calculate images this text will generate
                images_for_this_text = len(words_to_render) * len(compatible_fonts)
                
                # Check if adding this text would exceed limit
                if hasattr(self, 'images_per_lang_limit') and text_lang in self.images_per_lang_limit:
                    current_count = lang_image_counts.get(text_lang, 0)
                    limit = self.images_per_lang_limit[text_lang]
                    if current_count + images_for_this_text > limit * 1.1:  # 10% tolerance
                        continue  # Skip this text
                
                # Update language image counter
                lang_image_counts[text_lang] = lang_image_counts.get(text_lang, 0) + images_for_this_text

                for text_to_render in words_to_render:
                    for font_info in compatible_fonts:
                        img_filename = f"{counters[split_name]:08d}.png"
                        counters[split_name] += 1

                        bg_data = None
                        if self.backgrounds:
                            bg_data = random.choice(self.backgrounds)

                        task = {
                            'text': text_to_render,
                            'font_path': str(font_info['path']),
                            'split_dir': str(split_dir),
                            'img_filename': img_filename,
                            'text_data': {
                                'book': text_data['book'],
                                'file': text_data.get('file', '')
                            },
                            'font_info': {
                                'name': font_info['name'],
                                'category': font_info['category'],
                                'style': font_info['style']
                            },
                            'background': bg_data,
                            'mode': current_mode,
                            'split_name': split_name,
                            'perturbation_config': perturbation_config,
                            'language': text_data.get('language', self.language)
                        }
                        tasks.append(task)

        optimal_chunksize = max(1, len(tasks) // (self.num_workers * 4))

        if self.verbose:
            print(f"  [INFO] Total tasks: {len(tasks):,}")
            print(f"  [INFO] Chunksize: {optimal_chunksize}")

        if platform.system() == 'Windows':
            ctx = mp.get_context('spawn')
        else:
            ctx = mp.get_context('fork')

        worker_fn = partial(_generate_single_image, target_height=target_height)

        with ctx.Pool(processes=self.num_workers, initializer=_init_worker) as pool:
            results = []
            print(f"\n  Processing {len(tasks):,} tasks...")
            print(f"  Starting workers...", flush=True)
            processed = 0
            report_interval = max(500, len(tasks) // 200)

            print(f"  Workers started, waiting for results...", flush=True)
            for result in pool.imap_unordered(worker_fn, tasks, chunksize=optimal_chunksize):
                if result is not None:
                    results.append(result)
                    # Count quality
                    quality = result.get('quality', 'clean')
                    if quality == 'clean':
                        self.stats['quality_clean'] += 1
                    elif quality == 'degraded':
                        self.stats['quality_degraded'] += 1
                    elif quality == 'severe':
                        self.stats['quality_severe'] += 1
                processed += 1
                if processed % report_interval == 0 or processed == len(tasks):
                    percent = (processed / len(tasks)) * 100
                    print(f"  Progress: {processed:,}/{len(tasks):,} ({percent:.1f}%)", flush=True)

        for result in results:
            split_name = result.pop('split_name', 'train')
            if split_name == 'train':
                train_metadata.append(result)
            elif split_name == 'validation':
                val_metadata.append(result)
            else:
                test_metadata.append(result)

        self.stats['images_generated'] = len(results)
        self.stats['images_skipped_unsupported'] = len(tasks) - len(results)
        self.stats['train_samples'] = len(train_metadata)
        self.stats['val_samples'] = len(val_metadata)
        self.stats['test_samples'] = len(test_metadata)

        if self.mode == 'words':
            self.stats['words_generated'] = self.stats['images_generated']
        else:
            self.stats['lines_generated'] = self.stats['images_generated']

    def _generate_dataset_sequential(self, train_texts, val_texts, test_texts,
                                      train_metadata, val_metadata, test_metadata,
                                      target_height, total_items):
        """Generate dataset sequentially"""
        # Suppress fontTools timestamp warnings
        import logging
        logging.getLogger('fontTools').setLevel(logging.ERROR)
        
        global_train_count = 0
        global_val_count = 0
        global_test_count = 0
        
        # Image counters per language for balanced generation
        lang_image_counts = {lang: 0 for lang in self.languages} if hasattr(self, 'languages') else {}

        with tqdm(total=total_items, desc="Generating images", unit="img") as pbar:
            for split_name, split_texts, split_dir, split_metadata in [
                ('train', train_texts, self.train_dir, train_metadata),
                ('validation', val_texts, self.val_dir, val_metadata),
                ('test', test_texts, self.test_dir, test_metadata)
            ]:
                for text_data in split_texts:
                    text = text_data['text']
                    text_lang = text_data.get('language', self.languages[0] if self.languages else 'unknown')
                    
                    # Check if this language has reached its image limit
                    if hasattr(self, 'images_per_lang_limit') and text_lang in self.images_per_lang_limit:
                        if lang_image_counts.get(text_lang, 0) >= self.images_per_lang_limit[text_lang]:
                            continue  # Skip this text, language quota reached
                    
                    # Get compatible fonts for this language
                    if text_lang in self.fonts_by_lang:
                        compatible_fonts = self.fonts_by_lang[text_lang]
                    else:
                        compatible_fonts = self.fonts  # Fallback
                    
                    if not compatible_fonts:
                        continue
                    
                    # Select mode for this text (based on image count distribution)
                    num_words = len(text.split())
                    current_mode = self._select_mode_for_item(
                        num_fonts=len(compatible_fonts),
                        num_words=num_words
                    )
                    
                    if current_mode == 'words':
                        words = text.split()
                        if not words:
                            continue
                        words_to_render = words
                    else:
                        words_to_render = [text]

                    # Calculate images this text will generate
                    images_for_this_text = len(words_to_render) * len(compatible_fonts)
                    
                    # Check if adding this text would exceed limit
                    if hasattr(self, 'images_per_lang_limit') and text_lang in self.images_per_lang_limit:
                        current_count = lang_image_counts.get(text_lang, 0)
                        limit = self.images_per_lang_limit[text_lang]
                        if current_count + images_for_this_text > limit * 1.1:  # 10% tolerance
                            continue  # Skip this text
                    
                    # Update language image counter
                    lang_image_counts[text_lang] = lang_image_counts.get(text_lang, 0) + images_for_this_text

                    for text_to_render in words_to_render:
                        for font_info in compatible_fonts:
                            img_result = self.generate_image(text_to_render, font_info, target_height)

                            if img_result[0] is None:
                                self.stats['images_skipped_unsupported'] += 1
                                pbar.update(1)
                                continue

                            img, bg_type, bg_color = img_result

                            # Apply perturbations if enabled
                            perturb_metadata = {'quality': 'clean'}
                            if self.perturbations_enabled:
                                img, perturb_params = self.perturbation_pipeline.apply(img)
                                perturb_metadata = perturb_params.to_dict()
                                
                                # Count quality
                                quality = perturb_metadata.get('quality', 'clean')
                                if quality == 'clean':
                                    self.stats['quality_clean'] += 1
                                elif quality == 'degraded':
                                    self.stats['quality_degraded'] += 1
                                elif quality == 'severe':
                                    self.stats['quality_severe'] += 1

                            if split_name == 'train':
                                img_filename = f"{global_train_count:08d}.png"
                                global_train_count += 1
                                self.stats['train_samples'] += 1
                            elif split_name == 'validation':
                                img_filename = f"{global_val_count:08d}.png"
                                global_val_count += 1
                                self.stats['val_samples'] += 1
                            else:
                                img_filename = f"{global_test_count:08d}.png"
                                global_test_count += 1
                                self.stats['test_samples'] += 1

                            img_path = split_dir / img_filename
                            img.save(img_path)

                            metadata_entry = {
                                'file_name': img_filename,
                                'text': text_to_render,
                                'text_length': len(text_to_render),
                                'char_count': len(text_to_render),
                                'word_count': len(text_to_render.split()),
                                'language': text_data.get('language', self.language),
                                'font_name': font_info['name'],
                                'font_category': font_info['category'],
                                'font_style': font_info['style'],
                                'source_book': text_data['book'],
                                'background_type': bg_type,
                                'background_color': bg_color,
                                'mode': current_mode,
                                'quality': perturb_metadata.get('quality', 'clean'),
                            }
                            
                            # Add perturbation parameters if any
                            perturbation_params = {k: v for k, v in perturb_metadata.items() if k != 'quality' and v is not None}
                            if perturbation_params:
                                metadata_entry['perturbations'] = perturbation_params

                            split_metadata.append(metadata_entry)
                            self.stats['images_generated'] += 1

                            if self.mode == 'words':
                                self.stats['words_generated'] += 1
                            else:
                                self.stats['lines_generated'] += 1

                            pbar.update(1)

        self._save_metadata_jsonl(self.train_dir / 'metadata.jsonl', train_metadata)
        self._save_metadata_jsonl(self.val_dir / 'metadata.jsonl', val_metadata)
        self._save_metadata_jsonl(self.test_dir / 'metadata.jsonl', test_metadata)
        self._create_dataset_info()

        print(f"  [OK] {self.stats['images_generated']:,} images generated")
        print(f"    Train: {self.stats['train_samples']:,}")
        print(f"    Validation: {self.stats['val_samples']:,}")
        print(f"    Test: {self.stats['test_samples']:,}")

    def _save_metadata_jsonl(self, filepath, metadata_list):
        """Saves metadata in JSON Lines format"""
        with open(filepath, 'w', encoding='utf-8') as f:
            for entry in metadata_list:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def _create_dataset_info(self):
        """Creates the dataset_info.json file"""
        bg_types = list(set(bg['type'] for bg in self.backgrounds)) if self.backgrounds else ['plain']
        bg_colors = list(set(bg['color'] for bg in self.backgrounds)) if self.backgrounds else ['white']

        dataset_info = {
            'description': 'Synthetic multilingual handwriting dataset',
            'version': '2.1.0',
            'splits': {
                'train': {'name': 'train', 'num_samples': self.stats['train_samples']},
                'validation': {'name': 'validation', 'num_samples': self.stats['val_samples']},
                'test': {'name': 'test', 'num_samples': self.stats['test_samples']}
            },
            'features': {
                'file_name': {'dtype': 'string'},
                'text': {'dtype': 'string'},
                'char_count': {'dtype': 'int32'},
                'word_count': {'dtype': 'int32'},
                'font_name': {'dtype': 'string'},
                'font_category': {'dtype': 'string'},
                'font_style': {'dtype': 'string'},
                'source_book': {'dtype': 'string'},
                'background_type': {'dtype': 'string'},
                'background_color': {'dtype': 'string'},
                'mode': {'dtype': 'string'},
                'quality': {'dtype': 'string'},
            },
            'mode': self.mode,
            'style': self.style,
            'total_samples': self.stats['images_generated'],
            'num_fonts': len(self.fonts),
            'num_backgrounds': len(self.backgrounds),
            'background_types': bg_types,
            'background_colors': bg_colors,
            'perturbations_enabled': self.perturbations_enabled,
        }
        
        if self.perturbations_enabled:
            dataset_info['quality_distribution'] = {
                'clean': self.stats['quality_clean'],
                'degraded': self.stats['quality_degraded'],
                'severe': self.stats['quality_severe']
            }
            dataset_info['features']['perturbations'] = {'dtype': 'dict'}

        dataset_info_path = self.output_dir / 'dataset_info.json'
        with open(dataset_info_path, 'w', encoding='utf-8') as f:
            json.dump(dataset_info, f, ensure_ascii=False, indent=2)

        if self.verbose:
            print(f"  [SAVED] {dataset_info_path}")

    def generate_summary(self):
        """Generates dataset summary"""
        print()
        print("=" * 60)
        print("GENERATION SUMMARY - HUGGINGFACE FORMAT")
        print("=" * 60)
        if len(self.modes) > 1:
            mode_dist_str = ', '.join([f"{m}:{int(d*100)}%" for m, d in zip(self.modes, self.mode_distribution)])
            print(f"Mode: {', '.join(self.modes)} (distribution: {mode_dist_str})")
        else:
            print(f"Mode: {self.modes[0]}")
        print(f"Style: {self.style}")
        print(f"\nFonts:")
        print(f"  With bold: {self.stats['fonts_with_bold']}")
        print(f"  Without bold: {self.stats['fonts_without_bold']}")
        print(f"  Compatible used: {self.stats['fonts_used']}")
        if self.stats['fonts_incompatible'] > 0:
            print(f"  Incompatible (characters): {self.stats['fonts_incompatible']}")
        other_skipped = self.stats['fonts_skipped'] - self.stats['fonts_incompatible']
        if other_skipped > 0:
            print(f"  Skipped (other): {other_skipped}")
        print(f"\nPaper backgrounds:")
        if self.backgrounds:
            bg_summary = defaultdict(int)
            for bg in self.backgrounds:
                bg_summary[f"{bg['type']}_{bg['color']}"] += 1
            for name in sorted(bg_summary.keys()):
                print(f"  {name}: {bg_summary[name]}")
        else:
            print(f"  White (no backgrounds)")
        print(f"\nPerturbations:")
        if self.perturbations_enabled:
            print(f"  Status: ENABLED")
            print(f"  Configured distribution: {self.quality_distribution[0]}% clean, {self.quality_distribution[1]}% degraded, {self.quality_distribution[2]}% severe")
            print(f"  Results:")
            print(f"    Clean: {self.stats['quality_clean']:,}")
            print(f"    Degraded: {self.stats['quality_degraded']:,}")
            print(f"    Severe: {self.stats['quality_severe']:,}")
        else:
            print(f"  Status: DISABLED")
        print(f"\nImages generated:")
        print(f"  Total: {self.stats['images_generated']:,}")
        if self.stats['images_skipped_unsupported'] > 0:
            print(f"  Skipped (font unsupported chars): {self.stats['images_skipped_unsupported']:,}")
        if self.mode == 'words':
            print(f"  Words: {self.stats['words_generated']:,}")
        else:
            print(f"  Lines: {self.stats['lines_generated']:,}")
        print(f"\nSplits:")
        print(f"  Train: {self.stats['train_samples']:,} ({self.train_split:.0%})")
        print(f"  Validation: {self.stats['val_samples']:,} ({self.val_split:.0%})")
        print(f"  Test: {self.stats['test_samples']:,} ({self.test_split:.0%})")
        print(f"\nDataset structure:")
        print(f"  {self.output_dir.absolute()}/")
        print(f"    ├── train/")
        print(f"    │   ├── metadata.jsonl")
        print(f"    │   └── [images .png]")
        print(f"    ├── validation/")
        print(f"    │   ├── metadata.jsonl")
        print(f"    │   └── [images .png]")
        print(f"    ├── test/")
        print(f"    │   ├── metadata.jsonl")
        print(f"    │   └── [images .png]")
        print(f"    └── dataset_info.json")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Multilingual synthetic handwritten text dataset generator in HuggingFace format'
    )
    parser.add_argument('--data-dir', default='data', help='Directory with texts (default: data)')
    parser.add_argument('--fonts-dir', default='fonts', help='Directory with fonts (default: fonts)')
    parser.add_argument('--output-dir', default='output', help='Base output directory (default: output)')
    parser.add_argument('--output-name', default=None, help='Custom name for output folder')
    parser.add_argument('--language', default='unknown', help='Dataset language (default: unknown)')
    parser.add_argument('--mode', type=str, default='lines',
                        help='Mode(s): lines, words, or lines,words for both (default: lines)')
    parser.add_argument('--mode-distribution', type=str, default=None,
                        help='Mode distribution in %% (e.g.: 70,30). Default 50,50 if two modes passed')
    parser.add_argument('--style', choices=['normal', 'bold'], default='normal',
                        help='Font style: normal or bold (default: normal)')
    parser.add_argument('--train-split', type=float, default=0.8,
                        help='Training data ratio (default: 0.8)')
    parser.add_argument('--val-split', type=float, default=0.1,
                        help='Validation data ratio (default: 0.1)')
    parser.add_argument('--max-texts', type=int, default=None,
                        help='Maximum number of texts to use (default: all)')
    parser.add_argument('--total-images', type=int, default=None,
                        help='Total number of images to generate (calculates texts automatically)')
    parser.add_argument('--balanced', action='store_true',
                        help='Balance number of images per language')
    parser.add_argument('--font-size', type=int, default=128,
                        help='Image height in pixels (default: 128, compatible with IAM/TrOCR)')
    parser.add_argument('--workers', '-j', type=int, default=1,
                        help='Number of parallel workers (default: 1). Use -1 for all cores')
    parser.add_argument('--max-fonts-per-category', type=int, default=None,
                        help='Maximum number of fonts per category (default: all)')
    parser.add_argument('--category-filter', type=str, default=None,
                        help='Filter by font categories, comma-separated (e.g.: Handwritten,School)')
    parser.add_argument('--backgrounds-dir', default='backgrounds',
                        help='Directory with paper backgrounds (default: backgrounds). Use "none" to disable')
    parser.add_argument('--background-color', type=str, default=None,
                        help='Filter by background color, comma-separated (e.g.: white,grey,beige). Uses all by default')
    parser.add_argument('--background-type', type=str, default=None,
                        help='Filter by background type, comma-separated (e.g.: plain,grid,lined). Uses all by default')
    
    # Perturbation arguments
    parser.add_argument('--perturbations', action='store_true',
                        help='Apply realistic perturbations to images (blur, rotation, noise, etc.)')
    parser.add_argument('--quality-distribution', type=str, default='40,40,20',
                        help='Quality distribution: clean,degraded,severe in percentages (default: 40,40,20)')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed information')

    args = parser.parse_args()

    num_workers = args.workers
    if num_workers == -1:
        num_workers = mp.cpu_count()
    elif num_workers < 1:
        num_workers = 1

    if args.output_name:
        output_dir = f"{args.output_dir}_{args.output_name}"
    else:
        output_dir = args.output_dir

    backgrounds_dir = args.backgrounds_dir if args.backgrounds_dir != 'none' else None
    
    # Parse quality distribution
    quality_dist = tuple(map(int, args.quality_distribution.split(',')))
    if len(quality_dist) != 3 or sum(quality_dist) != 100:
        print(f"[ERROR] --quality-distribution must have 3 values that sum to 100 (e.g.: 40,40,20)")
        return

    print("=" * 60)
    print("SYNTHETIC DATASET GENERATOR - HUGGINGFACE FORMAT")
    print("=" * 60)
    if args.output_name:
        print(f"Dataset name: {args.output_name}")
        print(f"Output: {output_dir}")
    if args.category_filter:
        print(f"Font category: {args.category_filter}")
    if backgrounds_dir:
        print(f"Backgrounds: {backgrounds_dir}")
        if args.background_color:
            print(f"  Color: {args.background_color}")
        if args.background_type:
            print(f"  Type: {args.background_type}")
    if args.perturbations:
        print(f"Perturbations: ON ({quality_dist[0]}% clean, {quality_dist[1]}% degraded, {quality_dist[2]}% severe)")
    print()

    builder = SyntheticDatasetBuilder(
        data_dir=args.data_dir,
        fonts_dir=args.fonts_dir,
        output_dir=output_dir,
        mode=args.mode,
        mode_distribution=args.mode_distribution,
        style=args.style,
        train_split=args.train_split,
        val_split=args.val_split,
        num_workers=num_workers,
        max_fonts_per_category=args.max_fonts_per_category,
        category_filter=args.category_filter,
        backgrounds_dir=backgrounds_dir,
        background_color=args.background_color,
        background_type=args.background_type,
        perturbations=args.perturbations,
        quality_distribution=quality_dist,
        language=args.language,
        verbose=args.verbose
    )

    builder.scan_fonts()
    builder.load_texts()

    builder.generate_dataset(
        max_texts=args.max_texts,
        total_images=args.total_images,
        balanced=args.balanced or len(builder.languages) > 1,
        target_height=args.font_size
    )

    builder.generate_summary()
    print("[SUCCESS] Dataset generated successfully!")


if __name__ == "__main__":
    if platform.system() == 'Windows':
        mp.freeze_support()
    main()
