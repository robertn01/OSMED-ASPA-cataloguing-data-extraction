# RUNBOOK — Cataloguing & data extraction on an extended corpus

This is the operational, step-by-step guide for going from *a folder of NTRS PDFs*
to *reviewed CSVs of every table and figure*, at any scale (2 documents or 200).

It assumes the package layout described in `README.md`. Every command is run from
the repository root (`ntrs-extractor/`) unless stated otherwise.

**Mental model.** Three passes, each with a human checkpoint:

```
   PDFs ──► Pass 1: CATALOGUE ──►[review]──► Pass 2: TABLES  ──►[QC review]──► CSVs
                                     │
                                     └──────► Pass 3: FIGURES ──►[calibrate+QC]──► CSVs
```

You always run **Pass 1 for the whole corpus first**, confirm the catalogue, then
run Pass 2 and Pass 3 which read that catalogue to know *what* and *where* to
extract.

---

## 0. One-time setup

### 0.1 Install
```bash
git clone <your-fork-url> ntrs-extractor
cd ntrs-extractor
python -m venv .venv && source .venv/bin/activate     # optional but recommended
pip install -e ".[dev]"                                # core + test deps
```

### 0.2 System dependency for tables (ghostscript)
`camelot`'s *lattice* mode (ruled tables) needs Ghostscript:
```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y ghostscript
# macOS
brew install ghostscript
```
Without it, Pass 2 silently falls back to *stream* + `pdfplumber` (lower recall on
ruled tables). Check it is visible:
```bash
gs --version
```

### 0.3 Optional accelerators
```bash
pip install -e ".[fast]"    # PyMuPDF: faster page rasterisation for Pass 3
pip install -e ".[ocr]"     # pytesseract: suggests axis tick values in Pass 3
# OCR also needs the system binary:  apt-get install tesseract-ocr
```

### 0.4 Verify the toolchain
```bash
pytest -q                   # 5 tests, ~2s, uses synthetic PDFs (no network)
```
A green run confirms all three passes work on your machine before you touch real
data.

---

## 1. Assemble the corpus (the PDFs)

Organise **program-by-program**. Each program is a folder under `data/raw/`:

```
data/raw/
├── mercury/
├── gemini/
├── apollo/
└── skylab/
```

You have three ways to populate them; use whichever fits.

**A. Manual drop.** Download PDFs from https://ntrs.nasa.gov and drop them into the
right program folder. Keep original filenames or rename to something clean.

**B. Scripted download by NTRS accession id** (`scripts/fetch_ntrs.py`). The
accession id is the number in an `ntrs.nasa.gov/citations/<id>` URL.
```bash
pip install requests
python scripts/fetch_ntrs.py --program apollo 19710021329 19720005957
# or from a list
python scripts/fetch_ntrs.py --program gemini --ids-file docs/gemini_ids.txt
```

**C. Already have a pile of PDFs.** Just move them into the program folders.

> **Storage note.** `data/raw/` and all derived outputs are **git-ignored** by
> design (see `.gitignore`). Do not commit source scans. For team sharing use DVC,
> a shared drive, or GitHub release assets. Only *code* and the curated
> `catalogues/*.xlsx` belong in git.

---

## 2. Register the corpus (`config/corpus.yaml`)

The pipeline discovers work from `config/corpus.yaml`, not from the filesystem, so
every PDF must have a registry entry. For a large corpus, auto-generate them:

```bash
# scan every program folder and append entries for any unregistered PDF
python scripts/register_pdfs.py

# preview first, or restrict to one program
python scripts/register_pdfs.py --program gemini --dry-run
```

This **never overwrites** existing entries, so it is safe to re-run each time you
add PDFs. It derives a `doc_id` (e.g. `GT7`) and a placeholder `title` from the
filename.

**Then hand-refine** each new entry (2 minutes each):
```yaml
programs:
  gemini:
    label: Project Gemini
    id_prefix: GT
    documents:
      - doc_id: GT7                     # short, stable key -> catalogue ids GT7-T-001 ...
        pdf_filename: gemini_7_medical_results.pdf
        title: "Gemini 7 Medical Results, NASA MSC, 1966"   # for the 'original_source' column
        ntrs_id: "19660005960"          # optional provenance
        printed_offset: 4               # pdf_page = printed_page + offset (best-effort)
        notes: "14-day mission; cardiovascular + bone-density tables."
```
- `doc_id` is the **only** field the pipeline strictly needs to be clean — it
  prefixes every catalogue id and output filename.
- `printed_offset` is only used to sanity-check auto-detected page numbers; leave
  it `0` if unsure.

Registering a brand-new **program** (e.g. Skylab) additionally needs its slug in
`src/ntrs_extractor/schema.PROGRAMS` (one line) so id prefixes and folders resolve.
`mercury`, `gemini`, `apollo`, `skylab` are already there.

Confirm the registry parses:
```bash
python -c "from ntrs_extractor.config import load_corpus; \
c=load_corpus('config/corpus.yaml'); \
print({k:[d.doc_id for d in v] for k,v in c.items()})"
```

---

## 3. Pass 1 — Catalogue (automated pass, then confirm)

### 3.1 Run the automated cataloguing pass
```bash
# whole corpus
ntrs-extract catalogue
# or scope down
ntrs-extract catalogue --program apollo
ntrs-extract catalogue --doc GT7
```
Output: one workbook per document at
`catalogues/<program>/<doc_id>_catalogue.xlsx`, with sheets:
- **Summary** — counts by kind / sub-catalogue / QC flag;
- **A_tabular** — every table;
- **B_graphical** — every figure / non-table visualisation;
- **All** — combined view.

Console shows a per-document tally, e.g. `[catalogue] A14: 2 tables, 1 figures`.

### 3.2 Confirm the catalogue (the human checkpoint)
Open each workbook and scan the `A_tabular` and `B_graphical` sheets. For each row
check/adjust:

| Column | What to verify |
|---|---|
| `detection_confidence` | low values (< 0.6) first — likely mis-detections |
| `item_number`, `description` | matches the printed caption |
| `printed_page_number` / `pdf_page_number` | correct page (auto page-number reading can slip on messy footers) |
| `approx_rows` / `approx_cols` | rough data-volume sanity check |
| `figure_subtype` | is a `schematic`/`photo`/`map` mis-tagged as `line`? fix so Pass 3 skips/keeps correctly |
| `extractable` | set `FALSE` for anything with no recoverable data |
| `reviewer` | put your initials to mark the row confirmed |

Practical tips for a big corpus:
- Use the sheet's **auto-filter** to sort by `detection_confidence` ascending and
  review the weakest first.
- Rows with the same `item_number` appearing twice usually mean a caption echoed in
  a *List of Figures/Tables*; delete the TOC duplicate (keep the one on the real
  page).
- If the tool **missed** an item, add a row by hand: minimally
  `catalogue_id`, `pdf_page_number`, `kind`, `item_number`, `sub_catalogue`
  (`A_tabular`/`B_graphical`), and for figures `figure_subtype`.

The confirmed `catalogues/*.xlsx` is the one artefact you **do** commit to git — it
is the shared source of truth for Passes 2 and 3.

---

## 4. Pass 2 — Table extraction

### 4.1 Run
```bash
ntrs-extract tables               # whole corpus
ntrs-extract tables --program apollo
ntrs-extract tables --doc A14
```
For each row in the `A_tabular` sheet the tool tries `camelot lattice → camelot
stream → pdfplumber` and keeps the best by QC score. It writes:
- `data/outputs/<program>/tables/<catalogue_id>.csv` (one file per table);
- `qc/<program>/<doc_id>_tables_qc.xlsx` (QC record for every table).

Console prints a live line per table:
```
[tables] A14-T-002 green score=0.838 (camelot:lattice)
```

### 4.2 QC review
Open `qc/<program>/<doc_id>_tables_qc.xlsx`. Triage by flag:
- **green** (≥ 0.75): spot-check only.
- **amber** (0.45–0.75): open the CSV against the PDF; common issues are a merged
  header row or a split multi-line cell.
- **red** (< 0.45) or missing: extractor struggled. Options, in order:
  1. install Ghostscript (fixes many ruled-table cases);
  2. re-run just that doc after fixing;
  3. for a stubborn table, transcribe by hand into the CSV — the catalogue already
     tells you exactly which table and page.

`reason` in the QC sheet explains the score (`empty_ratio=…`, `ragged rows`,
`single column`).

---

## 5. Pass 3 — Figure extraction (two stages)

Figures are the hard pass. It runs in two stages: an **auto-trace** (no human
input) then **calibration** (four numbers per chart) to get real units.

### 5.1 Stage 1 — auto-trace + overlays
```bash
ntrs-extract figures              # whole corpus
ntrs-extract figures --program mercury
ntrs-extract figures --doc A14
```
Only figures whose `figure_subtype` is data-bearing (`line`, `scatter`, `bar`,
`trace`) are processed; schematics/photos/maps are skipped. For each it writes:
- `data/outputs/<program>/figures/<catalogue_id>.csv` — traced series, in **pixel**
  space at this stage (`series, x, y`);
- `qc/<program>/overlays/<catalogue_id>.png` — the original figure with recovered
  points drawn on top;
- `qc/<program>/<doc_id>_figures_qc.xlsx` — QC records.

**Review the overlays first.** Open each PNG: the coloured dots should sit on the
plotted lines. If a curve is missed or a schematic slipped through, fix
`figure_subtype`/`extractable` in the catalogue and re-run. Uncalibrated results
are **capped at amber** on purpose — pixel coordinates are not yet data.

### 5.2 Stage 2 — calibrate to real units
For each good trace, read four tick references off the axes and calibrate. Do this
in a short script or the provided notebook (`notebooks/`):

```python
from ntrs_extractor import figures

pdf  = "data/raw/apollo/Medical_Results_of_Apollo_14.pdf"
page = 4      # pdf_page_number from the catalogue row

# 1) auto-trace to get the plot rectangle in pixels
r = figures.digitise_figure(pdf, page)
x0, y0, x1, y1 = r.plot_bbox_px      # (left, top, right, bottom)

# 2) read tick labels off the axes and map pixel -> value.
#    Provide TWO x ticks and TWO y ticks. Image y grows downward, so the
#    bottom tick (y1) is the smaller data value.
cal = figures.CalibrationSpec(
    x_px=(x0, x1), x_val=(1, 10),        # e.g. 1 min at left, 10 min at right
    y_px=(y1, y0), y_val=(50, 120),      # 50 bpm at bottom, 120 bpm at top
    x_log=False, y_log=False,            # set True for log axes
)

# 3) re-digitise with calibration and save data-space CSV + overlay
r2 = figures.digitise_figure(pdf, page, calibration=cal)
figures.save_figure(
    r2,
    "data/outputs/apollo/figures/A14-F-001.csv",
    overlay_png="qc/apollo/overlays/A14-F-001.png",
)
print("calibrated:", r2.calibrated, "points:", r2.n_points)
```

Tips:
- Pick tick references **far apart** (e.g. first and last labelled tick) to
  minimise error.
- For multi-curve charts the tool emits `series_1`, `series_2`; rename them to
  meaningful labels (e.g. `preflight`, `postflight`) in the CSV.
- Dense (>2 curves) or heavily overlapping plots: flag in the catalogue's
  `qc_notes` and trace manually (e.g. WebPlotDigitizer). The catalogue tells you
  which figures those are.

After calibration, update the catalogue row: set `extraction_status = done`,
`output_path`, and bump `qc_flag` to `green` once you're satisfied with the
overlay.

---

## 6. Run everything at once

For a full sweep (all three passes, whole corpus or one program):
```bash
python scripts/run_all.py                    # every program
python scripts/run_all.py --program apollo
python scripts/run_all.py --pass catalogue   # just Pass 1 across the corpus
```
(Calibration in Pass 3 still happens per-figure afterwards — the sweep produces the
uncalibrated traces + overlays for you to calibrate.)

---

## 7. Scaling to a large corpus

- **Parallelism.** The passes are independent per document, so fan out with GNU
  parallel or a CI matrix:
  ```bash
  # example: catalogue every document in parallel
  python -c "from ntrs_extractor.config import load_corpus as L; \
  [print(d.doc_id) for v in L('config/corpus.yaml').values() for d in v]" \
    | parallel -j4 ntrs-extract catalogue --doc {}
  ```
- **Incremental work.** Re-running a pass re-does everything in scope; to redo one
  document use `--doc`. Outputs are overwritten deterministically.
- **CI.** `.github/workflows/ci.yml` installs Ghostscript, the package, and runs
  the tests on push/PR across Python 3.10–3.12. Extend it with a nightly job that
  re-runs `catalogue` on the registered corpus if you want drift detection.
- **Provenance.** Keep `ntrs_id` populated so every extracted CSV can be traced
  back to its NTRS source; the `original_source` column carries the human title.

---

## 8. Outputs map (where everything lands)

```
catalogues/<program>/<doc_id>_catalogue.xlsx        # Pass 1 (COMMIT after review)
data/outputs/<program>/tables/<catalogue_id>.csv    # Pass 2
data/outputs/<program>/figures/<catalogue_id>.csv   # Pass 3 (calibrated)
qc/<program>/<doc_id>_tables_qc.xlsx                 # Pass 2 QC
qc/<program>/<doc_id>_figures_qc.xlsx               # Pass 3 QC
qc/<program>/overlays/<catalogue_id>.png            # Pass 3 visual QC
```

---

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `[skip] missing PDF` | filename in `corpus.yaml` doesn't match the file in `data/raw/<program>/`. Fix the name. |
| `[skip] need PDF+catalogue` on Pass 2/3 | run Pass 1 for that doc first. |
| Pass 2 all *stream*, ruled tables ragged | Ghostscript not installed → install it, re-run. |
| Wrong `printed_page_number` in catalogue | messy footer; correct the cell manually (Pass 1 is a *draft* to confirm). |
| A photo/schematic got a `line` subtype | fix `figure_subtype` in the catalogue so Pass 3 skips it. |
| Figure overlay dots off the curve | crop tighter (pass a `bbox_pts` to `digitise_figure`) or check the plot-rect detection; recalibrate. |
| Figure stuck amber after calibration | expected only if trace coverage is low; inspect overlay, adjust crop, re-run. |
| `PyYAML required for merge` | `pip install pyyaml` (or edit `corpus.yaml` by hand). |
| New program not found | add its slug to `schema.PROGRAMS`. |

---

## 10. Quick reference (copy-paste)

```bash
# setup
pip install -e ".[dev]" && sudo apt-get install -y ghostscript && pytest -q

# corpus in, registered
python scripts/fetch_ntrs.py --program apollo <id1> <id2>   # optional
python scripts/register_pdfs.py                             # then edit corpus.yaml

# three passes
ntrs-extract catalogue            # then review catalogues/*.xlsx
ntrs-extract tables               # then review qc/*_tables_qc.xlsx
ntrs-extract figures              # then review overlays, calibrate, review qc

# or all at once
python scripts/run_all.py
```
