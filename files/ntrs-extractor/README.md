# NTRS Extractor

A self-contained, three-pass ML/computer-vision pipeline for **cataloguing** and
**extracting** tabular and figure data from historical NASA reports sourced from
the [NASA Technical Reports Server (NTRS)](https://ntrs.nasa.gov/).

Work is organised **space-program-by-space-program** (Mercury, Gemini, Apollo,
Skylab, ...). All extraction code is centrally controlled here and versioned in
Git.

## Documentation

- **[docs/RUNBOOK.md](docs/RUNBOOK.md)** — step-by-step how-to for running the
  cataloguing then table/figure extraction on an extended corpus (setup → PDFs →
  register → Pass 1 → Pass 2 → Pass 3 → QC → scaling → troubleshooting). **Start
  here to operate the tools.**
- **[docs/METHOD.md](docs/METHOD.md)** — why the design works the way it does.
- This README — architecture overview and reference.

---

## The three passes

| Pass | Name | Module | Output |
|------|------|--------|--------|
| 1 | **Catalogue** (automated + manual confirm) | `catalogue.py`, `catalogue_io.py` | one `*_catalogue.xlsx` per document, split into `A_tabular` / `B_graphical` sub-catalogues |
| 2 | **Table reader** | `tables.py` | one CSV per table + `*_tables_qc.xlsx` |
| 3 | **Figure reader** (hardest) | `figures.py` | one `(series,x,y)` CSV per data chart + a QC overlay PNG + `*_figures_qc.xlsx` |

Each pass has **QC built in**: every item gets a 0–1 quality score mapped to a
green / amber / red traffic light (`qc.py`). Amber/red items are surfaced in a
per-document QC workbook for human review.

### Pass 1 — Catalogue (start automated, finish manual)
`catalogue.py` runs an **automated cataloguing pass first** so a human only has to
*confirm and correct*, never build the list from scratch:
- a caption grammar finds every `Table N …` / `Figure N …` (arabic **and** roman,
  hyphenated section numbers like `3-I`, `4-7`), and distinguishes a real caption
  from an in-text reference (`see Table 2`);
- `pdfplumber` ruling-line / whitespace table finders give independent evidence
  for tables and an **approximate rows × columns** shape (data-volume gauge);
- figures are classified into a subtype (`line`, `scatter`, `bar`, `trace`,
  `schematic`, `photo`, `map`) so Pass 3 knows which ones are data-bearing.

The catalogue columns match the OSMED/ASPA corpus-catalogue template:

```
catalogue_id | printed_page_number | pdf_page_number | kind | item_number |
original_source | description | approx_rows | approx_cols
```

plus automation/provenance columns (`sub_catalogue`, `figure_subtype`,
`detection_method`, `detection_confidence`, `extractable`, `extraction_status`,
`output_path`, `qc_flag`, `qc_notes`, `reviewer`).

Two sub-catalogues per document (separate worksheet tabs):
- **A_tabular** — tables;
- **B_graphical** — any non-table data visualisation.

### Pass 2 — Table reader
Tries `camelot` *lattice* → `camelot` *stream* → `pdfplumber` lines and keeps the
best result by a QC score that rewards dense, rectangular, number-heavy grids and
penalises ragged rows / empty cells / single columns.

### Pass 3 — Figure reader (the hard one)
1. rasterise the figure region;
2. detect the plot rectangle (longest horizontal/vertical dark runs → axes);
3. **calibrate pixels→data** from two x and two y tick references
   (`CalibrationSpec`; linear or log). Uncalibrated runs still emit the traced
   **pixel** curve and are capped at *amber* (`needs_review`);
4. trace data ink inside the plot and split into series (handles the common
   1–2 curve NTRS charts);
5. write `(series, x, y)` CSV **and a QC overlay PNG** (recovered points drawn on
   the original) so a reviewer can eyeball fidelity.

> Fully unattended tick-label reading is unreliable on 1960s microfilm scans, so
> the reliable path is: auto-trace → human supplies 4 tick references → calibrated
> data. Optional `pytesseract` support can pre-fill the tick guesses.

---

## Install

```bash
python -m pip install -e ".[dev]"        # add ".[fast]" for PyMuPDF, ".[ocr]" for tesseract
# camelot 'lattice' needs ghostscript:  apt-get install ghostscript
```

## Run

> **New to this?** Follow the full step-by-step guide in
> **[`docs/RUNBOOK.md`](docs/RUNBOOK.md)** — it covers assembling an extended
> corpus, registering PDFs, running all three passes, calibrating figures, QC
> review, batch scaling and troubleshooting. The quick version is below.

Helper scripts (in `scripts/`):

| Script | Purpose |
|---|---|
| `fetch_ntrs.py` | download source PDFs from NTRS by accession id |
| `register_pdfs.py` | scan `data/raw/<program>/` and add entries to `config/corpus.yaml` |
| `run_all.py` | run all three passes across the corpus (or one program) |

Figure calibration (Pass 3, stage 2) lives in `notebooks/calibrate_figure.py`
(jupytext script, pairs with `notebooks/figure_calibration.ipynb`).

Place PDFs under `data/raw/<program>/` and register them in `config/corpus.yaml`.

```bash
# Pass 1 – catalogue the whole corpus
ntrs-extract catalogue

# Pass 2 – extract tables (all, one program, or one document)
ntrs-extract tables --program apollo
ntrs-extract tables --doc A14

# Pass 3 – digitise data figures (uncalibrated trace + overlays for review)
ntrs-extract figures --program mercury

# Everything for one document
ntrs-extract all --doc MR4
```

(Equivalently `python -m ntrs_extractor.cli <cmd>`.)

### Calibrating a figure to real units

```python
from ntrs_extractor import figures
pdf = "data/raw/apollo/Medical_Results_of_Apollo_14.pdf"

# 1) auto-trace to find the plot rectangle in pixels
r = figures.digitise_figure(pdf, pdf_page=4)
x0, y0, x1, y1 = r.plot_bbox_px

# 2) read four tick references off the axis and calibrate
cal = figures.CalibrationSpec(x_px=(x0, x1), x_val=(1, 10),      # minutes
                              y_px=(y1, y0), y_val=(50, 120))     # bpm
r2 = figures.digitise_figure(pdf, pdf_page=4, calibration=cal)
figures.save_figure(r2, "data/outputs/apollo/figures/A14-F-001.csv",
                    overlay_png="qc/apollo/overlays/A14-F-001.png")
```

## Directory tree

```
ntrs-extractor/
├── README.md, LICENSE, pyproject.toml, requirements.txt, .gitignore
├── .github/workflows/ci.yml          # lint + pytest on 3.10–3.12
├── config/
│   └── corpus.yaml                   # registry: program → documents (source of truth)
├── scripts/
│   ├── register_pdfs.py              # bulk-register PDFs into corpus.yaml
│   ├── fetch_ntrs.py                 # download source PDFs by NTRS accession id
│   └── run_all.py                    # run all passes across the corpus
├── src/ntrs_extractor/
│   ├── __init__.py
│   ├── schema.py                     # catalogue columns, dataclasses, program registry
│   ├── config.py                     # corpus.yaml loader
│   ├── pdf_utils.py                  # text/words/printed-page + rasterisation
│   ├── catalogue.py                  # PASS 1 detection
│   ├── catalogue_io.py               # PASS 1 workbook read/write (A/B sub-catalogues)
│   ├── tables.py                     # PASS 2 table reader
│   ├── figures.py                    # PASS 3 figure digitiser
│   ├── qc.py                         # QC scoring + report writer (shared)
│   └── cli.py                        # orchestrator
├── scripts/
│   ├── fetch_ntrs.py                 # download PDFs from NTRS by accession id
│   ├── register_pdfs.py              # bulk-add PDFs to corpus.yaml
│   └── run_all.py                    # run all passes across the corpus
├── catalogues/<program>/             # *_catalogue.xlsx (Pass 1, committed)
├── data/
│   ├── raw/<program>/                # source PDFs (git-ignored; use DVC/releases)
│   ├── interim/                      # scratch
│   └── outputs/<program>/{tables,figures}/   # extracted CSVs (git-ignored)
├── qc/<program>/                     # QC workbooks + overlays/ (git-ignored)
├── notebooks/
│   ├── calibrate_figure.py           # Pass 3 calibration walkthrough (jupytext .py)
│   └── figure_calibration.ipynb      # same, as a Jupyter notebook
├── docs/
│   ├── RUNBOOK.md                    # step-by-step operations guide (start here)
│   └── METHOD.md                     # design notes / rationale
└── tests/                            # pytest (synthetic PDFs, no binary fixtures)
```

### What to commit vs. ignore
- **Commit**: all code, `config/corpus.yaml`, and the curated `catalogues/*.xlsx`.
- **Ignore** (regenerate or store via DVC / release assets): raw PDFs and every
  derived artefact under `data/outputs/` and `qc/`. This keeps the repo small and
  avoids re-distributing source scans.

## QC & error assessment

- **Pass 1**: `detection_confidence` per item; ambiguous captions default to amber
  for human confirmation; the `reviewer` column records sign-off.
- **Pass 2**: `qc_score` from empty-ratio, raggedness, size and numeric density;
  method used is logged; anything < 0.45 is red.
- **Pass 3**: coverage/density score; **uncalibrated results can never be green**;
  every figure gets a visual overlay for review.

## Adding a program / document
Add an entry under the relevant program in `config/corpus.yaml`, drop the PDF into
`data/raw/<program>/`, and re-run the passes. New programs only need a slug added
to `schema.PROGRAMS`.
```
