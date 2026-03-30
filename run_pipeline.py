#!/usr/bin/env python3
"""
Script orquestrador del pipeline complet de generació de datasets sintètics.
Executa tots els passos en ordre amb una sola comanda.

Ús bàsic:
    python run_pipeline.py --language catalan -v

Ús amb tots els paràmetres:
    python run_pipeline.py --language catalan --max-articles 100 --font-pages 10 --mode lines --category-filter Handwritten --background-color white,grey --background-type lined,grid --workers -1 -v

Saltar passos:
    python run_pipeline.py --language catalan --skip-text --skip-fonts -v
"""

import subprocess
import sys
import argparse
import json
from pathlib import Path
import shutil


def run_step(step_name, command, verbose=False):
    """Executa un pas del pipeline i mostra el resultat"""
    separator = "=" * 60
    print(f"\n{separator}")
    print(f"  STEP: {step_name}")
    print(f"{separator}\n")

    if verbose:
        print(f"  Comanda: {' '.join(command)}\n")

    result = subprocess.run(command, capture_output=not verbose)

    if result.returncode != 0:
        print(f"\n  [ERROR] El pas '{step_name}' ha fallat!")
        if not verbose and result.stderr:
            print(f"  Error: {result.stderr.decode('utf-8', errors='replace')}")
        return False

    print(f"\n  [OK] {step_name} completat")
    return True


def load_language_config(language):
    """Carrega la configuració de l'idioma"""
    config_path = Path(__file__).parent / 'languages' / f'{language}.json'
    if not config_path.exists():
        available = [p.stem for p in (Path(__file__).parent / 'languages').glob('*.json')]
        print(f"[ERROR] No s'ha trobat la configuració per a '{language}'")
        print(f"  Idiomes disponibles: {', '.join(sorted(available))}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description='Pipeline complet de generació de datasets sintètics de escritura manuscrita',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  # Pipeline complet per a català (prova ràpida)
  python run_pipeline.py --language catalan --max-articles 10 --font-pages 2 --max-fonts-per-category 5 --max-texts 50 -v

  # Amb filtres de fons
  python run_pipeline.py --language catalan --background-color grey --background-type lined --skip-text --skip-fonts -v

  # Només paper blanc pautat
  python run_pipeline.py --language catalan --background-color white --background-type lined --skip-text --skip-fonts -v

  # Sense fons (només blanc llis)
  python run_pipeline.py --language catalan --no-backgrounds --skip-text --skip-fonts -v

  # Només generar dataset (textos i fonts ja descarregats)
  python run_pipeline.py --language catalan --skip-text --skip-fonts -v
        """
    )

    # Paràmetres generals
    parser.add_argument('--language', '-l', required=True,
                        help='Idioma (ex: catalan, spanish, basque, romanian...)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Mostrar informació detallada')
    parser.add_argument('--clean-output', action='store_true',
                        help='Esborrar la carpeta output abans de generar')

    # Control de passos
    parser.add_argument('--skip-text', action='store_true',
                        help='Saltar la descàrrega de textos')
    parser.add_argument('--skip-fonts', action='store_true',
                        help='Saltar la descàrrega i verificació de fonts')
    parser.add_argument('--skip-dataset', action='store_true',
                        help='Saltar la generació del dataset')

    # Paràmetres de textos
    parser.add_argument('--text-source', choices=['wikipedia', 'wikisource'], default='wikipedia',
                        help='Font de textos (default: wikipedia)')
    parser.add_argument('--max-articles', type=int, default=100,
                        help='Nombre màxim d\'articles a descarregar (default: 100)')

    # Paràmetres de fonts
    parser.add_argument('--font-pages', type=int, default=5,
                        help='Pàgines a escanejar dins la categoria seleccionada (default: 5)')

    # Paràmetres de fons
    parser.add_argument('--background-color', type=str, default=None,
                        help='Colors de fons, separats per comes (ex: white,grey,beige). Per defecte usa tots')
    parser.add_argument('--background-type', type=str, default=None,
                        help='Tipus de fons, separats per comes (ex: plain,grid,lined). Per defecte usa tots')
    parser.add_argument('--no-backgrounds', action='store_true',
                        help='Desactivar fons de paper (només blanc llis)')

    # Paràmetres de generació
    parser.add_argument('--mode', choices=['lines', 'words'], default='lines',
                        help='Mode de generació: lines o words (default: lines)')
    parser.add_argument('--style', choices=['normal', 'bold'], default='normal',
                        help='Estil de font (default: normal)')
    parser.add_argument('--category-filter', type=str, default='Handwritten',
                        help='Filtrar per categories de font, separades per comes (default: Handwritten)')
    parser.add_argument('--max-fonts-per-category', type=int, default=None,
                        help='Màxim de fonts per categoria')
    parser.add_argument('--max-texts', type=int, default=None,
                        help='Màxim de textos a usar')
    parser.add_argument('--workers', '-j', type=int, default=-1,
                        help='Workers paral·lels, -1 per tots els nuclis (default: -1)')
    parser.add_argument('--output-name', type=str, default=None,
                        help='Nom personalitzat per la carpeta output')

    args = parser.parse_args()

    # Carregar configuració de l'idioma
    lang_config = load_language_config(args.language)
    lang_code = lang_config['code']

    print("=" * 60)
    print("  PIPELINE DE GENERACIÓ DE DATASET SINTÈTIC")
    print("=" * 60)
    print(f"  Idioma: {args.language} ({lang_code})")
    print(f"  Font de textos: {args.text_source}")
    print(f"  Mode: {args.mode}")
    print(f"  Categoria fonts: {args.category_filter}")
    if args.no_backgrounds:
        print(f"  Fons: desactivats (només blanc llis)")
    else:
        bg_color_str = args.background_color if args.background_color else "tots"
        bg_type_str = args.background_type if args.background_type else "tots"
        print(f"  Fons color: {bg_color_str}")
        print(f"  Fons tipus: {bg_type_str}")
    if args.skip_text:
        print(f"  [SKIP] Descàrrega de textos")
    if args.skip_fonts:
        print(f"  [SKIP] Descàrrega de fonts")
    if args.skip_dataset:
        print(f"  [SKIP] Generació del dataset")
    print("=" * 60)

    verbose_flag = ['-v'] if args.verbose else []
    success = True

    # ============================================================
    # PAS 1: Descarregar textos
    # ============================================================
    if not args.skip_text:
        if args.text_source == 'wikipedia':
            cmd = [
                sys.executable, 'scrape_wikipedia.py',
                '--language', lang_code,
                '--max-articles', str(args.max_articles),
            ] + verbose_flag
        else:
            cmd = [
                sys.executable, 'scrape_wikisource.py',
                '--max-books', str(args.max_articles),
            ] + verbose_flag

        success = run_step(
            f"1/6 - Descarregar textos ({args.text_source}, {args.language})",
            cmd, args.verbose
        )
        if not success:
            print("\n[ABORT] Pipeline aturat per error al pas 1")
            sys.exit(1)
    else:
        print("\n[SKIP] Pas 1 - Descàrrega de textos (saltat)")

    # ============================================================
    # PAS 2: Escanejar fonts a DaFont
    # ============================================================
    if not args.skip_fonts:
        cmd = [
            sys.executable, 'scrape_dafont.py',
            '--language', args.language,
            '--category-filter', args.category_filter,
            '--pages', str(args.font_pages),
        ] + verbose_flag

        success = run_step(
            f"2/6 - Escanejar fonts compatibles amb {args.language}",
            cmd, args.verbose
        )
        if not success:
            print("\n[ABORT] Pipeline aturat per error al pas 2")
            sys.exit(1)

        # ============================================================
        # PAS 3: Descarregar fonts
        # ============================================================
        csv_file = 'compatible_fonts.csv'
        if not Path(csv_file).exists():
            csv_file = 'catalan_fonts.csv'

        if Path(csv_file).exists():
            cmd = [
                sys.executable, 'download_fonts.py',
                csv_file,
                '--skip-existing',
            ]

            success = run_step(
                "3/6 - Descarregar fonts",
                cmd, args.verbose
            )
            if not success:
                print("\n[ABORT] Pipeline aturat per error al pas 3")
                sys.exit(1)
        else:
            print(f"\n[WARNING] No s'ha trobat el fitxer CSV de fonts")

        # ============================================================
        # PAS 4: Verificar i netejar fonts
        # ============================================================
        cmd = [
            sys.executable, 'verify_and_clean_fonts.py',
            '--language', args.language,
        ] + verbose_flag

        success = run_step(
            f"4/6 - Verificar fonts per a {args.language}",
            cmd, args.verbose
        )
        if not success:
            print("\n[ABORT] Pipeline aturat per error al pas 4")
            sys.exit(1)
    else:
        print("\n[SKIP] Passos 2-4 - Descàrrega i verificació de fonts (saltats)")

    # ============================================================
    # PAS 5: Generar fons de paper (si no existeixen)
    # ============================================================
    backgrounds_dir = Path('backgrounds')
    if not args.no_backgrounds:
        if not backgrounds_dir.exists() or not any(backgrounds_dir.iterdir()):
            cmd = [
                sys.executable, 'generate_backgrounds.py',
            ] + verbose_flag

            success = run_step(
                "5/6 - Generar fons de paper",
                cmd, args.verbose
            )
            if not success:
                print("\n[WARNING] No s'han pogut generar els fons, continuant sense fons")
        else:
            bg_count = sum(1 for _ in backgrounds_dir.rglob('*.png'))
            print(f"\n[OK] Pas 5 - Fons de paper ja existents ({bg_count} imatges)")
    else:
        print("\n[SKIP] Pas 5 - Fons de paper (desactivats)")

    # ============================================================
    # PAS 6: Generar dataset
    # ============================================================
    if not args.skip_dataset:
        data_dir = f"data/wikipedia_{lang_code}" if args.text_source == 'wikipedia' else "data"

        output_dir = 'output'
        if args.output_name:
            output_dir = f'output_{args.output_name}'

        if args.clean_output and Path(output_dir).exists():
            print(f"\n  [CLEAN] Esborrant {output_dir}/...")
            shutil.rmtree(output_dir)

        cmd = [
            sys.executable, 'build_dataset.py',
            '--data-dir', data_dir,
            '--mode', args.mode,
            '--style', args.style,
            '--workers', str(args.workers),
        ] + verbose_flag

        if args.category_filter:
            cmd.extend(['--category-filter', args.category_filter])

        if args.max_fonts_per_category:
            cmd.extend(['--max-fonts-per-category', str(args.max_fonts_per_category)])

        if args.max_texts:
            cmd.extend(['--max-texts', str(args.max_texts)])

        if args.output_name:
            cmd.extend(['--output-name', args.output_name])

        # Fons de paper
        if args.no_backgrounds:
            cmd.extend(['--backgrounds-dir', 'none'])
        else:
            if args.background_color:
                cmd.extend(['--background-color', args.background_color])
            if args.background_type:
                cmd.extend(['--background-type', args.background_type])

        success = run_step(
            "6/6 - Generar dataset sintètic",
            cmd, args.verbose
        )
        if not success:
            print("\n[ABORT] Pipeline aturat per error al pas 6")
            sys.exit(1)
    else:
        print("\n[SKIP] Pas 6 - Generació del dataset (saltat)")

    # ============================================================
    # RESUM FINAL
    # ============================================================
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETAT!")
    print("=" * 60)
    print(f"  Idioma: {args.language}")
    print(f"  Textos: data/wikipedia_{lang_code}/")
    print(f"  Fonts: fonts/")
    print(f"  Fons: {'desactivats' if args.no_backgrounds else 'backgrounds/'}")
    output_dir = f"output_{args.output_name}" if args.output_name else "output"
    print(f"  Dataset: {output_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
