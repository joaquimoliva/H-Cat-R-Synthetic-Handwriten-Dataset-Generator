#!/usr/bin/env python3
"""
Verificació robusta del dataset multilingüe.
Comprova: rectangles, metadata, modes, qualitat, caràcters especials per idioma.

Ús:
    python verificar_dataset.py                     # Usa output/
    python verificar_dataset.py output_test_fix     # Usa output_test_fix/
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

# Configuració - agafa argument o usa 'output' per defecte
if len(sys.argv) > 1:
    OUTPUT_DIR = sys.argv[1]
else:
    OUTPUT_DIR = 'output'

METADATA_FILES = [
    f'{OUTPUT_DIR}/train/metadata.jsonl',
    f'{OUTPUT_DIR}/validation/metadata.jsonl',
    f'{OUTPUT_DIR}/test/metadata.jsonl',
]

# Caràcters especials per idioma (que podrien ser rectangles)
SPECIAL_CHARS = {
    'catalan': 'àèéíïòóúüç·',
    'polish': 'ąęłńóśźż',
    'romanian': 'șțăâî',
    'czech': 'áčďéěíňóřšťúůýž',
    'hungarian': 'áéíóöőúüű',
}

# Fonts conegudes amb problemes de rectangles
PROBLEMATIC_FONTS = ['Cursif', 'Ecolier']

# Caràcters que sabem que són rectangles a Cursif/Ecolier
RECTANGLE_CHARS = set('óòáú')

def main():
    print(f"📂 Verificant: {OUTPUT_DIR}/")
    
    # Verificar que existeixen els fitxers
    existing_files = [f for f in METADATA_FILES if Path(f).exists()]
    if not existing_files:
        print(f"❌ ERROR: No existeixen fitxers metadata a {OUTPUT_DIR}/")
        print(f"\nUsa: python verificar_dataset.py <carpeta>")
        print(f"Exemple: python verificar_dataset.py output_test_fix")
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
                
                # Verificar nous camps metadata
                if 'char_count' not in e:
                    stats['errors'].append(f"{e['file_name']}: falta char_count")
                if 'word_count' not in e:
                    stats['errors'].append(f"{e['file_name']}: falta word_count")
                
                # Verificar coherència char_count/word_count
                if 'char_count' in e and e['char_count'] != len(e['text']):
                    stats['errors'].append(f"{e['file_name']}: char_count incorrecte")
                if 'word_count' in e and e['word_count'] != len(e['text'].split()):
                    stats['errors'].append(f"{e['file_name']}: word_count incorrecte")
                
                # Verificar rectangles (fonts problemàtiques + caràcters problemàtics)
                if e['font_name'] in PROBLEMATIC_FONTS:
                    if any(c in e['text'] for c in RECTANGLE_CHARS):
                        stats['rectangles'].append({
                            'file': e['file_name'],
                            'font': e['font_name'],
                            'chars': [c for c in RECTANGLE_CHARS if c in e['text']]
                        })
                
                # Registrar caràcters especials trobats per idioma
                if lang in SPECIAL_CHARS:
                    for c in SPECIAL_CHARS[lang]:
                        if c in e['text']:
                            stats['special_chars_found'][lang].add(c)

    # Mostrar resultats
    print("=" * 70)
    print("📊 VERIFICACIÓ DATASET MULTILINGÜE")
    print("=" * 70)
    
    print(f"\n📈 ESTADÍSTIQUES GENERALS")
    print(f"   Total imatges: {stats['total']:,}")
    print(f"   Fonts úniques: {len(stats['fonts'])}")
    
    print(f"\n🌍 IDIOMES")
    for lang, count in sorted(stats['languages'].items()):
        pct = count / stats['total'] * 100
        fonts = len(stats['fonts_per_lang'][lang])
        print(f"   {lang}: {count:,} imatges ({pct:.1f}%), {fonts} fonts")
    
    print(f"\n📝 MODES")
    for mode, count in stats['modes'].items():
        pct = count / stats['total'] * 100
        print(f"   {mode}: {count:,} ({pct:.1f}%)")
    
    print(f"\n🎨 QUALITAT")
    for q, count in stats['quality'].items():
        pct = count / stats['total'] * 100
        print(f"   {q}: {count:,} ({pct:.1f}%)")
    
    print(f"\n🔤 CARÀCTERS ESPECIALS TROBATS")
    for lang in SPECIAL_CHARS:
        if lang in stats['languages']:
            found = stats['special_chars_found'].get(lang, set())
            expected = set(SPECIAL_CHARS[lang])
            missing = expected - found
            if missing:
                print(f"   {lang}: ✅ trobats: {''.join(sorted(found))} | ⚠️  no trobats: {''.join(sorted(missing))}")
            else:
                print(f"   {lang}: ✅ tots trobats: {''.join(sorted(found))}")
    
    print(f"\n" + "=" * 70)
    print("🧪 TESTS")
    print("=" * 70)
    
    # Test 1: Rectangles
    if stats['rectangles']:
        print(f"\n❌ TEST RECTANGLES: FALLAT")
        print(f"   {len(stats['rectangles'])} imatges amb rectangles placeholder!")
        for item in stats['rectangles'][:5]:
            print(f"   - {item['file']} ({item['font']}): {item['chars']}")
    else:
        print(f"\n✅ TEST RECTANGLES: PASSAT")
        print(f"   Cap imatge amb glifs rectangle (ó,ò,á,ú) de fonts problemàtiques")
    
    # Test 2: Metadata
    if stats['errors']:
        print(f"\n❌ TEST METADATA: FALLAT")
        for err in stats['errors'][:5]:
            print(f"   - {err}")
        if len(stats['errors']) > 5:
            print(f"   ... i {len(stats['errors'])-5} errors més")
    else:
        print(f"\n✅ TEST METADATA: PASSAT")
        print(f"   Tots els registres tenen char_count i word_count correctes")
    
    # Test 3: Distribució modes (si s'espera 70/30)
    lines_pct = stats['modes'].get('lines', 0) / stats['total'] * 100
    words_pct = stats['modes'].get('words', 0) / stats['total'] * 100
    if 60 <= lines_pct <= 80:
        print(f"\n✅ TEST MODES: PASSAT")
        print(f"   Distribució {lines_pct:.0f}% lines / {words_pct:.0f}% words (esperat ~70/30)")
    else:
        print(f"\n⚠️  TEST MODES: REVISAR")
        print(f"   Distribució {lines_pct:.0f}% lines / {words_pct:.0f}% words (esperat ~70/30)")
    
    # Test 4: Múltiples idiomes
    if len(stats['languages']) >= 2:
        print(f"\n✅ TEST MULTILINGÜE: PASSAT")
        print(f"   {len(stats['languages'])} idiomes detectats")
    else:
        print(f"\n⚠️  TEST MULTILINGÜE: REVISAR")
        print(f"   Només {len(stats['languages'])} idioma(es) detectat(s)")
    
    # Resum final
    print(f"\n" + "=" * 70)
    all_passed = not stats['rectangles'] and not stats['errors']
    if all_passed:
        print("🎉 TOTS ELS TESTS CRÍTICS PASSATS!")
    else:
        print("⚠️  ALGUNS TESTS HAN FALLAT - REVISA ELS ERRORS")
    print("=" * 70)

if __name__ == '__main__':
    main()
