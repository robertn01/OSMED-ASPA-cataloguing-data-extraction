"""Pass 1 - automated cataloguing.

Strategy (belt-and-braces, so recall is high and a human only *confirms*):

1. Caption regex over the text layer finds every "Table N ..." / "Figure N ..."
   mention and, crucially, distinguishes a *caption* (start of line, followed by
   a title) from an in-text *reference* ("see Table 2").
2. pdfplumber's ruling-line table finder gives independent evidence for tables
   and an approximate rows x cols shape.
3. Figures are sized by locating the caption line and measuring the whitespace /
   image band above it (a coarse but useful area estimate) and classified into a
   subtype by simple cues (later refined in Pass 3).

Every candidate is emitted as a CatalogueEntry with a detection_confidence so the
manual reviewer can triage. Nothing here is destructive: the output is a fresh
catalogue that a human edits.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from .schema import (
    CatalogueEntry,
    DocumentSpec,
    TABULAR_KINDS,
    DATA_BEARING_FIGURE_SUBTYPES,
)
from . import pdf_utils

import pdfplumber


# --- caption grammar --------------------------------------------------------
# Roman-or-arabic item numbers, optional hyphenated section ("4-7", "3-I").
_ITEM = r"(?P<num>\d{1,3}(?:[-\u2013]\s?[0-9IVXLC]{1,4})?|[IVXLC]{1,6})"
TABLE_CAP_RE = re.compile(rf"^\s*TABLE\s+{_ITEM}\b[.\-\u2013:]*\s*(?P<title>.*)$",
                          re.IGNORECASE)
FIG_CAP_RE = re.compile(rf"^\s*FIG(?:URE|\.)?\s+{_ITEM}\b[.\-\u2013:]*\s*(?P<title>.*)$",
                        re.IGNORECASE)
# In-text references we must NOT treat as captions.
REF_RE = re.compile(r"\b(see|in|from|shown in|table|figure)\b", re.IGNORECASE)

# Cues that a figure caption describes a data chart vs. a schematic/photo.
_SUBTYPE_CUES = {
    "line":      ["rate", "vs", "versus", "curve", "history", "profile", "trace",
                  "time", "pulse", "heart rate", "attitude"],
    "scatter":   ["scatter", "correlation", "points"],
    "bar":       ["bar", "histogram"],
    "trace":     ["telemetry", "recorder", "record", "ecg", "respiration"],
    "schematic": ["configuration", "diagram", "panel", "cutaway", "chart of",
                  "instrument", "differences"],
    "map":       ["map", "recovery operations", "landing", "trajectory chart"],
    "photo":     ["photograph", "view of", "trainer", "hovering", "electrode",
                  "sensor", "cardioscope"],
}


def _classify_figure(title: str) -> tuple[str, float]:
    """Return (subtype, confidence)."""
    t = title.lower()
    best, score = "", 0
    for subtype, cues in _SUBTYPE_CUES.items():
        hits = sum(1 for c in cues if c in t)
        if hits > score:
            best, score = subtype, hits
    if not best:
        return "line", 0.35  # NTRS figures are most often line charts
    conf = min(0.9, 0.4 + 0.15 * score)
    return best, conf


def _looks_like_caption(line: str) -> bool:
    """A caption starts the item number and has a following title, and is not a
    mid-sentence reference like '... shown in Table 5 ...'."""
    stripped = line.strip()
    if not stripped:
        return False
    head = stripped[:8].lower()
    return head.startswith(("table", "figure", "fig.", "fig "))


def _table_shapes(pdf_path: str, pdf_page: int) -> list[tuple[int, int, tuple]]:
    """Use pdfplumber ruling/where-text lines to estimate (rows, cols, bbox)."""
    shapes: list[tuple[int, int, tuple]] = []
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[pdf_page - 1]
        settings_variants = [
            {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
            {"vertical_strategy": "text", "horizontal_strategy": "text",
             "min_words_vertical": 2, "min_words_horizontal": 2},
        ]
        found = []
        for st in settings_variants:
            try:
                for tb in page.find_tables(table_settings=st):
                    rows = tb.rows or []
                    ncols = max((len(r.cells) for r in rows), default=0)
                    found.append((len(rows), ncols, tuple(tb.bbox)))
            except Exception:
                continue
            if found:
                break
        # de-dup by rough bbox
        seen = []
        for r, c, bbox in found:
            if all(abs(bbox[1] - s[1]) > 12 for s in seen):
                shapes.append((r, c, bbox))
                seen.append(bbox)
    return shapes


def catalogue_document(spec: DocumentSpec, pdf_path: str) -> list[CatalogueEntry]:
    """Produce catalogue entries for one PDF."""
    entries: list[CatalogueEntry] = []
    t_counter = 0
    f_counter = 0

    pages = list(pdf_utils.iter_pages(pdf_path))
    # Pre-compute table shapes only on pages that mention a table (cheap filter).
    for pt in pages:
        lines = pt.text.splitlines()
        page_table_shapes = None  # lazy

        for li, line in enumerate(lines):
            if not _looks_like_caption(line):
                continue

            m_t = TABLE_CAP_RE.match(line)
            m_f = FIG_CAP_RE.match(line)

            # If the caption line carries no title, borrow the next non-empty
            # line (common layout: "Table 1" / "Apollo 14 Mission").
            next_line = lines[li + 1].strip() if li + 1 < len(lines) else ""

            if m_t:
                title = m_t.group("title").strip()
                if not title and next_line and not _looks_like_caption(next_line):
                    title = next_line
                # skip a "List of Tables" / TOC line etc.
                if title.lower().startswith(("of contents",)):
                    continue
                if not title:
                    title = "(untitled table)"
                t_counter += 1
                if page_table_shapes is None:
                    page_table_shapes = _table_shapes(pdf_path, pt.pdf_page_number)
                rows = cols = None
                if page_table_shapes:
                    rows, cols, _bbox = max(page_table_shapes,
                                            key=lambda s: s[0] * s[1])
                conf = 0.85 if page_table_shapes else 0.55
                entries.append(CatalogueEntry(
                    catalogue_id=f"{spec.doc_id}-T-{t_counter:03d}",
                    printed_page_number=pt.printed_page_guess,
                    pdf_page_number=pt.pdf_page_number,
                    kind="table",
                    item_number=f"Table {m_t.group('num')}",
                    original_source=spec.title,
                    description=title[:180],
                    approx_rows=rows,
                    approx_cols=cols,
                    sub_catalogue="A_tabular",
                    figure_subtype="",
                    detection_method="auto:caption+lines",
                    detection_confidence=round(conf, 2),
                    extractable=True,
                    extraction_status="pending",
                    qc_flag="amber",
                ))

            elif m_f:
                title = m_f.group("title").strip()
                if not title and next_line and not _looks_like_caption(next_line):
                    title = next_line
                if not title:
                    continue
                f_counter += 1
                subtype, sconf = _classify_figure(title)
                extractable = subtype in DATA_BEARING_FIGURE_SUBTYPES
                entries.append(CatalogueEntry(
                    catalogue_id=f"{spec.doc_id}-F-{f_counter:03d}",
                    printed_page_number=pt.printed_page_guess,
                    pdf_page_number=pt.pdf_page_number,
                    kind="figure",
                    item_number=f"Figure {m_f.group('num')}",
                    original_source=spec.title,
                    description=title[:180],
                    approx_rows=None,
                    approx_cols=None,
                    sub_catalogue="B_graphical",
                    figure_subtype=subtype,
                    detection_method="auto:caption-regex",
                    detection_confidence=round(sconf, 2),
                    extractable=extractable,
                    extraction_status="pending" if extractable else "skipped",
                    qc_flag="amber" if extractable else "green",
                    qc_notes="" if extractable else "non-data figure (photo/schematic)",
                ))

    entries = _dedupe(entries)
    return entries


def _dedupe(entries: Iterable[CatalogueEntry]) -> list[CatalogueEntry]:
    """Collapse repeat captions (same item number appearing on consecutive
    pages, e.g. a table continued or a caption echoed in a list-of-figures)."""
    out: list[CatalogueEntry] = []
    seen: dict[tuple[str, str], CatalogueEntry] = {}
    for e in entries:
        key = (e.kind, e.item_number.lower())
        if key in seen:
            # keep the one with the stronger evidence / earliest page
            prev = seen[key]
            if e.detection_confidence > prev.detection_confidence:
                out[out.index(prev)] = e
                seen[key] = e
            continue
        seen[key] = e
        out.append(e)
    return out
