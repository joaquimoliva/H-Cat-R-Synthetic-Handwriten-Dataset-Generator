#!/usr/bin/env python3
"""
Verify existing fonts for required character, number, and punctuation support.
Remove fonts that don't support all required characters.
Includes watermark detection in special characters (spaces, apostrophes).
"""

import os
import shutil
from pathlib import Path
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm
import argparse

class FontVerifier:
    def __init__(self, fonts_dir='fonts', language='catalan', verbose=False, dry_run=False):
        self.fonts_dir = Path(fonts_dir)
        self.verbose = verbose
        self.dry_run = dry_run

        # Load language config
        self.language = language
        self.lang_config = self._load_language_config(language)

        # Base required characters (common to all languages)
        self.required_chars = {
            # Digits
            0x0030: ('digit 0', '0'),
            0x0031: ('digit 1', '1'),
            0x0032: ('digit 2', '2'),
            0x0033: ('digit 3', '3'),
            0x0034: ('digit 4', '4'),
            0x0035: ('digit 5', '5'),
            0x0036: ('digit 6', '6'),
            0x0037: ('digit 7', '7'),
            0x0038: ('digit 8', '8'),
            0x0039: ('digit 9', '9'),
            
            # Basic punctuation
            0x002E: ('period', '.'),
            0x002C: ('comma', ','),
            0x003A: ('colon', ':'),
            0x003B: ('semicolon', ';'),
            0x0021: ('exclamation mark', '!'),
            0x003F: ('question mark', '?'),
            
            # Quotes and apostrophes
            0x0027: ('apostrophe', "'"),
            0x0022: ('quotation mark', '"'),
            
            # Brackets and parentheses
            0x0028: ('left parenthesis', '('),
            0x0029: ('right parenthesis', ')'),
            0x005B: ('left bracket', '['),
            0x005D: ('right bracket', ']'),
            
            # Hyphens and dashes
            0x002D: ('hyphen-minus', '-'),
            
            # Common symbols
            0x0025: ('percent', '%'),
            0x0026: ('ampersand', '&'),
            0x0040: ('at sign', '@'),
            0x002F: ('slash', '/'),
            
            # Mathematical
            0x002B: ('plus', '+'),
            0x003D: ('equals', '='),
            
            # Currency (common)
            0x20AC: ('euro', '€'),
            0x0024: ('dollar', '$'),
        }

        # Add language-specific characters
        for char in self.lang_config.get('required_chars', []):
            codepoint = ord(char)
            self.required_chars[codepoint] = (f'lang-specific: {char}', char)

        self.stats = {
            'total_fonts': 0,
            'valid_fonts': 0,
            'invalid_fonts': 0,
            'removed_fonts': 0,
            'errors': 0
        }

        self.invalid_fonts = []  # Store info about invalid fonts

    def _load_language_config(self, language):
        """Carrega la configuració de l'idioma des de languages/"""
        import json
        config_path = Path(__file__).parent / 'languages' / f'{language}.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print(f"[WARNING] No language config found: {config_path}")
            return {'required_chars': []}

    def detect_watermark_in_special_chars(self, font_path, font_size=64):
        """
        Detect watermarks embedded in special characters (spaces, apostrophes, etc.)
        
        Many DaFont fonts embed "PERSONAL USE ONLY" or similar watermarks in:
        - Space character (U+0020)
        - Apostrophe (U+0027)
        - Quotation marks (U+0022, U+2018, U+2019)
        - Other punctuation
        
        Detection strategy:
        1. Render a phrase WITH special chars and measure total width
        2. Render the same phrase WITHOUT special chars
        3. Calculate expected space width based on letter widths
        4. If actual space width >> expected, likely contains watermark
        
        Returns: (is_clean, reason)
        """
        try:
            pil_font = ImageFont.truetype(str(font_path), font_size)
            
            # Test phrases - one with spaces/apostrophes, one without
            test_with_spaces = "a b c d e"      # 4 spaces
            test_without_spaces = "abcde"        # same letters, no spaces
            test_with_apostrophe = "it's here"   # has apostrophe
            test_without_apostrophe = "itshere"  # no apostrophe
            
            # Create temporary image for measurements
            temp_img = Image.new('RGB', (2000, 100), 'white')
            draw = ImageDraw.Draw(temp_img)
            
            # Measure widths
            def get_text_width(text):
                bbox = draw.textbbox((0, 0), text, font=pil_font)
                return bbox[2] - bbox[0]
            
            # Get reference letter width (average of a few common letters)
            ref_letters = "abcdefghij"
            ref_width = get_text_width(ref_letters) / len(ref_letters)
            
            # Expected space width: typically 20-50% of average letter width
            expected_space_width = ref_width * 0.5
            max_reasonable_space_width = ref_width * 1.5  # generous upper bound
            
            # Calculate actual space width
            width_with_spaces = get_text_width(test_with_spaces)
            width_without_spaces = get_text_width(test_without_spaces)
            num_spaces = test_with_spaces.count(' ')
            actual_space_width = (width_with_spaces - width_without_spaces) / num_spaces if num_spaces > 0 else 0
            
            # Check if space is suspiciously wide (contains watermark)
            if actual_space_width > max_reasonable_space_width * 3:
                return False, f"Space char contains watermark (width: {actual_space_width:.0f}px vs expected ~{expected_space_width:.0f}px)"
            
            # Check apostrophe similarly
            width_with_apos = get_text_width(test_with_apostrophe)
            width_without_apos = get_text_width(test_without_apostrophe)
            actual_apos_width = width_with_apos - width_without_apos + ref_width  # account for missing letter
            
            if actual_apos_width > max_reasonable_space_width * 4:
                return False, f"Apostrophe contains watermark (width: {actual_apos_width:.0f}px vs expected ~{expected_space_width:.0f}px)"
            
            # Visual check: render phrase with spaces and look for repeated patterns
            # This catches watermarks that might appear as visual noise
            test_phrase = "a a a a a"  # Multiple spaces
            phrase_img = Image.new('L', (2000, 100), 255)
            phrase_draw = ImageDraw.Draw(phrase_img)
            phrase_draw.text((10, 10), test_phrase, font=pil_font, fill=0)
            
            # Crop to content
            bbox = phrase_img.getbbox()
            if bbox:
                cropped = phrase_img.crop(bbox)
                
                # Count dark pixels (text content)
                pixels = list(cropped.getdata())
                dark_pixels = sum(1 for p in pixels if p < 200)
                total_pixels = len(pixels)
                
                # Expected: mostly white with some dark letters
                # Watermark fonts: much higher dark pixel ratio due to embedded text
                dark_ratio = dark_pixels / total_pixels if total_pixels > 0 else 0
                
                # Normal handwriting font: ~5-15% dark pixels for "a a a a a"
                # Watermark font: >25% due to extra embedded text
                if dark_ratio > 0.25:
                    return False, f"Excessive ink in spaces suggests watermark (dark pixel ratio: {dark_ratio:.1%})"
            
            return True, "No watermark detected in special characters"
            
        except Exception as e:
            if self.verbose:
                print(f"    [WARNING] Watermark detection error: {e}")
            # Don't reject font on detection error, just skip this check
            return True, f"Watermark detection skipped: {e}"

    def check_font_file(self, font_path):
        """
        Check if a font file supports all required characters
        Uses both cmap check AND actual rendering test
        """
        try:
            # Step 1: Check cmap (character mapping table)
            font = TTFont(str(font_path))
            cmap = font.getBestCmap()

            if not cmap:
                return False, "No character map found"

            # Check for all required characters in cmap
            missing_in_cmap = []
            for codepoint, (name, char) in self.required_chars.items():
                if codepoint not in cmap:
                    missing_in_cmap.append(char)

            if missing_in_cmap:
                return False, f"Missing in cmap: {', '.join(missing_in_cmap)}"

            # Step 2: Test actual rendering with PIL (more robust check)
            # This catches fonts that have cmap entries but fail to render
            # Also detects .notdef glyphs (empty boxes for missing characters)
            try:
                pil_font = ImageFont.truetype(str(font_path), 32)
                test_img = Image.new('L', (100, 50), 255)  # Grayscale for comparison
                draw = ImageDraw.Draw(test_img)

                # First, get reference image of .notdef glyph (missing character box)
                # Use a character that almost certainly doesn't exist
                notdef_img = Image.new('L', (100, 50), 255)
                notdef_draw = ImageDraw.Draw(notdef_img)
                notdef_draw.text((10, 10), '\uffff', font=pil_font, fill=0)  # U+FFFF rarely exists
                notdef_bbox = notdef_img.getbbox()
                notdef_bytes = notdef_img.crop(notdef_bbox).tobytes() if notdef_bbox else None

                # Test each required character
                cannot_render = []
                for codepoint, (name, char) in self.required_chars.items():
                    try:
                        # Try to get bounding box - if it fails, font can't render it
                        bbox = draw.textbbox((0, 0), char, font=pil_font)
                        width = bbox[2] - bbox[0]

                        # Some fonts have glyphs with 0 width for missing chars
                        if width <= 0:
                            cannot_render.append(char)
                            continue

                        # Render the character and check if it's actually visible
                        char_img = Image.new('L', (100, 50), 255)
                        char_draw = ImageDraw.Draw(char_img)
                        char_draw.text((10, 10), char, font=pil_font, fill=0)
                        char_bbox = char_img.getbbox()
                        
                        # If getbbox() returns None, the glyph is empty/invisible
                        if char_bbox is None:
                            cannot_render.append(char)
                            continue
                        
                        # Compare with .notdef to detect placeholder glyphs
                        if notdef_bytes:
                            char_bytes = char_img.crop(char_bbox).tobytes()
                            # If identical to .notdef, the glyph doesn't really exist
                            if char_bytes == notdef_bytes:
                                cannot_render.append(char)

                    except Exception:
                        cannot_render.append(char)

                if cannot_render:
                    return False, f"Cannot render (missing/empty glyph): {', '.join(cannot_render)}"

            except Exception as e:
                return False, f"PIL rendering error: {str(e)}"

            # Step 3: Detect embedded logos/watermarks in regular glyphs
            # Renders each character individually and checks for anomalies
            try:
                logo_font = ImageFont.truetype(str(font_path), 64)
                char_images = []
                char_widths = []

                test_chars = list('ABCDEFGHabcdefgh0123456789')

                for char in test_chars:
                    try:
                        char_img = Image.new('L', (300, 100), 255)
                        char_draw = ImageDraw.Draw(char_img)
                        char_draw.text((10, 10), char, font=logo_font, fill=0)

                        bbox = char_img.getbbox()
                        if bbox:
                            width = bbox[2] - bbox[0]
                            height = bbox[3] - bbox[1]
                            char_widths.append(width)

                            # Crop to bounding box for comparison
                            cropped = char_img.crop(bbox)
                            char_images.append(cropped.tobytes())
                        else:
                            char_widths.append(0)
                            char_images.append(None)

                    except Exception:
                        char_widths.append(0)
                        char_images.append(None)

                # Check 1: If any glyph is abnormally wide (> 3x median), likely a logo
                valid_widths = [w for w in char_widths if w > 0]
                if valid_widths:
                    median_width = sorted(valid_widths)[len(valid_widths) // 2]
                    if median_width > 0:
                        for i, w in enumerate(char_widths):
                            if w > median_width * 3:
                                return False, f"Suspicious glyph detected (logo?): char '{test_chars[i]}' width {w} vs median {median_width}"

                # Check 2: If many different characters produce identical images, likely a logo
                valid_images = [img for img in char_images if img is not None]
                if len(valid_images) >= 4:
                    unique_images = set(valid_images)
                    duplicate_ratio = 1 - (len(unique_images) / len(valid_images))
                    if duplicate_ratio > 0.5:
                        return False, f"Too many identical glyphs ({duplicate_ratio:.0%}): likely embedded logo"

            except Exception as e:
                if self.verbose:
                    print(f"    [WARNING] Logo detection skipped: {e}")

            # Step 4: NEW - Detect watermarks in special characters (spaces, apostrophes)
            # This catches fonts like "Borgers" that embed "PERSONAL USE ONLY" in spaces
            try:
                is_clean, watermark_reason = self.detect_watermark_in_special_chars(font_path)
                if not is_clean:
                    return False, watermark_reason
            except Exception as e:
                if self.verbose:
                    print(f"    [WARNING] Special char watermark detection skipped: {e}")

            return True, "All characters supported and renderable"

        except Exception as e:
            return False, f"Error: {str(e)}"

    def get_all_font_files(self):
        """Get all font files from fonts directory"""
        font_files = []

        if not self.fonts_dir.exists():
            print(f"[ERROR] Fonts directory not found: {self.fonts_dir}")
            return []

        # Traverse all subdirectories
        for root, dirs, files in os.walk(self.fonts_dir):
            for file in files:
                if file.lower().endswith(('.ttf', '.otf')):
                    font_path = Path(root) / file
                    # Get relative path from fonts_dir
                    rel_path = font_path.relative_to(self.fonts_dir)
                    font_files.append({
                        'path': font_path,
                        'relative': rel_path,
                        'category': rel_path.parts[0] if len(rel_path.parts) > 1 else 'Unknown',
                        'font_folder': rel_path.parts[1] if len(rel_path.parts) > 2 else rel_path.parts[0]
                    })

        return font_files

    def verify_all_fonts(self):
        """Verify all fonts in the fonts directory"""
        print("=" * 60)
        print("FONT VERIFICATION - language-specific chars + numbers + punctuation")
        print("               + watermark detection in spaces/apostrophes")
        print("=" * 60)
        print()

        # Get all font files
        print("[1] Scanning fonts directory...")
        font_files = self.get_all_font_files()

        if not font_files:
            print("[ERROR] No font files found")
            return

        print(f"  [OK] Found {len(font_files)} font files")
        self.stats['total_fonts'] = len(font_files)

        # Verify each font
        print(f"\n[2] Verifying fonts...")

        for font_info in tqdm(font_files, desc="Checking fonts", unit="font"):
            font_path = font_info['path']
            is_valid, message = self.check_font_file(font_path)

            if is_valid:
                self.stats['valid_fonts'] += 1
                if self.verbose:
                    print(f"  [OK] {font_info['relative']}")
            else:
                self.stats['invalid_fonts'] += 1
                self.invalid_fonts.append({
                    'path': font_path,
                    'relative': font_info['relative'],
                    'category': font_info['category'],
                    'font_folder': font_info['font_folder'],
                    'reason': message
                })
                if self.verbose:
                    print(f"  [X] {font_info['relative']} - {message}")

        # Summary
        print(f"\n[3] Verification Summary:")
        print(f"  Total fonts checked: {self.stats['total_fonts']}")
        print(f"  Valid fonts: {self.stats['valid_fonts']}")
        print(f"  Invalid fonts: {self.stats['invalid_fonts']}")

        if self.invalid_fonts:
            print(f"\n[4] Invalid fonts by category:")
            # Group by category
            by_category = {}
            for font in self.invalid_fonts:
                cat = font['category']
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(font)

            for category, fonts in sorted(by_category.items()):
                print(f"  {category}: {len(fonts)} fonts")
                if self.verbose:
                    for font in fonts[:5]:  # Show first 5
                        print(f"    - {font['font_folder']}: {font['reason']}")
                    if len(fonts) > 5:
                        print(f"    ... and {len(fonts) - 5} more")

    def remove_invalid_fonts(self):
        """Remove invalid font folders"""
        if not self.invalid_fonts:
            print("\n[OK] No invalid fonts to remove")
            return

        print(f"\n[5] Removing invalid fonts...")

        if self.dry_run:
            print("  [DRY RUN] The following would be removed:")

        # Group by font folder (so we remove entire font folders, not individual files)
        folders_to_remove = set()
        for font in self.invalid_fonts:
            # Get the font folder path (category/font_name)
            font_folder = font['path'].parent
            folders_to_remove.add(font_folder)

        for folder in tqdm(sorted(folders_to_remove), desc="Removing folders", unit="folder"):
            try:
                if self.dry_run:
                    print(f"  [DRY RUN] Would remove: {folder.relative_to(self.fonts_dir)}")
                else:
                    shutil.rmtree(folder)
                    self.stats['removed_fonts'] += 1
                    if self.verbose:
                        print(f"  [REMOVED] {folder.relative_to(self.fonts_dir)}")
            except Exception as e:
                self.stats['errors'] += 1
                print(f"  [ERROR] Failed to remove {folder.relative_to(self.fonts_dir)}: {e}")

        if not self.dry_run:
            print(f"\n  [OK] Removed {self.stats['removed_fonts']} font folders")
            if self.stats['errors'] > 0:
                print(f"  [WARNING] {self.stats['errors']} errors occurred")

    def generate_report(self, output_file='font_verification_report.txt'):
        """Generate a detailed report of invalid fonts"""
        if not self.invalid_fonts:
            return

        print(f"\n[6] Generating report: {output_file}")

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("FONT VERIFICATION REPORT\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"Total fonts checked: {self.stats['total_fonts']}\n")
            f.write(f"Valid fonts: {self.stats['valid_fonts']}\n")
            f.write(f"Invalid fonts: {self.stats['invalid_fonts']}\n\n")

            f.write("=" * 60 + "\n")
            f.write("INVALID FONTS DETAILS\n")
            f.write("=" * 60 + "\n\n")

            # Group by category
            by_category = {}
            for font in self.invalid_fonts:
                cat = font['category']
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(font)

            for category, fonts in sorted(by_category.items()):
                f.write(f"\n{category} ({len(fonts)} fonts)\n")
                f.write("-" * 60 + "\n")
                for font in fonts:
                    f.write(f"  Font: {font['font_folder']}\n")
                    f.write(f"  Path: {font['relative']}\n")
                    f.write(f"  Reason: {font['reason']}\n\n")

        print(f"  [OK] Report saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description='Verify and clean fonts that don\'t support certain characters, numbers, and punctuation'
    )
    parser.add_argument('--language', default='catalan',
                        help='Idioma per verificar suport de caràcters (default: catalan)')
    parser.add_argument('--fonts-dir', default='fonts', help='Fonts directory (default: fonts)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be removed without actually removing')
    parser.add_argument('--no-remove', action='store_true', help='Only verify, don\'t remove invalid fonts')
    parser.add_argument('--report', default='font_verification_report.txt', help='Output report file')

    args = parser.parse_args()

    verifier = FontVerifier(
        fonts_dir=args.fonts_dir,
        language=args.language,
        verbose=args.verbose,
        dry_run=args.dry_run
    )

    # Verify all fonts
    verifier.verify_all_fonts()

    # Generate report if there are invalid fonts
    if verifier.invalid_fonts:
        verifier.generate_report(args.report)

    # Remove invalid fonts unless --no-remove is specified
    if not args.no_remove:
        verifier.remove_invalid_fonts()

    # Final summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Total fonts: {verifier.stats['total_fonts']}")
    print(f"Valid fonts: {verifier.stats['valid_fonts']}")
    print(f"Invalid fonts: {verifier.stats['invalid_fonts']}")
    if not args.no_remove and not args.dry_run:
        print(f"Removed: {verifier.stats['removed_fonts']} font folders")
    print()

    if args.dry_run:
        print("[DRY RUN] No files were actually removed")
        print("Run without --dry-run to remove invalid fonts")
    elif args.no_remove:
        print("[NO REMOVE] Fonts were verified but not removed")
        print("Run without --no-remove to remove invalid fonts")
    else:
        print("[SUCCESS] Font verification and cleanup complete!")

if __name__ == "__main__":
    main()
