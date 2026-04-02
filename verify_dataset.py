#!/usr/bin/env python3
"""
Robust verification of multilingual datasets.
Checks: rectangles, metadata, modes, quality, special characters per language.

Usage:
    python verify_dataset.py                     # Uses output/
    python verify_dataset.py output_test_fix     # Uses output_test_fix/
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

# Configuration - takes argument or uses 'output' by default
if len(sys.argv) > 1:
    OUTPUT_DIR = sys.argv[1]
else:
    OUTPUT_DIR = 'output'

METADATA_FILES = [
    f'{OUTPUT_DIR}/train/metadata.jsonl',
    f'{OUTPUT_DIR}/validation/metadata.jsonl',
    f'{OUTPUT_DIR}/test/metadata.jsonl',
]

# Special characters per language (that could be rectangles)
SPECIAL_CHARS = {
    'catalan': 'àèéíïòóúüç·',
    'polish': 'ąęłńóśźż',
    'romanian': 'șțăâî',
    'czech': 'áčďéěíňóřšťúůýž',
    'hungarian': 'áéíóöőúüű',
}

# Known fonts with rectangle problems
PROBLEMATIC_FONTS = ['Cursif', 'Ecolier']

# Characters known to be rectangles in Cursif/Ecolier
RECTANGLE_CHARS = set('óòáú')

def main():
    print(f"📂 Verifying: {OUTPUT_DIR}/")
    
    # Check that metadata files exist
    existing_files = [f for f in METADATA_FILES if Path(f).exists()]
    if not existing_files:
        print(f"❌ ERROR: No metadata files found in {OUTPUT_DIR}/")
        print(f"\nUsage: python verify_dataset.py <folder>")
        print(f"Example: python verify_dataset.py output_test_fix")
        return

    stats = {
        'total': 0,
        'languages': defaultdict(int),
        'modes': defaultdict(int),
        'quality': defaultdict(int),
        'fonts': set(),
        'fonts_per_lang': defaultdict(set),
        'errors': [],
        'rectangles': [],
        'special_chars_found': defaultdict(set),
    }

    for metadata_file in existing_files:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            for line in f:
                e = json.loads(line)
                stats['total'] += 1
                lang = e.get('language', 'unknown')
                stats['languages'][lang] += 1
                stats['modes'][e.get('mode', 'lines')] += 1
                stats['quality'][e.get('quality', 'clean')] += 1
                stats['fonts'].add(e['font_name'])
                stats['fonts_per_lang'][lang].add(e['font_name'])
                
                # Verify new metadata fields
                if 'char_count' not in e:
                    stats['errors'].append(f"{e['file_name']}: missing char_count")
                if 'word_count' not in e:
                    stats['errors'].append(f"{e['file_name']}: missing word_count")
                
                # Verify char_count/word_count consistency
                if 'char_count' in e and e['char_count'] != len(e['text']):
                    stats['errors'].append(f"{e['file_name']}: incorrect char_count")
                if 'word_count' in e and e['word_count'] != len(e['text'].split()):
                    stats['errors'].append(f"{e['file_name']}: incorrect word_count")
                
                # Check for rectangles (problematic fonts + problematic characters)
                if e['font_name'] in PROBLEMATIC_FONTS:
                    if any(c in e['text'] for c in RECTANGLE_CHARS):
                        stats['rectangles'].append({
                            'file': e['file_name'],
                            'font': e['font_name'],
                            'chars': [c for c in RECTANGLE_CHARS if c in e['text']]
                        })
                
                # Record special characters found per language
                if lang in SPECIAL_CHARS:
                    for c in SPECIAL_CHARS[lang]:
                        if c in e['text']:
                            stats['special_chars_found'][lang].add(c)

    # Show results
    print("=" * 70)
    print("📊 MULTILINGUAL DATASET VERIFICATION")
    print("=" * 70)
    
    print(f"\n📈 GENERAL STATISTICS")
    print(f"   Total images: {stats['total']:,}")
    print(f"   Unique fonts: {len(stats['fonts'])}")
    
    print(f"\n🌍 LANGUAGES")
    for lang, count in sorted(stats['languages'].items()):
        pct = count / stats['total'] * 100
        fonts = len(stats['fonts_per_lang'][lang])
        print(f"   {lang}: {count:,} images ({pct:.1f}%), {fonts} fonts")
    
    print(f"\n📝 MODES")
    for mode, count in stats['modes'].items():
        pct = count / stats['total'] * 100
        print(f"   {mode}: {count:,} ({pct:.1f}%)")
    
    print(f"\n🎨 QUALITY")
    for q, count in stats['quality'].items():
        pct = count / stats['total'] * 100
        print(f"   {q}: {count:,} ({pct:.1f}%)")
    
    print(f"\n🔤 SPECIAL CHARACTERS FOUND")
    for lang in SPECIAL_CHARS:
        if lang in stats['languages']:
            found = stats['special_chars_found'].get(lang, set())
            expected = set(SPECIAL_CHARS[lang])
            missing = expected - found
            if missing:
                print(f"   {lang}: ✅ found: {''.join(sorted(found))} | ⚠️  not found: {''.join(sorted(missing))}")
            else:
                print(f"   {lang}: ✅ all found: {''.join(sorted(found))}")
    
    print(f"\n" + "=" * 70)
    print("🧪 TESTS")
    print("=" * 70)
    
    # Test 1: Rectangles
    if stats['rectangles']:
        print(f"\n❌ TEST RECTANGLES: FAILED")
        print(f"   {len(stats['rectangles'])} images with placeholder rectangles!")
        for item in stats['rectangles'][:5]:
            print(f"   - {item['file']} ({item['font']}): {item['chars']}")
    else:
        print(f"\n✅ TEST RECTANGLES: PASSED")
        print(f"   No images with rectangle glyphs (ó,ò,á,ú) from problematic fonts")
    
    # Test 2: Metadata
    if stats['errors']:
        print(f"\n❌ TEST METADATA: FAILED")
        for err in stats['errors'][:5]:
            print(f"   - {err}")
        if len(stats['errors']) > 5:
            print(f"   ... and {len(stats['errors'])-5} more errors")
    else:
        print(f"\n✅ TEST METADATA: PASSED")
        print(f"   All records have correct char_count and word_count")
    
    # Test 3: Mode distribution (with tolerance)
    lines_pct = stats['modes'].get('lines', 0) / stats['total'] * 100
    words_pct = stats['modes'].get('words', 0) / stats['total'] * 100
    # Accept if within reasonable range or single mode
    if lines_pct == 100 or words_pct == 100 or (55 <= lines_pct <= 85):
        print(f"\n✅ TEST MODES: PASSED")
        print(f"   Distribution {lines_pct:.0f}% lines / {words_pct:.0f}% words")
    else:
        print(f"\n⚠️  TEST MODES: REVIEW")
        print(f"   Distribution {lines_pct:.0f}% lines / {words_pct:.0f}% words")
    
    # Test 4: Multiple languages
    if len(stats['languages']) >= 2:
        print(f"\n✅ TEST MULTILINGUAL: PASSED")
        print(f"   {len(stats['languages'])} languages detected")
    elif len(stats['languages']) == 1:
        print(f"\n⚠️  TEST MULTILINGUAL: SINGLE LANGUAGE")
        print(f"   Only 1 language detected (OK if intended)")
    else:
        print(f"\n❌ TEST MULTILINGUAL: FAILED")
        print(f"   No languages detected")
    
    # Final summary
    print(f"\n" + "=" * 70)
    all_passed = not stats['rectangles'] and not stats['errors']
    if all_passed:
        print("🎉 ALL CRITICAL TESTS PASSED!")
    else:
        print("⚠️  SOME TESTS FAILED - REVIEW ERRORS")
    print("=" * 70)

if __name__ == '__main__':
    main()
