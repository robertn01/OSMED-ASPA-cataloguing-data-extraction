# Method notes

## Why three passes, and why manual-in-the-loop
Historical NTRS PDFs are microfilm scans (1960s–70s): skewed baselines, broken
glyphs, mixed roman/arabic numbering, and figures that are line drawings rather
than born-digital vectors. Fully unattended extraction would silently emit wrong
numbers. The design therefore front-loads **recall** (catch everything) and defers
**precision** to a cheap human confirmation step, with QC scores routing attention.

## Pass 1 — cataloguing
- **Caption vs reference.** A caption starts a line with the item word and item
  number and is followed by a title; an in-text mention (`shown in Table 5`) is
  ignored. Titles that spill onto the next line are stitched back.
- **Shape estimate.** `approx_rows × approx_cols` comes from `pdfplumber` table
  finders. It is a *volume gauge*, not ground truth.
- **Figure subtyping.** Keyword cues split data-bearing charts (line/scatter/bar/
  trace) from schematics/photos/maps so Pass 3 only spends effort where data can
  be recovered.

## Pass 2 — tables
Ordered fallback (lattice → stream → pdfplumber) with a single QC score so the
best of several extractions wins automatically. Numeric-density is part of the
score because NTRS data tables are number-heavy; a high-text block scoring low is
usually a mis-detected paragraph.

## Pass 3 — figures
- **Axis detection** via longest dark horizontal/vertical runs is robust to noise
  and needs no training data.
- **Calibration** is deliberately explicit (`CalibrationSpec`, 2 refs/axis, linear
  or log). This is auditable and works even when tick OCR fails. Optional
  `pytesseract` can *suggest* tick values but never sets green QC on its own.
- **Series separation** clusters ink pixels per column; adequate for the common
  1–2 curve charts. Dense multi-series plots should be flagged for manual tracing
  (e.g. WebPlotDigitizer) — the catalogue's `qc_notes` is the place to record that.

## Extending
- New extractor backends slot into `tables._from_*` / `figures._trace_curves`.
- New programs: add to `schema.PROGRAMS` and `config/corpus.yaml`.
- Batch scale: the CLI already iterates program → document; wrap in GNU parallel
  or a CI matrix for large corpora, and store outputs via DVC.
