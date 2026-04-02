## Pipeline Usage

The `run_pipeline.py` script orchestrates the complete synthetic handwriting dataset generation process. It executes all steps in sequence with a single command.

### Basic Usage

```bash
python run_pipeline.py --language <IDIOMA> [opcions]
```

**Multilingual support:** Use comma-separated languages to generate a mixed dataset:
```bash
python run_pipeline.py --language catalan,polish,romanian --total-images 300
```

Each language uses its own pool of compatible fonts, maximizing typographic variety.

### Understanding Dataset Composition

When generating a dataset, you need to balance two types of variety:

| Type | Benefit | Controlled by |
|------|---------|---------------|
| **Typographic variety** | More handwriting styles | Number of fonts |
| **Linguistic variety** | More diverse sentences | Number of texts |

Since `total images = texts × fonts`, you must choose what to prioritize:

#### How Auto-Balancing Works

**Without `--total-images`:** Uses all texts × all fonts. This can generate thousands of images!

**With `--total-images`:** The system calculates how many texts and fonts to use:

**Single language (most common):**
```
texts_to_use = total_images / available_fonts
```
Uses all available fonts and adjusts the number of texts to reach the target.

**Example:** `--total-images 500` with 50 fonts available
```
texts = 500 / 50 = 10 texts per font
Result: 10 texts × 50 fonts = 500 images ✓
```

**Multiple languages:**
Each language gets an equal share of images, then balances independently:
```
images_per_language = total_images / num_languages
```

| Language | Fonts available | Calculation | Result |
|----------|-----------------|-------------|--------|
| Catalan | 74 | 20 fonts × 5 texts | 100 images |
| Polish | 16 | 16 fonts × 6 texts | 96 images |
| Romanian | 6 | 6 fonts × 16 texts | 96 images |

Languages with fewer fonts automatically get more texts per font.

#### Quick Decision Guide

| Your goal | Recommendation |
|-----------|----------------|
| Train a robust HTR model | Balance both: `--total-images 1000` (system auto-balances) |
| Test many handwriting styles | Prioritize fonts: `--max-texts 5` (few texts, all fonts) |
| Test linguistic coverage | Prioritize texts: `--max-fonts-per-category 10` (few fonts, many texts) |
| Maximum variety | Don't set limits, use `--total-images` only |

#### Examples

```bash
# Balanced (recommended): 1000 images, system decides distribution
python run_pipeline.py --language catalan --total-images 1000

# Prioritize fonts: 5 texts × all available fonts
python run_pipeline.py --language catalan --max-texts 5

# Prioritize texts: all texts × max 10 fonts
python run_pipeline.py --language catalan --max-fonts-per-category 10

# Explicit control: exactly 20 texts × 15 fonts = 300 images
python run_pipeline.py --language catalan --max-texts 20 --max-fonts-per-category 15
```

### Command-Line Arguments

#### General Parameters

| Argument | Short | Description |
|----------|-------|-------------|
| `--language` | `-l` | Required. Target language(s) comma-separated (e.g., `catalan`, `spanish,french`) |
| `--verbose` | `-v` | Show detailed output during execution |
| `--output-name` | | Custom name for output folder. Without it, uses `output/`. With `--output-name test`, uses `output_test/`. The target folder is automatically deleted (if exists) before each run to avoid mixing images from different experiments |

#### Step Control

| Argument | Description |
|----------|-------------|
| `--skip-text` | Skip text download (use existing texts) |
| `--skip-fonts` | Skip font download and verification (use existing fonts) |

#### Text Parameters

Text samples are natural sentences extracted from Wikipedia articles, filtered to a suitable length for HTR (approximately 30-150 characters). The system automatically downloads enough articles based on `--total-images`.

#### Font Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--font-pages` | `5` | Number of DaFont pages to scan per category |
| `--category-filter` | `Handwritten` | Font categories (comma-separated): `Handwritten`, `School` |

**Note:** The scraper and generator automatically filter fonts that:
- Don't support required characters for the target language(s)
- Don't have common punctuation glyphs (`, . : ; ! ?`)
- Are in the blacklist (known watermarks or broken glyphs)
- Show watermark patterns in generated test images
- Have **rectangle placeholder glyphs** (▢) instead of real characters — detected at generation time by analyzing glyph contours

#### Generation Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--total-images` | No limit | Target total images. If not set, generates `all_texts × all_fonts` (can be very large!) |
| `--max-texts` | All available | Limit texts per language. Use low values (5-10) to prioritize font variety |
| `--max-fonts-per-category` | All available | Limit fonts per category. Use low values (10-20) to prioritize text variety |
| `--mode` | `lines` | Generation mode: `lines` (sentences), `words` (individual words), or `lines,words` for both |
| `--mode-distribution` | `50,50` | Distribution of **images** when using mixed modes (e.g., `70,30` for 70% lines images, 30% words images) |

**Tip:** Always set `--total-images` or limit texts/fonts to avoid generating unexpectedly large datasets.

**Mode examples:**
```bash
# Only lines (default)
python run_pipeline.py --language catalan --mode lines --total-images 1000

# Only words  
python run_pipeline.py --language catalan --mode words --total-images 1000

# Mixed: 50% lines, 50% words (default distribution)
python run_pipeline.py --language catalan --mode lines,words --total-images 1000

# Mixed: 70% lines, 30% words (applied to IMAGES, not texts)
python run_pipeline.py --language catalan --mode lines,words --mode-distribution 70,30 --total-images 1000
```

**Note:** The `--mode-distribution` applies to the final **images**, not to texts. The system automatically calculates how many texts to assign to each mode to achieve the desired image distribution.

#### Background Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--background-color` | All | Background colors: `white`, `grey`, `beige` (comma-separated) |
| `--background-type` | All | Background types: `plain`, `grid`, `lined` (comma-separated) |
| `--no-backgrounds` | | Disable paper backgrounds (plain white only) |

#### Perturbation Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--perturbations` | Off | Enable realistic perturbations (blur, rotation, noise, etc.) |
| `--quality-distribution` | `40,40,20` | Quality distribution as `clean,degraded,severe` percentages (must sum to 100) |

**Quality Levels:**
- **Clean:** No perturbations applied
- **Degraded:** Light perturbations (max 2, max 1 heavy) — subtle blur, minor rotation (±0.5°), light noise
- **Severe:** Heavy perturbations (max 3, max 2 heavy) — mandatory blur + contrast/brightness reduction, rotation (±1.0°)

### Examples

```bash
# Basic: single language
python run_pipeline.py --language catalan -v

# Multilingual with target images
python run_pipeline.py --language catalan,polish,romanian \
    --total-images 300 --perturbations -v

# Full pipeline with all options
python run_pipeline.py --language english \
    --category-filter Handwritten,School --font-pages 50 \
    --total-images 2000 --perturbations --quality-distribution 40,40,20 \
    --output-name english_dataset -v

# Quick regeneration (reuse existing texts and fonts)
python run_pipeline.py --language catalan \
    --skip-text --skip-fonts \
    --total-images 500 --perturbations -v
```

### Output Metadata

Each generated image includes metadata in `metadata.jsonl`:

```json
{
  "file_name": "00000001.png",
  "text": "Reconstrucció de marca Després d'un llarg període,",
  "char_count": 50,
  "word_count": 7,
  "language": "catalan",
  "font_name": "Belle_Allure",
  "font_category": "School",
  "font_style": "normal",
  "source_book": "wikipedia_ca",
  "background_type": "grid",
  "background_color": "grey",
  "mode": "lines",
  "quality": "severe",
  "perturbations": {
    "blur_radius": 2.48,
    "rotation_angle": -1.78,
    "contrast_factor": 0.48
  }
}
```

| Field | Description |
|-------|-------------|
| `char_count` | Number of characters in the text |
| `word_count` | Number of words in the text |
| `mode` | `lines` (full sentence) or `words` (single word) |
| `quality` | `clean`, `degraded`, or `severe` |
| `perturbations` | Applied perturbations (only present if quality ≠ clean) |

### Dataset Verification

Use `verify_dataset.py` to validate generated datasets:

```bash
# Verify a specific dataset
python verify_dataset.py output_my_dataset

# Default: verifies output/
python verify_dataset.py
```

**Checks performed:**
- ✅ Rectangle glyphs (placeholder characters from problematic fonts)
- ✅ Metadata integrity (`char_count`, `word_count` correctness)
- ✅ Mode distribution (lines vs words percentages)
- ✅ Quality distribution (clean/degraded/severe)
- ✅ Multilingual support (languages detected)
- ✅ Special characters per language

**Example output:**
```
📂 Verificant: output_test/
======================================================================
📊 VERIFICACIÓ DATASET MULTILINGÜE
======================================================================
📈 ESTADÍSTIQUES GENERALS
   Total imatges: 1,333
   Fonts úniques: 36
🌍 IDIOMES
   catalan: 1,333 imatges (100.0%), 36 fonts
📝 MODES
   lines: 981 (73.6%)
   words: 352 (26.4%)
🎨 QUALITAT
   clean: 558 (41.9%)
   degraded: 520 (39.0%)
   severe: 255 (19.1%)
======================================================================
🧪 TESTS
======================================================================
✅ TEST RECTANGLES: PASSAT
✅ TEST METADATA: PASSAT
✅ TEST MODES: PASSAT
✅ TEST MULTILINGÜE: PASSAT
======================================================================
🎉 TOTS ELS TESTS CRÍTICS PASSATS!
======================================================================
```
