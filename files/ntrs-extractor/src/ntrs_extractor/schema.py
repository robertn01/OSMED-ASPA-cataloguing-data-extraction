"""Canonical schemas shared by every pass.

The catalogue columns mirror the OSMED/ASPA corpus-catalogue template:
    printed page number, PDF page number, table-or-figure, table/figure number,
    original source, brief description, approximate rows x columns.

Extra machine-generated bookkeeping columns are appended so the manual (Pass 1)
and automated (Passes 2-3) views can live in one sheet without clobbering the
human-curated fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Catalogue column order (Pass 1 template, followed by automation columns).
# ---------------------------------------------------------------------------
CATALOGUE_COLUMNS: list[str] = [
    # ---- human-facing template fields (match the provided EXAMPLE workbook) ----
    "catalogue_id",          # stable key, e.g. MR4-T-001 / A14-F-003
    "printed_page_number",   # page number printed on the page ("iv", "3", ...)
    "pdf_page_number",       # 1-based index of the page inside the PDF
    "kind",                  # "table" | "figure"
    "item_number",           # "Table 2", "Figure 4-7", "Table 3-I"
    "original_source",       # source document / report title
    "description",           # brief human description of contents
    "approx_rows",           # approximate data rows
    "approx_cols",           # approximate data columns
    # ---- automation / provenance fields -------------------------------------
    "sub_catalogue",         # "A_tabular" | "B_graphical"
    "figure_subtype",        # line | scatter | bar | schematic | photo | trace | ""
    "detection_method",      # "manual" | "auto:pdfplumber" | "auto:caption-regex"
    "detection_confidence",  # 0-1 float
    "extractable",           # bool: is data recoverable by Pass 2/3?
    "extraction_status",     # "pending"|"done"|"failed"|"skipped"|"needs_review"
    "output_path",           # relative path to extracted CSV / series file
    "qc_flag",               # "green"|"amber"|"red"
    "qc_notes",              # free text
    "reviewer",              # human sign-off initials
]

# Which kinds/subtypes go into which sub-catalogue.
TABULAR_KINDS = {"table"}
GRAPHICAL_SUBTYPES = {"line", "scatter", "bar", "schematic", "photo", "trace", "map"}

# Figure subtypes that carry recoverable quantitative data (Pass 3 targets).
DATA_BEARING_FIGURE_SUBTYPES = {"line", "scatter", "bar", "trace"}


@dataclass
class CatalogueEntry:
    """One row of the catalogue."""
    catalogue_id: str
    printed_page_number: str = ""
    pdf_page_number: Optional[int] = None
    kind: str = ""                       # table | figure
    item_number: str = ""
    original_source: str = ""
    description: str = ""
    approx_rows: Optional[int] = None
    approx_cols: Optional[int] = None
    sub_catalogue: str = ""
    figure_subtype: str = ""
    detection_method: str = ""
    detection_confidence: float = 0.0
    extractable: bool = True
    extraction_status: str = "pending"
    output_path: str = ""
    qc_flag: str = "amber"
    qc_notes: str = ""
    reviewer: str = ""

    def as_row(self) -> dict:
        d = asdict(self)
        return {c: d.get(c, "") for c in CATALOGUE_COLUMNS}


@dataclass
class Program:
    """A space-program workspace (Mercury, Gemini, Apollo, ...)."""
    key: str          # short slug used in folder names, e.g. "mercury"
    label: str        # human label, e.g. "Project Mercury"
    id_prefix: str    # catalogue-id prefix, e.g. "MR"

    @property
    def raw_dir(self) -> str:
        return f"data/raw/{self.key}"

    @property
    def catalogue_dir(self) -> str:
        return f"catalogues/{self.key}"

    @property
    def output_dir(self) -> str:
        return f"data/outputs/{self.key}"

    @property
    def qc_dir(self) -> str:
        return f"qc/{self.key}"


# Registry of programs known to the corpus. Extend as new programs are added.
PROGRAMS: dict[str, Program] = {
    "mercury": Program("mercury", "Project Mercury", "MR"),
    "gemini":  Program("gemini",  "Project Gemini",  "GT"),
    "apollo":  Program("apollo",  "Project Apollo",  "AP"),
    "skylab":  Program("skylab",  "Skylab",          "SL"),
}


@dataclass
class DocumentSpec:
    """A single PDF within a program."""
    doc_id: str                 # e.g. "MR4", "A14"
    program_key: str            # "mercury"
    pdf_filename: str           # basename under the program raw dir
    title: str                  # human title / original source string
    ntrs_id: str = ""           # NTRS accession id if known
    printed_offset: int = 0     # pdf_page = printed_page + offset (best-effort)
    notes: str = ""
