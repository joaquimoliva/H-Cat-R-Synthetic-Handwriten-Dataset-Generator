# Synthetic Handwriting Dataset Generator for HTR

A Python framework for generating synthetic multilingual handwritten text datasets for Handwritten Text Recognition (HTR) training. The system automatically downloads texts from Wikipedia, scrapes handwriting fonts from DaFont, and generates realistic synthetic images with configurable perturbations.

## Features

- **Multilingual support:** 35 languages with Latin script
- **Automatic font discovery:** Scrapes DaFont for handwriting fonts with character validation
- **Realistic perturbations:** Blur, rotation, noise, contrast/brightness variations
- **Multiple generation modes:** Full sentences (`lines`) or individual words (`words`)
- **Paper backgrounds:** Grid, lined, and plain textures in multiple colors
- **Unique texts mode:** Maximize text diversity for HTR training (1 font per text)
- **HuggingFace-compatible output:** Ready for ML training pipelines

## Requirements

```bash
pip install pillow fonttools tqdm requests beautifulsoup4
```

## Quick Start

```bash
# Generate a basic dataset
python run_pipeline.py --language english --total-images 1000 -v

# Multilingual dataset with perturbations
python run_pipeline.py --language catalan,polish,romanian \
    --total-images 3000 --perturbations -v

# Mixed modes (70% sentences, 30% words)
python run_pipeline.py --language spanish \
    --mode lines,words --mode-distribution 70,30 \
    --total-images 2000 --perturbations -v

# Maximized text diversity (recommended for HTR training)
python run_pipeline.py --language french \
    --total-images 5000 --unique-texts --perturbations -v
```

## Pipeline Steps

The pipeline executes 6 steps in order:

1. **Download texts** — Fetches text from Wikipedia/Wikisource API
2. **Scan fonts** — Searches DaFont for compatible fonts
3. **Download fonts** — Downloads font files (.ttf/.otf)
4. **Verify fonts** — Validates character support and removes incompatible fonts
5. **Generate backgrounds** — Creates paper texture images (if not existing)
6. **Generate dataset** — Produces synthetic handwriting images with metadata

## Output Structure

The generated dataset follows HuggingFace format with train/validation/test splits:

```
output/
├── train/
│   ├── 00000001.png
│   ├── 00000002.png
│   ├── ...
│   └── metadata.jsonl
├── validation/
│   ├── ...
│   └── metadata.jsonl
├── test/
│   ├── ...
│   └── metadata.jsonl
└── dataset_info.json
```

## Supported Languages

The framework supports **35 languages** with Latin script. Each language has a configuration file in `languages/` defining required special characters, Wikipedia URLs, and sample text for font verification.

### Category A — Global Languages (>50M speakers)

| Language | Code | Speakers | Diacritics |
|----------|------|----------|------------|
| English | en | ~1,500M | none |
| Spanish | es | ~550M | ñ, á, é, í, ó, ú |
| Portuguese | pt | ~260M | à, á, â, ã, ç, é, ê, í, ó, ô, õ, ú |
| French | fr | ~275M | à, â, ç, é, è, ê, ë, î, ï, ô, ù, û, ü, ÿ, œ, æ |
| German | de | ~135M | ä, ö, ü, ß |
| Indonesian | id | ~200M | none |
| Vietnamese | vi | ~85M | many tones (ă, â, đ, ê, ô, ơ, ư + accents) |
| Italian | it | ~65M | à, è, é, ì, ò, ù |
| Turkish | tr | ~85M | ç, ğ, ı, ö, ş, ü |
| Polish | pl | ~45M | ą, ć, ę, ł, ń, ó, ś, ź, ż |
| Dutch | nl | ~25M | none (ij optional) |
| Malay | ms | ~80M | none |
| Swahili | sw | ~100M | none |

### Category B — European National Languages (5-25M speakers)

| Language | Code | Speakers | Diacritics |
|----------|------|----------|------------|
| Romanian | ro | ~24M | ă, â, î, ș, ț |
| Czech | cs | ~10M | á, č, ď, é, ě, í, ň, ó, ř, š, ť, ú, ů, ý, ž |
| Hungarian | hu | ~13M | á, é, í, ó, ö, ő, ú, ü, ű |
| Swedish | sv | ~10M | å, ä, ö |
| Catalan | ca | ~10M | à, ç, è, é, í, ï, ò, ó, ú, ü, l·l |
| Croatian | hr | ~5M | č, ć, đ, š, ž |
| Slovak | sk | ~5M | á, ä, č, ď, é, í, ĺ, ľ, ň, ó, ô, ŕ, š, ť, ú, ý, ž |
| Danish | da | ~6M | æ, ø, å |
| Norwegian | no | ~5M | æ, ø, å |
| Finnish | fi | ~5M | ä, ö |
| Slovenian | sl | ~2.5M | č, š, ž |
| Lithuanian | lt | ~3M | ą, č, ę, ė, į, š, ų, ū, ž |
| Latvian | lv | ~1.5M | ā, č, ē, ģ, ī, ķ, ļ, ņ, š, ū, ž |
| Estonian | et | ~1.1M | ä, ö, ü, õ |

### Category C — Minority and Regional Languages (<1M native speakers)

| Language | Code | Speakers | Diacritics |
|----------|------|----------|------------|
| Galician | gl | ~2.5M | á, é, í, ñ, ó, ú |
| Basque | eu | ~750K | ñ |
| Welsh | cy | ~500K | â, ê, î, ô, û, ŵ, ŷ |
| Icelandic | is | ~350K | á, ð, é, í, ó, ú, ý, þ, æ, ö |
| Irish | ga | ~1.7M (few native) | á, é, í, ó, ú |
| Breton | br | ~200K | añ, eñ, iñ, oñ, uñ |
| Asturian | ast | ~100-450K | ḥ, ḷ, ñ |
| Occitan | oc | ~100-500K | à, á, ç, è, é, í, ï, ò, ó, ú |
| Aragonese | an | ~10-25K | á, é, í, ó, ú |

### Unsupported Languages (Non-Latin Alphabets)

| Alphabet | Languages |
|----------|-----------|
| Cyrillic | Russian, Ukrainian, Bulgarian, Serbian, Macedonian, Belarusian, Kazakh |
| Greek | Modern Greek |
| Arabic | Arabic, Persian, Urdu |
| Hebrew | Hebrew, Yiddish |
| CJK | Chinese (simplified/traditional), Japanese, Korean |
| Indic | Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati |
| Others | Thai, Georgian, Armenian, Amharic, Khmer |

---

## Command-Line Arguments

### General Parameters

| Argument | Short | Description |
|----------|-------|-------------|
| `--language` | `-l` | **Required.** Target language(s) comma-separated (e.g., `catalan`, `spanish,french`) |
| `--verbose` | `-v` | Show detailed output during execution |
| `--output-name` | | Custom name for output folder (e.g., `--output-name test` creates `output_test/`) |

### Step Control

| Argument | Description |
|----------|-------------|
| `--skip-text` | Skip text download (use existing texts) |
| `--skip-fonts` | Skip font download and verification (use existing fonts) |

### Font Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--font-pages` | `5` | Number of DaFont pages to scan per category |
| `--category-filter` | `Handwritten` | Font categories: `Handwritten`, `School` (comma-separated) |

**Automatic font filtering:**
- Fonts without required characters for target language(s)
- Fonts missing common punctuation (`, . : ; ! ?`)
- Blacklisted fonts (known watermarks or broken glyphs)
- Fonts with rectangle placeholder glyphs (▢) detected at generation time

### Generation Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--total-images` | No limit | Target total images |
| `--max-texts` | All | Limit texts per language |
| `--max-fonts-per-category` | All | Limit fonts per category |
| `--mode` | `lines` | Mode: `lines`, `words`, or `lines,words` |
| `--mode-distribution` | `50,50` | Image distribution for mixed modes (e.g., `70,30`) |
| `--unique-texts` | Off | Each text uses only one random font (maximizes text diversity) |

**Note:** `--mode-distribution` applies to **images**, not texts. The system calculates optimal text-to-mode assignment automatically.

> ⚠️ **Minimum dataset size:** The `--mode-distribution` parameter works accurately for datasets of **2,000+ images**. For smaller datasets, the granularity of image generation may prevent achieving the exact target distribution. This occurs because selecting 'words' mode for a single text generates approximately 10× more images than 'lines' mode (one image per word × number of fonts vs. one image per sentence × number of fonts).

### Unique Texts Mode

The `--unique-texts` flag changes how fonts are assigned to texts:

| Mode | Behavior | Text Diversity |
|------|----------|----------------|
| **Default** | Each text × all compatible fonts | Low (~1-5%) |
| **`--unique-texts`** | Each text × 1 random font | High (~100%) |

**When to use `--unique-texts`:**
- ✅ **HTR training:** Maximizes vocabulary and character sequence diversity
- ✅ **Fine-tuning:** Better generalization to unseen text patterns
- ✅ **Low-resource scenarios:** More effective use of limited training data

**When NOT to use:**
- ❌ **Font style learning:** When you need many examples of each font
- ❌ **Writer identification:** When font/style consistency matters

### Background Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--background-color` | All | Colors: `white`, `grey`, `beige` |
| `--background-type` | All | Types: `plain`, `grid`, `lined` |
| `--no-backgrounds` | | Disable backgrounds (plain white only) |

### Perturbation Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--perturbations` | Off | Enable realistic perturbations |
| `--quality-distribution` | `40,40,20` | Percentages for `clean,degraded,severe` |

**Quality Levels:**
- **Clean:** No perturbations
- **Degraded:** Light perturbations (subtle blur, minor rotation ±0.5°, light noise)
- **Severe:** Heavy perturbations (mandatory blur, contrast reduction, rotation ±1.0°)

---

## Examples

```bash
# Basic single language
python run_pipeline.py --language catalan -v

# Multilingual with perturbations
python run_pipeline.py --language catalan,polish,romanian \
    --total-images 3000 --perturbations -v

# Full pipeline with all options
python run_pipeline.py --language english \
    --category-filter Handwritten,School --font-pages 50 \
    --total-images 5000 --perturbations --quality-distribution 40,40,20 \
    --mode lines,words --mode-distribution 70,30 \
    --output-name english_full -v

# Quick regeneration (reuse existing texts and fonts)
python run_pipeline.py --language catalan \
    --skip-text --skip-fonts \
    --total-images 1000 --perturbations -v

# HTR-optimized dataset with maximum text diversity
python run_pipeline.py --language german \
    --total-images 10000 --unique-texts \
    --perturbations --quality-distribution 30,50,20 \
    --output-name german_htr -v
```

---

## Output Metadata

Each image includes metadata in `metadata.jsonl`:

```json
{
  "file_name": "00000001.png",
  "text": "The quick brown fox jumps over the lazy dog.",
  "char_count": 44,
  "word_count": 9,
  "language": "english",
  "font_name": "Belle_Allure",
  "font_category": "School",
  "font_style": "normal",
  "source_book": "wikipedia_en",
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
| `char_count` | Number of characters |
| `word_count` | Number of words |
| `mode` | `lines` (sentence) or `words` (single word) |
| `quality` | `clean`, `degraded`, or `severe` |
| `perturbations` | Applied perturbations (if quality ≠ clean) |

---

## Dataset Verification

Use `verify_dataset.py` to validate generated datasets:

```bash
python verify_dataset.py output_my_dataset
```

**Checks performed:**
- ✅ Rectangle glyphs (placeholder characters)
- ✅ Metadata integrity (`char_count`, `word_count`)
- ✅ Mode distribution (lines vs words)
- ✅ Quality distribution (clean/degraded/severe)
- ✅ Multilingual support
- ✅ Special characters per language

**Example output:**
```
📂 Verifying: output_test/
======================================================================
📊 MULTILINGUAL DATASET VERIFICATION
======================================================================
📈 GENERAL STATISTICS
   Total images: 4,428
   Unique fonts: 52
🌍 LANGUAGES
   catalan: 1,344 images (30.4%), 33 fonts
   polish: 1,683 images (38.0%), 33 fonts
   romanian: 1,401 images (31.6%), 10 fonts
📝 MODES
   lines: 2,697 (60.9%)
   words: 1,731 (39.1%)
🎨 QUALITY
   clean: 1,549 (35.0%)
   degraded: 1,775 (40.1%)
   severe: 1,104 (24.9%)
======================================================================
🧪 TESTS
======================================================================
✅ TEST RECTANGLES: PASSED
✅ TEST METADATA: PASSED
✅ TEST MODES: PASSED
✅ TEST MULTILINGUAL: PASSED
======================================================================
🎉 ALL CRITICAL TESTS PASSED!
======================================================================
```

---

## License

MIT License

## Acknowledgments

This project is a fork of [Daniel Grao's TFG](https://github.com/original-repo) with significant enhancements for multilingual support, mode mixing, and quality assurance.
