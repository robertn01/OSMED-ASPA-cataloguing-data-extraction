"""Pass 2 - automated table reader.

For each catalogued table we try several extractors in order of reliability and
keep the best result by a QC score:

    1. camelot 'lattice'  - best when the table has ruling lines.
    2. camelot 'stream'   - whitespace-aligned tables (many NTRS tables).
    3. pdfplumber lines   - fallback using detected ruling lines.

QC score rewards rectangular, densely-populated grids and penalises ragged rows,
empty cells and single-column results. Every extracted table is written to CSV
and accompanied by a QC record (see qc.table_qc).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

import pdfplumber

try:
    import camelot  # type: ignore
    _HAS_CAMELOT = True
except Exception:  # pragma: no cover
    _HAS_CAMELOT = False


@dataclass
class TableResult:
    df: pd.DataFrame
    method: str
    qc_score: float
    n_rows: int
    n_cols: int
    empty_ratio: float
    ragged: bool
    notes: str = ""


_NUM_RE = re.compile(r"^[\s(]*[-+\u2212]?[\d,]*\.?\d+[)\s%]*$")


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.replace({r"^\s*$": np.nan}, regex=True)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.apply(lambda c: c.map(lambda v: str(v).strip() if pd.notna(v) else v))
    return df.reset_index(drop=True)


def _empty_ratio(df: pd.DataFrame) -> float:
    if df.size == 0:
        return 1.0
    empty = df.isna().sum().sum() + (df == "").sum().sum()
    return float(empty) / float(df.size)


def _is_ragged(df: pd.DataFrame) -> bool:
    # ragged if the count of non-empty cells per row varies a lot
    filled = df.notna().sum(axis=1)
    return bool(filled.std() > 1.5) if len(filled) > 1 else False


def _numeric_fraction(df: pd.DataFrame) -> float:
    vals = [str(v) for v in df.values.ravel() if pd.notna(v) and str(v).strip()]
    if not vals:
        return 0.0
    num = sum(1 for v in vals if _NUM_RE.match(v))
    return num / len(vals)


def _score(df: pd.DataFrame) -> tuple[float, dict]:
    if df is None or df.empty or df.shape[1] < 2:
        return 0.0, {"reason": "too small"}
    er = _empty_ratio(df)
    ragged = _is_ragged(df)
    numfrac = _numeric_fraction(df)
    size_bonus = min(1.0, (df.shape[0] * df.shape[1]) / 40.0)
    score = (
        0.40 * (1 - er)
        + 0.20 * (0.0 if ragged else 1.0)
        + 0.20 * size_bonus
        + 0.20 * min(1.0, numfrac * 1.4)  # data tables are number-heavy
    )
    meta = {"empty_ratio": round(er, 3), "ragged": ragged,
            "numeric_fraction": round(numfrac, 3)}
    return round(float(score), 3), meta


def _from_camelot(pdf_path: str, page: int, flavor: str) -> list[pd.DataFrame]:
    if not _HAS_CAMELOT:
        return []
    try:
        tables = camelot.read_pdf(pdf_path, pages=str(page), flavor=flavor,
                                  suppress_stdout=True)
        return [t.df for t in tables]
    except Exception:
        return []


def _from_pdfplumber(pdf_path: str, page: int) -> list[pd.DataFrame]:
    out: list[pd.DataFrame] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pg = pdf.pages[page - 1]
            for st in ({"vertical_strategy": "lines", "horizontal_strategy": "lines"},
                       {"vertical_strategy": "text", "horizontal_strategy": "text"}):
                for tb in pg.extract_tables(table_settings=st) or []:
                    if tb:
                        out.append(pd.DataFrame(tb))
    except Exception:
        pass
    return out


def extract_table(pdf_path: str, pdf_page: int,
                  item_hint: str = "") -> Optional[TableResult]:
    """Return the best TableResult on the given page, or None."""
    candidates: list[tuple[str, pd.DataFrame]] = []
    for flavor in ("lattice", "stream"):
        for df in _from_camelot(pdf_path, pdf_page, flavor):
            candidates.append((f"camelot:{flavor}", df))
    for df in _from_pdfplumber(pdf_path, pdf_page):
        candidates.append(("pdfplumber", df))

    best: Optional[TableResult] = None
    for method, raw in candidates:
        df = _clean(raw)
        score, meta = _score(df)
        if best is None or score > best.qc_score:
            best = TableResult(
                df=df, method=method, qc_score=score,
                n_rows=df.shape[0], n_cols=df.shape[1],
                empty_ratio=meta.get("empty_ratio", 1.0),
                ragged=bool(meta.get("ragged", False)),
                notes=f"numeric_fraction={meta.get('numeric_fraction')}",
            )
    return best


def save_table(result: TableResult, out_csv: str) -> str:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    result.df.to_csv(out_csv, index=False, header=False)
    return out_csv
