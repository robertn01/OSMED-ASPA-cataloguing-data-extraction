# OSMED-ASPA cataloguing and data extraction

This repository supports automated extraction of tabular and figure data from historical NASA Technical Reports Server (NTRS) PDFs for the OSMED/ASPA workflow.

The extraction code lives in:

- `/home/runner/work/OSMED-ASPA-cataloguing-data-extraction/OSMED-ASPA-cataloguing-data-extraction/files/ntrs-extractor`

The repository root also includes sample catalogues, sample source files, and legacy runbooks.

## What this project does

The pipeline is organized into three passes:

1. **Pass 1 — Catalogue**
   - Detects tables and figures per document.
   - Produces one catalogue workbook per PDF.
   - Splits records into `A_tabular` (tables) and `B_graphical` (figures).
2. **Pass 2 — Tables**
   - Extracts table data into CSV files.
   - Produces table QC workbooks.
3. **Pass 3 — Figures**
   - Traces data-bearing figures (line/scatter/bar/trace) to CSV.
   - Produces overlay images and figure QC workbooks.

The key expected output for cataloguing is:

- `catalogues/<program>/<doc_id>_catalogue.xlsx` (one per document)

with the main sheets:

- `A_tabular` (table catalogue)
- `B_graphical` (figure catalogue)
- `All`
- `Summary`

## Codebase structure

Inside `files/ntrs-extractor`:

- `src/ntrs_extractor/`
  - `cli.py` — command orchestration (`catalogue`, `tables`, `figures`, `all`)
  - `catalogue.py` / `catalogue_io.py` — Pass 1 detection and workbook I/O
  - `tables.py` — Pass 2 table extraction
  - `figures.py` — Pass 3 figure digitization/calibration
  - `qc.py` — shared QC scoring/reporting
  - `schema.py` — catalogue schema and program registry
  - `config.py` — `config/corpus.yaml` loader
  - `pdf_utils.py` — PDF text/page/raster helpers
- `config/corpus.yaml` — source-of-truth registry of documents
- `scripts/` — helper scripts (`fetch_ntrs.py`, `register_pdfs.py`, `run_all.py`)
- `tests/test_pipeline.py` — synthetic PDF tests for all 3 passes
- `docs/RUNBOOK.md` — full operational runbook

## Key technologies

- Python 3.10+
- `pandas`, `numpy`, `openpyxl`, `PyYAML`
- `pdfplumber`, `camelot-py` (tables)
- `opencv-python-headless`, `scikit-image`, `scipy` (figure digitization)
- Optional: `PyMuPDF` (`.[fast]`), `pytesseract` (`.[ocr]`)

## How to use the code

Run all commands from:

- `/home/runner/work/OSMED-ASPA-cataloguing-data-extraction/OSMED-ASPA-cataloguing-data-extraction/files/ntrs-extractor`

### 1) Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

For better table extraction (Camelot lattice mode), install Ghostscript:

```bash
sudo apt-get update && sudo apt-get install -y ghostscript
```

Optional extras:

```bash
pip install -e ".[fast]"
pip install -e ".[ocr]"
```

### 2) Register documents in `config/corpus.yaml`

The pipeline reads documents from `config/corpus.yaml`.
Each entry includes fields such as:

- `doc_id`
- `pdf_filename`
- `title`
- `ntrs_id` (optional)
- `printed_offset`

Use helper script for bulk registration:

```bash
python scripts/register_pdfs.py
```

### 3) Generate per-document catalogues (Pass 1)

```bash
# all documents in corpus.yaml
ntrs-extract catalogue

# one program only
ntrs-extract catalogue --program apollo

# one document only
ntrs-extract catalogue --doc A14
```

This produces one catalogue workbook per document at:

- `catalogues/<program>/<doc_id>_catalogue.xlsx`

Example:

- `catalogues/apollo/A14_catalogue.xlsx`

### 4) (Optional) Extract tables and figures

Tables:

```bash
ntrs-extract tables
ntrs-extract tables --program mercury
ntrs-extract tables --doc MR4
```

Figures:

```bash
ntrs-extract figures
ntrs-extract figures --program apollo
ntrs-extract figures --doc A14
```

### 5) Run full pipeline

```bash
python scripts/run_all.py
python scripts/run_all.py --program apollo
```

## Output locations

- **Pass 1 (catalogues):**
  - `catalogues/<program>/<doc_id>_catalogue.xlsx`
- **Pass 2 (table CSVs):**
  - `data/outputs/<program>/tables/<catalogue_id>.csv`
  - `qc/<program>/<doc_id>_tables_qc.xlsx`
- **Pass 3 (figure CSVs + overlays):**
  - `data/outputs/<program>/figures/<catalogue_id>.csv`
  - `qc/<program>/<doc_id>_figures_qc.xlsx`
  - `qc/<program>/overlays/<catalogue_id>.png`

## Validation

```bash
pytest -q
```

CI runs tests on Python 3.10–3.12 (`.github/workflows/ci.yml` under `files/ntrs-extractor`).

## Notes

- Commit code/config and curated `catalogues/*.xlsx`.
- Keep raw PDFs and derived outputs (`data/outputs/`, `qc/`) out of git.
- For complete operating guidance, see:
  - `files/ntrs-extractor/docs/RUNBOOK.md`
