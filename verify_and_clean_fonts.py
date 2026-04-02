#!/usr/bin/env python3
"""
Verify existing fonts for corruption and watermark detection.
By default, does NOT remove fonts based on language-specific characters
(this is now handled by build_dataset.py per-language filtering).

Only removes fonts that:
- Are corrupted (cannot be loaded)
- Have no valid character map
- Contain embedded watermarks/logos
"""

import os
import shutil
from pathlib import Path
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm
import argparse

class FontVerifier:
    def __init__(self, fonts_dir='fonts', language='catalan', verbose=False, 
                 dry_run=False, check_language_chars=False):
        self.fonts_dir = Path(fonts_dir)
        self.verbose = verbose
        self.dry_run = dry_run
        self.check_language_chars = check_language_chars

        # Load language config (only used if check_language_chars=True)
        self.language = language
        self.lang_config = self._load_language_config(language)

        # Base required characters - only numbers and basic punctuation
        # These are needed by ANY language, so safe to check always
        self.base_required_chars = {
            0x0030: ('0 (zero)', '0'),
            0x0031: ('1 (one)', '1'),
            0x0032: ('2 (two)', '2'),
            0x0033: ('3 (three)', '3'),
            0x0034: ('4 (four)', '4'),
            0x0035: ('5 (five)', '5'),
            0x0036: ('6 (six)', '6'),
            0x0037: ('7 (seven)', '7'),
            0x0038: ('8 (eight)', '8'),
            0x0039: ('9 (nine)', '9'),
            0x002D: ('hyphen-minus', '-'),
            0x0028: ('left parenthesis', '('),
            0x0029: ('right parenthesis', ')'),
            0x0020: ('space', ' '),
            0x002E: ('period', '.'),
            0x002C: ('comma', ','),
        }
        
        # Full required chars (base + language-specific)
        self.required_chars = dict(self.base_required_chars)
        
        # Only add language-specific characters if explicitly requested
        if self.check_language_chars:
            for char in self.lang_config.get('required_chars', []):
                codepoint = ord(char)
                self.required_chars[codepoint] = (f'lang-specific: {char}', char)

        self.stats = {
            'total_fonts': 0,
            'valid_fonts': 0,
            'invalid_fonts': 0,
            'removed_fonts': 0,
            'errors': 0,
            'watermark_detected': 0,
            'corrupted': 0,
            'missing_chars': 0
        }

        self.invalid_fonts = []  # Store info about invalid fonts

    def _load_language_config(self, language):
        """Load language configuration from languages/"""
        import json
        config_path = Path(__file__).parent / 'languages' / f'{language}.json'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            if self.verbose:
                print(f"[INFO] No language config found: {config_path}")
            return {'required_chars': []}

    def detect_watermark_in_special_chars(self, font_path, font_size=64):
        """
        Detect watermarks embedded in special characters (spaces, apostrophes, etc.)
        
        Many DaFont fonts embed "PERSONAL USE ONLY" or similar watermarks in:
        - Space character (U+0020)
        - Apostrophe (U+0027)
        - Quotation marks (U+0022, U+2018, U+2019)
        - Other punctuation
        
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
        Check if a font file is valid and usable.
        
        Checks:
        1. Font can be loaded (not corrupted)
        2. Has a valid character map
        3. Can render basic characters
        4. No embedded logos in regular glyphs
        5. No watermarks in special characters (spaces, apostrophes)
        6. (Optional) Supports language-specific characters
        
        Returns: (is_valid, reason, issue_type)
        """
        try:
            # Step 1: Check cmap (character mapping table)
            font = TTFont(str(font_path))
            cmap = font.getBestCmap()

            if not cmap:
                return False, "No character map found", "corrupted"

            # Step 2: Check for base required characters in cmap
            # Only check base chars (numbers, basic punctuation) - NOT language-specific
            chars_to_check = self.required_chars if self.check_language_chars else self.base_required_chars
            
            missing_in_cmap = []
            for codepoint, (name, char) in chars_to_check.items():
                if codepoint not in cmap:
                    missing_in_cmap.append(char)

            if missing_in_cmap:
                issue_type = "missing_lang_chars" if self.check_language_chars else "missing_base_chars"
                return False, f"Missing in cmap: {', '.join(missing_in_cmap)}", issue_type

            # Step 3: Test actual rendering with PIL (more robust check)
            try:
                pil_font = ImageFont.truetype(str(font_path), 32)
                test_img = Image.new('RGB', (200, 50), 'white')
                draw = ImageDraw.Draw(test_img)

                # Test each required character
                cannot_render = []
                for codepoint, (name, char) in chars_to_check.items():
                    try:
                        bbox = draw.textbbox((0, 0), char, font=pil_font)
                        width = bbox[2] - bbox[0]
                        if width <= 0:
                            cannot_render.append(char)
                    except Exception:
                        cannot_render.append(char)

                if cannot_render:
                    return False, f"Cannot render: {', '.join(cannot_render)}", "corrupted"

            except Exception as e:
                return False, f"PIL rendering error: {str(e)}", "corrupted"

            # Step 4: Detect embedded logos/watermarks in regular glyphs
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
                            char_widths.append(width)
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
                                return False, f"Suspicious glyph (logo?): '{test_chars[i]}' width {w} vs median {median_width}", "watermark"

                # Check 2: If many different characters produce identical images, likely a logo
                valid_images = [img for img in char_images if img is not None]
                if len(valid_images) >= 4:
                    unique_images = set(valid_images)
                    duplicate_ratio = 1 - (len(unique_images) / len(valid_images))
                    if duplicate_ratio > 0.5:
                        return False, f"Too many identical glyphs ({duplicate_ratio:.0%}): likely embedded logo", "watermark"

            except Exception as e:
                if self.verbose:
                    print(f"    [WARNING] Logo detection skipped: {e}")

            # Step 5: Detect watermarks in special characters (spaces, apostrophes)
            try:
                is_clean, watermark_reason = self.detect_watermark_in_special_chars(font_path)
                if not is_clean:
                    return False, watermark_reason, "watermark"
            except Exception as e:
                if self.verbose:
                    print(f"    [WARNING] Special char watermark detection skipped: {e}")

            return True, "Font is valid and usable", "valid"

        except Exception as e:
            return False, f"Error: {str(e)}", "corrupted"

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
        if self.check_language_chars:
            print(f"FONT VERIFICATION - watermarks + corruption + {self.language} chars")
        else:
            print("FONT VERIFICATION - watermarks + corruption only")
            print("(language-specific char filtering done by build_dataset.py)")
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
            is_valid, message, issue_type = self.check_font_file(font_path)

            if is_valid:
                self.stats['valid_fonts'] += 1
                if self.verbose:
                    print(f"  [OK] {font_info['relative']}")
            else:
                self.stats['invalid_fonts'] += 1
                
                # Track issue types
                if issue_type == "watermark":
                    self.stats['watermark_detected'] += 1
                elif issue_type == "corrupted":
                    self.stats['corrupted'] += 1
                elif issue_type in ("missing_lang_chars", "missing_base_chars"):
                    self.stats['missing_chars'] += 1
                
                self.invalid_fonts.append({
                    'path': font_path,
                    'relative': font_info['relative'],
                    'category': font_info['category'],
                    'font_folder': font_info['font_folder'],
                    'reason': message,
                    'issue_type': issue_type
                })
                if self.verbose:
                    print(f"  [X] {font_info['relative']} - {message}")

        # Summary
        print(f"\n[3] Verification Summary:")
        print(f"  Total fonts checked: {self.stats['total_fonts']}")
        print(f"  Valid fonts: {self.stats['valid_fonts']}")
        print(f"  Invalid fonts: {self.stats['invalid_fonts']}")
        if self.stats['invalid_fonts'] > 0:
            print(f"    - Watermarks/logos: {self.stats['watermark_detected']}")
            print(f"    - Corrupted/unloadable: {self.stats['corrupted']}")
            print(f"    - Missing characters: {self.stats['missing_chars']}")

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
            f.write(f"Invalid fonts: {self.stats['invalid_fonts']}\n")
            f.write(f"  - Watermarks/logos: {self.stats['watermark_detected']}\n")
            f.write(f"  - Corrupted: {self.stats['corrupted']}\n")
            f.write(f"  - Missing chars: {self.stats['missing_chars']}\n\n")

            f.write("=" * 60 + "\n")
            f.write("INVALID FONTS DETAILS\n")
            f.write("=" * 60 + "\n\n")

            # Group by issue type
            by_type = {}
            for font in self.invalid_fonts:
                t = font.get('issue_type', 'unknown')
                if t not in by_type:
                    by_type[t] = []
                by_type[t].append(font)

            for issue_type, fonts in sorted(by_type.items()):
                f.write(f"\n{issue_type.upper()} ({len(fonts)} fonts)\n")
                f.write("-" * 60 + "\n")
                for font in fonts:
                    f.write(f"  Font: {font['font_folder']}\n")
                    f.write(f"  Path: {font['relative']}\n")
                    f.write(f"  Reason: {font['reason']}\n\n")

        print(f"  [OK] Report saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description='Verify and clean fonts - removes corrupted fonts and those with watermarks'
    )
    parser.add_argument('--language', default='catalan',
                        help='Language for char verification (only used with --check-language-chars)')
    parser.add_argument('--fonts-dir', default='fonts', help='Fonts directory (default: fonts)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be removed without actually removing')
    parser.add_argument('--no-remove', action='store_true', help='Only verify, don\'t remove invalid fonts')
    parser.add_argument('--check-language-chars', action='store_true', 
                        help='Also check language-specific characters (by default, only watermarks and corruption)')
    parser.add_argument('--report', default='font_verification_report.txt', help='Output report file')

    args = parser.parse_args()

    verifier = FontVerifier(
        fonts_dir=args.fonts_dir,
        language=args.language,
        verbose=args.verbose,
        dry_run=args.dry_run,
        check_language_chars=args.check_language_chars
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
    if verifier.stats['invalid_fonts'] > 0:
        print(f"  - Watermarks/logos: {verifier.stats['watermark_detected']}")
        print(f"  - Corrupted: {verifier.stats['corrupted']}")
        print(f"  - Missing base chars: {verifier.stats['missing_chars']}")
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
