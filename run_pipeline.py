#!/usr/bin/env python3
"""
Script orquestrador del pipeline complet de generació de datasets sintètics.
Executa tots els passos en ordre amb una sola comanda.

Ús bàsic:
    python run_pipeline.py --language catalan -v

Ús amb tots els paràmetres:
    python run_pipeline.py --language catalan --max-articles 100 --font-pages 10 --mode lines --category-filter Handwritten --background-color white,grey --background-type lined,grid --workers -1 -v

Amb pertorbacions:
    python run_pipeline.py --language catalan --perturbations --quality-distribution 40,40,20 -v

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
        print(f"  Command: {' '.join(command)}\n")

    result = subprocess.run(command, capture_output=not verbose)

    if result.returncode != 0:
        print(f"\n  [ERROR] Step '{step_name}' failed!")
        if not verbose and result.stderr:
            print(f"  Error: {result.stderr.decode('utf-8', errors='replace')}")
        return False

    print(f"\n  [OK] {step_name} completed")
    return True


def load_language_config(language):
    """Carrega la configuració de l'idioma"""
    config_path = Path(__file__).parent / 'languages' / f'{language}.json'
    if not config_path.exists():
        available = [p.stem for p in (Path(__file__).parent / 'languages').glob('*.json')]
        print(f"[ERROR] Configuration not found for '{language}'")
        print(f"  Available languages: {', '.join(sorted(available))}")
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

  # Amb pertorbacions realistes
  python run_pipeline.py --language catalan --perturbations --quality-distribution 40,40,20 -v

  # Més images degradades (entrenament robust)
  python run_pipeline.py --language catalan --perturbations --quality-distribution 20,50,30 -v

  # Sense fons (només blanc llis)
  python run_pipeline.py --language catalan --no-backgrounds --skip-text --skip-fonts -v

  # Només generar dataset (textos i fonts ja descarregats)
  python run_pipeline.py --language catalan --skip-text --skip-fonts -v
        """
    )

    # Paràmetres generals
    parser.add_argument('--language', '-l', required=True,
                        help='Idioma/es separats per comes (ex: catalan o catalan,spanish,french)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Mostrar informació detallada')

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

    # Paràmetres de pertorbacions
    parser.add_argument('--perturbations', action='store_true',
                        help='Aplicar pertorbacions realistes (blur, rotació, soroll, etc.)')
    parser.add_argument('--quality-distribution', type=str, default='40,40,20',
                        help='Distribució de qualitat: clean,degraded,severe en %% (default: 40,40,20)')

    # Paràmetres de generació
    parser.add_argument('--mode', type=str, default='lines',
                        help='Mode(s) de generació: lines, words, o lines,words per ambdós')
    parser.add_argument('--mode-distribution', type=str, default=None,
                        help='Distribució de modes en %% (ex: 70,30 per 70%% lines, 30%% words)')
    parser.add_argument('--style', choices=['normal', 'bold'], default='normal',
                        help='Estil de font (default: normal)')
    parser.add_argument('--category-filter', type=str, default='Handwritten',
                        help='Filtrar per categories de font, separades per comes (default: Handwritten)')
    parser.add_argument('--max-fonts-per-category', type=int, default=None,
                        help='Màxim de fonts per categoria')
    parser.add_argument('--max-texts', type=int, default=None,
                        help='Màxim de textos a usar')
    parser.add_argument('--total-images', type=int, default=None,
                        help='Nombre total d\'images a generar (equilibrat entre languages)')
    parser.add_argument('--workers', '-j', type=int, default=-1,
                        help='Workers paral·lels, -1 per tots els nuclis (default: -1)')
    parser.add_argument('--output-name', type=str, default=None,
                        help='Nom personalitzat per la carpeta output')

    args = parser.parse_args()

    # Parsejar languages (separats per comes)
    languages = [lang.strip() for lang in args.language.split(',')]
    
    # Calcular max_articles automàticament si s'especifica --total-images
    # i no s'ha especificat --max-articles explícitament
    auto_articles = False
    if args.total_images and not args.skip_text:
        # Estimar fonts disponibles
        estimated_fonts = args.max_fonts_per_category if args.max_fonts_per_category else 25
        
        # Calcular textos necessaris per idioma
        images_per_lang = args.total_images // len(languages)
        # Mínim 3 textos per idioma per fer split adequat
        MIN_TEXTS_PER_LANG = 3
        max_fonts_for_texts = images_per_lang // MIN_TEXTS_PER_LANG
        fonts_to_use = min(estimated_fonts, max_fonts_for_texts) if max_fonts_for_texts > 0 else estimated_fonts
        texts_per_lang = max(MIN_TEXTS_PER_LANG, images_per_lang // fonts_to_use)
        
        # Estimar articles necessaris (aprox 30 frases útils per article, ×2 marge)
        FRASES_PER_ARTICLE = 30
        SAFETY_MARGIN = 2.0
        articles_needed = int((texts_per_lang / FRASES_PER_ARTICLE) * SAFETY_MARGIN) + 5
        articles_needed = max(10, articles_needed)  # Mínim 10 articles
        
        # Si el valor calculat és diferent del default (100), actualitzar
        if articles_needed != args.max_articles:
            args.max_articles = articles_needed
            auto_articles = True
    
    # Validar quality-distribution
    quality_dist = args.quality_distribution.split(',')
    if len(quality_dist) != 3:
        print(f"[ERROR] --quality-distribution must have 3 comma-separated values (ex: 40,40,20)")
        sys.exit(1)
    try:
        quality_values = [int(x) for x in quality_dist]
        if sum(quality_values) != 100:
            print(f"[ERROR] --quality-distribution must sum to 100 (current: {sum(quality_values)})")
            sys.exit(1)
    except ValueError:
        print(f"[ERROR] --quality-distribution must contain integers")
        sys.exit(1)

    # Validar tots els languages abans de començar
    lang_configs = {}
    for lang in languages:
        lang_configs[lang] = load_language_config(lang)

    print("=" * 60)
    print("  SYNTHETIC DATASET GENERATION PIPELINE")
    print("=" * 60)
    if len(languages) == 1:
        print(f"  Language: {languages[0]} ({lang_configs[languages[0]]['code']})")
    else:
        print(f"  Languages: {', '.join(languages)} ({len(languages)} languages)")
    print(f"  Text source: {args.text_source}")
    mode_str = args.mode
    if ',' in args.mode and args.mode_distribution:
        mode_str += f" (distribució: {args.mode_distribution})"
    elif ',' in args.mode:
        mode_str += " (distribució: 50,50)"
    print(f"  Mode: {mode_str}")
    print(f"  Font category: {args.category_filter}")
    if args.no_backgrounds:
        print(f"  Backgrounds: disabled (white only)")
    else:
        bg_color_str = args.background_color if args.background_color else "tots"
        bg_type_str = args.background_type if args.background_type else "tots"
        print(f"  Background color: {bg_color_str}")
        print(f"  Background type: {bg_type_str}")
    if args.perturbations:
        print(f"  Perturbations: ON ({args.quality_distribution} clean/degraded/severe)")
    else:
        print(f"  Perturbations: OFF")
    if args.skip_text:
        print(f"  [SKIP] Text download")
    elif auto_articles:
        print(f"  Articles per language: {args.max_articles} (auto-calculated for {args.total_images} images)")
    if args.skip_fonts:
        print(f"  [SKIP] Font download")
    if args.skip_dataset:
        print(f"  [SKIP] Dataset generation")
    print("=" * 60)

    verbose_flag = ['-v'] if args.verbose else []
    success = True

    # ============================================================
    # PASSOS 1-4: Per cada idioma, descarregar textos i fonts
    # ============================================================
    for lang_idx, lang in enumerate(languages):
        lang_config = lang_configs[lang]
        lang_code = lang_config['code']
        
        if len(languages) > 1:
            print(f"\n{'='*60}")
            print(f"  PROCESSANT IDIOMA {lang_idx+1}/{len(languages)}: {lang} ({lang_code})")
            print(f"{'='*60}")

        # ============================================================
        # PAS 1: Descarregar textos (per cada idioma)
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
                f"1/6 - Descarregar textos ({args.text_source}, {lang})",
                cmd, args.verbose
            )
            if not success:
                print(f"\n[ABORT] Pipeline aturat per error al pas 1 ({lang})")
                sys.exit(1)
        else:
            if lang_idx == 0:
                print("\n[SKIP] Pas 1 - Text download (saltat)")

        # ============================================================
        # PAS 2-4: Fonts (només una vegada, amb el primer idioma)
        # ============================================================
        if lang_idx == 0 and not args.skip_fonts:
            # PAS 2: Escanejar fonts a DaFont (per TOTS els languages)
            all_languages_str = ','.join(languages)
            cmd = [
                sys.executable, 'scrape_dafont.py',
                '--language', all_languages_str,
                '--category-filter', args.category_filter,
                '--pages', str(args.font_pages),
            ] + verbose_flag

            success = run_step(
                f"2/6 - Escanejar fonts compatibles ({all_languages_str})",
                cmd, args.verbose
            )
            if not success:
                print("\n[ABORT] Pipeline aturat per error al pas 2")
                sys.exit(1)

            # PAS 3: Descarregar fonts
            csv_file = 'compatible_fonts.csv'

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
                print(f"\n[ABORT] No s'ha trobat {csv_file}")
                print(f"  El pas 2 (scrape_dafont.py) hauria d'haver-lo creat.")
                sys.exit(1)

            # PAS 4: Verificar i netejar fonts (per TOTS els languages)
            cmd = [
                sys.executable, 'verify_and_clean_fonts.py',
                '--language', all_languages_str,
            ] + verbose_flag

            success = run_step(
                f"4/6 - Verificar fonts ({all_languages_str})",
                cmd, args.verbose
            )
            if not success:
                print("\n[ABORT] Pipeline aturat per error al pas 4")
                sys.exit(1)
        elif lang_idx == 0 and args.skip_fonts:
            print("\n[SKIP] Passos 2-4 - Descàrrega i verificació de fonts (saltat)")

    # ============================================================
    # PAS 5: Generar fons de paper (si no existeixen) - només una vegada
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
            print(f"\n[OK] Pas 5 - Fons de paper ja existents ({bg_count} images)")
    else:
        print("\n[SKIP] Pas 5 - Fons de paper (desactivats)")

    # ============================================================
    # PAS 6: Generar dataset (tots els languages junts)
    # ============================================================
    if not args.skip_dataset:
        output_dir = 'output'
        if args.output_name:
            output_dir = f'output_{args.output_name}'

        # Sempre eliminar carpeta existent per evitar barrejar images
        if Path(output_dir).exists():
            print(f"\n  [CLEAN] Esborrant {output_dir}/ per evitar barrejar images...")
            shutil.rmtree(output_dir)

        # Construir llista de directoris de dades i languages
        data_dirs = []
        for lang in languages:
            lang_code = lang_configs[lang]['code']
            data_dir = f"data/wikipedia_{lang_code}" if args.text_source == 'wikipedia' else "data"
            data_dirs.append(data_dir)
        
        # Passar com a llistes separades per comes
        data_dirs_str = ','.join(data_dirs)
        languages_str = ','.join(languages)

        cmd = [
            sys.executable, 'build_dataset.py',
            '--data-dir', data_dirs_str,
            '--language', languages_str,
            '--mode', args.mode,
            '--style', args.style,
            '--workers', str(args.workers),
        ] + verbose_flag

        if args.mode_distribution:
            cmd.extend(['--mode-distribution', args.mode_distribution])

        if args.category_filter:
            cmd.extend(['--category-filter', args.category_filter])

        if args.max_fonts_per_category:
            cmd.extend(['--max-fonts-per-category', str(args.max_fonts_per_category)])

        if args.max_texts:
            cmd.extend(['--max-texts', str(args.max_texts)])

        if args.total_images:
            cmd.extend(['--total-images', str(args.total_images)])

        # Equilibrar automàticament si hi ha múltiples languages
        if len(languages) > 1:
            cmd.append('--balanced')

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

        # Pertorbacions
        if args.perturbations:
            cmd.append('--perturbations')
            cmd.extend(['--quality-distribution', args.quality_distribution])

        success = run_step(
            f"6/6 - Generar dataset sintètic ({', '.join(languages)})",
            cmd, args.verbose
        )
        if not success:
            print(f"\n[ABORT] Pipeline aturat per error al pas 6")
            sys.exit(1)
    else:
        print("\n[SKIP] Pas 6 - Dataset generation (saltat)")

    # ============================================================
    # RESUM FINAL
    # ============================================================
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETAT!")
    print("=" * 60)
    if len(languages) == 1:
        print(f"  Language: {languages[0]}")
        print(f"  Textos: data/wikipedia_{lang_configs[languages[0]]['code']}/")
    else:
        print(f"  Languages: {', '.join(languages)}")
        for lang in languages:
            print(f"    - {lang}: data/wikipedia_{lang_configs[lang]['code']}/")
    print(f"  Fonts: fonts/")
    print(f"  Fons: {'desactivats' if args.no_backgrounds else 'backgrounds/'}")
    if args.perturbations:
        print(f"  Pertorbacions: {args.quality_distribution} (clean/degraded/severe)")
    output_dir = f"output_{args.output_name}" if args.output_name else "output"
    print(f"  Dataset: {output_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
