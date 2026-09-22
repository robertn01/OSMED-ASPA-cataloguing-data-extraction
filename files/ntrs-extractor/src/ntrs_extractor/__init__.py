"""NTRS Extractor: a three-pass ML/CV pipeline for cataloguing and extracting
tabular and figure data from historical NASA Technical Reports (NTRS) PDFs.

Passes
------
1. catalogue : locate every table / figure and write a per-document catalogue.
2. tables    : read tables into tidy CSV/XLSX with confidence + QC metrics.
3. figures   : digitise line/scatter charts into (x, y) series with QC overlays.
"""

__version__ = "0.1.0"
__all__ = ["catalogue", "tables", "figures", "qc", "schema", "pdf_utils"]
