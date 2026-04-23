#!/usr/bin/env python3
"""
Orchestrator script for the complete synthetic dataset generation pipeline.
Executes all steps in order with a single command.

Basic usage:
    python run_pipeline.py --language catalan -v

Usage with all parameters:
    python run_pipeline.py --language catalan --max-articles 100 --font-pages 10 --mode lines --category-filter Handwritten --background-color white,grey --background-type lined,grid --workers -1 -v

With perturbations:
    python run_pipeline.py --language catalan --perturbations --quality-distribution 40,40,20 -v

Skip steps:
    python run_pipeline.py --language catalan --skip-text --skip-fonts -v
"""

import subprocess
import sys
import argparse
import json
from pathlib import Path
import shutil


def run_step(step_name, command, verbose=False):
    """Executes a pipeline step and shows the result"""
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
    """Loads the language configuration"""
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
        description='Complete pipeline for synthetic handwriting dataset generation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Complete pipeline for catalan (quick test)
  python run_pipeline.py --language catalan --max-articles 10 --font-pages 2 --max-fonts-per-category 5 --max-texts 50 -v

  # With background filters
  python run_pipeline.py --language catalan --background-color grey --background-type lined --skip-text --skip-fonts -v

  # With realistic perturbations
  python run_pipeline.py --language catalan --perturbations --quality-distribution 40,40,20 -v

  # More degraded images (robust training)
  python run_pipeline.py --language catalan --perturbations --quality-distribution 20,50,30 -v

  # Without backgrounds (white only)
  python run_pipeline.py --language catalan --no-backgrounds --skip-text --skip-fonts -v

  # Only generate dataset (texts and fonts already downloaded)
  python run_pipeline.py --language catalan --skip-text --skip-fonts -v
        """
    )

    # General parameters
    parser.add_argument('--language', '-l', required=True,
                        help='Language(s) comma-separated (e.g.: catalan or catalan,spanish,french)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed information')

    # Step control
    parser.add_argument('--skip-text', action='store_true',
                        help='Skip text download')
    parser.add_argument('--skip-fonts', action='store_true',
                        help='Skip font download and verification')
    parser.add_argument('--skip-dataset', action='store_true',
                        help='Skip dataset generation')

    # Text parameters
    parser.add_argument('--text-source', choices=['wikipedia', 'wikisource'], default='wikipedia',
                        help='Text source (default: wikipedia)')
    parser.add_argument('--max-articles', type=int, default=100,
                        help='Maximum number of articles to download (default: 100)')

    # Font parameters
    parser.add_argument('--font-pages', type=int, default=5,
                        help='Pages to scan within selected category (default: 5)')

    # Background parameters
    parser.add_argument('--background-color', type=str, default=None,
                        help='Background colors, comma-separated (e.g.: white,grey,beige). Uses all by default')
    parser.add_argument('--background-type', type=str, default=None,
                        help='Background types, comma-separated (e.g.: plain,grid,lined). Uses all by default')
    parser.add_argument('--no-backgrounds', action='store_true',
                        help='Disable paper backgrounds (white only)')

    # Perturbation parameters
    parser.add_argument('--perturbations', action='store_true',
                        help='Apply realistic perturbations (blur, rotation, noise, etc.)')
    parser.add_argument('--quality-distribution', type=str, default='40,40,20',
                        help='Quality distribution: clean,degraded,severe in %% (default: 40,40,20)')

    # Generation parameters
    parser.add_argument('--mode', type=str, default='lines',
                        help='Generation mode(s): lines, words, or lines,words for both')
    parser.add_argument('--mode-distribution', type=str, default=None,
                        help='Mode distribution in %% (e.g.: 70,30 for 70%% lines, 30%% words)')
    parser.add_argument('--style', choices=['normal', 'bold'], default='normal',
                        help='Font style (default: normal)')
    parser.add_argument('--category-filter', type=str, default='Handwritten',
                        help='Filter by font categories, comma-separated (default: Handwritten)')
    parser.add_argument('--max-fonts-per-category', type=int, default=None,
                        help='Maximum fonts per category')
    parser.add_argument('--max-texts', type=int, default=None,
                        help='Maximum texts to use')
    parser.add_argument('--total-images', type=int, default=None,
                        help='Total number of images to generate (balanced between languages)')
    parser.add_argument('--workers', '-j', type=int, default=-1,
                        help='Parallel workers, -1 for all cores (default: -1)')
    parser.add_argument('--output-name', type=str, default=None,
                        help='Custom name for output folder')
    parser.add_argument('--unique-texts', action='store_true',
                        help='Each text uses only one random font (maximizes text variety, recommended for HTR)')

    args = parser.parse_args()

    # Parse languages (comma-separated)
    languages = [lang.strip() for lang in args.language.split(',')]
    
    # Auto-calculate max_articles if --total-images is specified
    # and --max-articles was not explicitly set
    auto_articles = False
    if args.total_images and not args.skip_text:
        # Estimate available fonts
        estimated_fonts = args.max_fonts_per_category if args.max_fonts_per_category else 25
        
        # Calculate texts needed per language
        images_per_lang = args.total_images // len(languages)
        # Minimum 3 texts per language for proper split
        MIN_TEXTS_PER_LANG = 3
        
        # With --unique-texts, each text = 1 image
        # Without --unique-texts, each text = fonts_to_use images
        if args.unique_texts:
            texts_per_lang = images_per_lang  # 1 text = 1 image
        else:
            max_fonts_for_texts = images_per_lang // MIN_TEXTS_PER_LANG
            fonts_to_use = min(estimated_fonts, max_fonts_for_texts) if max_fonts_for_texts > 0 else estimated_fonts
            texts_per_lang = max(MIN_TEXTS_PER_LANG, images_per_lang // fonts_to_use)
        
        # Estimate needed articles (approx 30 useful sentences per article, x2 margin)
        SENTENCES_PER_ARTICLE = 30
        SAFETY_MARGIN = 2.0
        articles_needed = int((texts_per_lang / SENTENCES_PER_ARTICLE) * SAFETY_MARGIN) + 5
        articles_needed = max(10, articles_needed)  # Minimum 10 articles
        
        # If calculated value differs from default (100), update
        if articles_needed != args.max_articles:
            args.max_articles = articles_needed
            auto_articles = True
    
    # Validate quality-distribution
    quality_dist = args.quality_distribution.split(',')
    if len(quality_dist) != 3:
        print(f"[ERROR] --quality-distribution must have 3 comma-separated values (e.g.: 40,40,20)")
        sys.exit(1)
    try:
        quality_values = [int(x) for x in quality_dist]
        if sum(quality_values) != 100:
            print(f"[ERROR] --quality-distribution must sum to 100 (current: {sum(quality_values)})")
            sys.exit(1)
    except ValueError:
        print(f"[ERROR] --quality-distribution must contain integers")
        sys.exit(1)

    # Validate all languages before starting
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
        mode_str += f" (distribution: {args.mode_distribution})"
    elif ',' in args.mode:
        mode_str += " (distribution: 50,50)"
    print(f"  Mode: {mode_str}")
    print(f"  Font category: {args.category_filter}")
    if args.no_backgrounds:
        print(f"  Backgrounds: disabled (white only)")
    else:
        bg_color_str = args.background_color if args.background_color else "all"
        bg_type_str = args.background_type if args.background_type else "all"
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
    # STEPS 1-4: For each language, download texts and fonts
    # ============================================================
    for lang_idx, lang in enumerate(languages):
        lang_config = lang_configs[lang]
        lang_code = lang_config['code']
        
        if len(languages) > 1:
            print(f"\n{'='*60}")
            print(f"  PROCESSING LANGUAGE {lang_idx+1}/{len(languages)}: {lang} ({lang_code})")
            print(f"{'='*60}")

        # ============================================================
        # STEP 1: Download texts (for each language)
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
                f"1/6 - Download texts ({args.text_source}, {lang})",
                cmd, args.verbose
            )
            if not success:
                print(f"\n[ABORT] Pipeline stopped at step 1 ({lang})")
                sys.exit(1)
        else:
            if lang_idx == 0:
                print("\n[SKIP] Step 1 - Text download (skipped)")

        # ============================================================
        # STEPS 2-4: Fonts (only once, with the first language)
        # ============================================================
        if lang_idx == 0 and not args.skip_fonts:
            # STEP 2: Scan fonts on DaFont (for ALL languages)
            all_languages_str = ','.join(languages)
            cmd = [
                sys.executable, 'scrape_dafont.py',
                '--language', all_languages_str,
                '--category-filter', args.category_filter,
                '--pages', str(args.font_pages),
            ] + verbose_flag

            success = run_step(
                f"2/6 - Scan compatible fonts ({all_languages_str})",
                cmd, args.verbose
            )
            if not success:
                print("\n[ABORT] Pipeline stopped at step 2")
                sys.exit(1)

            # STEP 3: Download fonts
            csv_file = 'compatible_fonts.csv'

            if Path(csv_file).exists():
                cmd = [
                    sys.executable, 'download_fonts.py',
                    csv_file,
                    '--skip-existing',
                ]

                success = run_step(
                    "3/6 - Download fonts",
                    cmd, args.verbose
                )
                if not success:
                    print("\n[ABORT] Pipeline stopped at step 3")
                    sys.exit(1)
            else:
                print(f"\n[ABORT] File not found: {csv_file}")
                print(f"  Step 2 (scrape_dafont.py) should have created it.")
                sys.exit(1)

            # STEP 4: Verify and clean fonts (for ALL languages)
            cmd = [
                sys.executable, 'verify_and_clean_fonts.py',
                '--language', all_languages_str,
            ] + verbose_flag

            success = run_step(
                f"4/6 - Verify fonts ({all_languages_str})",
                cmd, args.verbose
            )
            if not success:
                print("\n[ABORT] Pipeline stopped at step 4")
                sys.exit(1)
        elif lang_idx == 0 and args.skip_fonts:
            print("\n[SKIP] Steps 2-4 - Font download and verification (skipped)")

    # ============================================================
    # STEP 5: Generate paper backgrounds (if not exist) - only once
    # ============================================================
    backgrounds_dir = Path('backgrounds')
    if not args.no_backgrounds:
        if not backgrounds_dir.exists() or not any(backgrounds_dir.iterdir()):
            cmd = [
                sys.executable, 'generate_backgrounds.py',
            ] + verbose_flag

            success = run_step(
                "5/6 - Generate paper backgrounds",
                cmd, args.verbose
            )
            if not success:
                print("\n[WARNING] Could not generate backgrounds, continuing without")
        else:
            bg_count = sum(1 for _ in backgrounds_dir.rglob('*.png'))
            print(f"\n[OK] Step 5 - Paper backgrounds already exist ({bg_count} images)")
    else:
        print("\n[SKIP] Step 5 - Paper backgrounds (disabled)")

    # ============================================================
    # STEP 6: Generate dataset (all languages together)
    # ============================================================
    if not args.skip_dataset:
        if args.output_name:
            output_dir = args.output_name if args.output_name.startswith('output') else f'output_{args.output_name}'
        else:
            output_dir = 'output'

        # Always delete existing folder to avoid mixing images
        if Path(output_dir).exists():
            print(f"\n  [CLEAN] Deleting {output_dir}/ to avoid mixing images...")
            shutil.rmtree(output_dir)

        # Build list of data directories and languages
        data_dirs = []
        for lang in languages:
            lang_code = lang_configs[lang]['code']
            data_dir = f"data/wikipedia_{lang_code}" if args.text_source == 'wikipedia' else "data"
            data_dirs.append(data_dir)
        
        # Pass as comma-separated lists
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

        # Auto-balance if multiple languages
        if len(languages) > 1:
            cmd.append('--balanced')

        if args.output_name:
            cmd.extend(['--output-name', args.output_name])

        # Paper backgrounds
        if args.no_backgrounds:
            cmd.extend(['--backgrounds-dir', 'none'])
        else:
            if args.background_color:
                cmd.extend(['--background-color', args.background_color])
            if args.background_type:
                cmd.extend(['--background-type', args.background_type])

        # Perturbations
        if args.perturbations:
            cmd.append('--perturbations')
            cmd.extend(['--quality-distribution', args.quality_distribution])

        # Unique texts (1 font per text)
        if args.unique_texts:
            cmd.append('--unique-texts')

        success = run_step(
            f"6/6 - Generate synthetic dataset ({', '.join(languages)})",
            cmd, args.verbose
        )
        if not success:
            print(f"\n[ABORT] Pipeline stopped at step 6")
            sys.exit(1)
    else:
        print("\n[SKIP] Step 6 - Dataset generation (skipped)")

    # ============================================================
    # FINAL SUMMARY
    # ============================================================
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETED!")
    print("=" * 60)
    if len(languages) == 1:
        print(f"  Language: {languages[0]}")
        print(f"  Texts: data/wikipedia_{lang_configs[languages[0]]['code']}/")
    else:
        print(f"  Languages: {', '.join(languages)}")
        for lang in languages:
            print(f"    - {lang}: data/wikipedia_{lang_configs[lang]['code']}/")
    print(f"  Fonts: fonts/")
    print(f"  Backgrounds: {'disabled' if args.no_backgrounds else 'backgrounds/'}")
    if args.perturbations:
        print(f"  Perturbations: {args.quality_distribution} (clean/degraded/severe)")
    output_dir = f"output_{args.output_name}" if args.output_name else "output"
    print(f"  Dataset: {output_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
