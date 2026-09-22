"""Thin wrappers over pdfplumber for page text, words and rasterisation.

We standardise on pdfplumber because it ships pure-python and exposes both the
text layer (for caption detection) and a rasteriser (for figure work). PyMuPDF
is used opportunistically if available (faster raster), else pdfplumber's
``to_image`` is used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

try:  # optional, faster raster if present
    import fitz  # type: ignore
    _HAS_FITZ = True
except Exception:  # pragma: no cover
    _HAS_FITZ = False

import pdfplumber


PRINTED_PAGE_RE = re.compile(
    r"^\s*(?:page\s*)?(?P<num>[ivxlcdm]{1,7}|\d{1,4})\s*$", re.IGNORECASE
)


@dataclass
class PageText:
    pdf_page_number: int          # 1-based
    text: str
    words: list                   # pdfplumber word dicts
    width: float
    height: float
    printed_page_guess: str = ""


def iter_pages(pdf_path: str) -> Iterator[PageText]:
    """Yield text + geometry for every page."""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=True) or []
            text = page.extract_text() or ""
            yield PageText(
                pdf_page_number=i,
                text=text,
                words=words,
                width=float(page.width),
                height=float(page.height),
                printed_page_guess=_guess_printed_page(page, text),
            )


def _guess_printed_page(page, text: str) -> str:
    """Best-effort read of the page number printed in header/footer.

    We look at words in the top 8% and bottom 8% of the page and keep any that
    look like a bare page number (arabic or roman).
    """
    h = float(page.height)
    band = 0.08 * h
    candidates: list[str] = []
    for w in page.extract_words() or []:
        top, bottom = float(w["top"]), float(w["bottom"])
        if top <= band or bottom >= h - band:
            m = PRINTED_PAGE_RE.match(w["text"])
            if m:
                candidates.append(m.group("num"))
    # Prefer footer-most numeric candidate; fall back to any.
    numeric = [c for c in candidates if c.isdigit()]
    if numeric:
        return numeric[-1]
    if candidates:
        return candidates[-1]
    return ""


def page_count(pdf_path: str) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def render_page(pdf_path: str, pdf_page_number: int, dpi: int = 300) -> np.ndarray:
    """Return an RGB uint8 array for one page (1-based index)."""
    if _HAS_FITZ:
        doc = fitz.open(pdf_path)
        page = doc[pdf_page_number - 1]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        return arr[:, :, :3].copy()
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[pdf_page_number - 1]
        pil = page.to_image(resolution=dpi).original.convert("RGB")
        return np.asarray(pil)


def crop_bbox(pdf_path: str, pdf_page_number: int, bbox, dpi: int = 300) -> np.ndarray:
    """Rasterise a bbox (x0, top, x1, bottom) in PDF points to an RGB array."""
    scale = dpi / 72.0
    img = render_page(pdf_path, pdf_page_number, dpi=dpi)
    x0, top, x1, bottom = bbox
    x0i, x1i = int(x0 * scale), int(x1 * scale)
    y0i, y1i = int(top * scale), int(bottom * scale)
    h, w = img.shape[:2]
    x0i, x1i = max(0, x0i), min(w, x1i)
    y0i, y1i = max(0, y0i), min(h, y1i)
    return img[y0i:y1i, x0i:x1i].copy()
