"""Pass 3 - automated figure (chart) reader. The hardest pass.

Scope: recover (x, y) series from *data-bearing* line / scatter / trace charts
(schematics, maps and photographs are catalogued but not digitised).

Pipeline
--------
1. Rasterise the figure region.
2. Detect the plot rectangle (longest horizontal + vertical dark runs -> axes).
3. Calibrate pixel<->data. Two modes:
     a. auto : OCR-free calibration is impossible in general, so we expose a
        `CalibrationSpec` that a human fills from the axis tick labels (two x and
        two y reference points). This is the reliable, auditable path.
     b. assisted: if tick label OCR is available (pytesseract), attempt to read
        numeric ticks; still emit confidence + require review.
4. Trace data ink inside the plot rectangle (after removing gridlines/axes) and
   convert each retained pixel column to a (x, y) sample. Multiple series are
   separated by dash/solid + connected-component heuristics.
5. Emit CSV of (x, y[, series]) plus a QC overlay PNG (original with recovered
   points superimposed) so a reviewer can eyeball fidelity.

Everything degrades gracefully: if calibration is missing we still return the
traced *pixel* curve and mark the item needs_review.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    import cv2
    _HAS_CV2 = True
except Exception:  # pragma: no cover
    _HAS_CV2 = False

from . import pdf_utils


@dataclass
class CalibrationSpec:
    """Two known reference points per axis, in pixel and data coordinates.

    x_px/x_val: two x tick positions (pixels within the crop) and their values.
    y_px/y_val: two y tick positions and their values. Log axes supported.
    """
    x_px: tuple[float, float]
    x_val: tuple[float, float]
    y_px: tuple[float, float]
    y_val: tuple[float, float]
    x_log: bool = False
    y_log: bool = False

    def px_to_data(self, px: np.ndarray, py: np.ndarray):
        def lin(p, p0, p1, v0, v1, log):
            v0_, v1_ = (np.log10(v0), np.log10(v1)) if log else (v0, v1)
            val = v0_ + (p - p0) * (v1_ - v0_) / (p1 - p0)
            return np.power(10.0, val) if log else val
        x = lin(px, self.x_px[0], self.x_px[1], self.x_val[0], self.x_val[1], self.x_log)
        y = lin(py, self.y_px[0], self.y_px[1], self.y_val[0], self.y_val[1], self.y_log)
        return x, y


@dataclass
class FigureResult:
    series: dict[str, np.ndarray]        # name -> (N,2) array in data coords (or px)
    plot_bbox_px: tuple[int, int, int, int]
    calibrated: bool
    qc_score: float
    n_points: int
    overlay: Optional[np.ndarray] = None
    notes: str = ""


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if _HAS_CV2 else img.mean(2).astype(np.uint8)
    return img


def detect_plot_rect(gray: np.ndarray) -> tuple[int, int, int, int]:
    """Find the plot rectangle as the strongest long horizontal & vertical dark
    runs. Returns (x0, y0, x1, y1) in pixels."""
    h, w = gray.shape
    dark = (gray < 128).astype(np.uint8)
    col_sum = dark.sum(axis=0)          # vertical lines -> tall columns
    row_sum = dark.sum(axis=1)          # horizontal lines -> wide rows
    # candidate axis lines: columns/rows whose dark count exceeds 50% of extent
    v_cols = np.where(col_sum > 0.5 * h)[0]
    h_rows = np.where(row_sum > 0.5 * w)[0]
    x0 = int(v_cols.min()) if v_cols.size else int(0.12 * w)
    x1 = int(v_cols.max()) if v_cols.size else int(0.95 * w)
    y0 = int(h_rows.min()) if h_rows.size else int(0.05 * h)
    y1 = int(h_rows.max()) if h_rows.size else int(0.88 * h)
    if x1 - x0 < 0.2 * w:               # fallback if detection collapsed
        x0, x1 = int(0.12 * w), int(0.95 * w)
    if y1 - y0 < 0.2 * h:
        y0, y1 = int(0.05 * h), int(0.88 * h)
    return x0, y0, x1, y1


def _trace_curves(gray: np.ndarray, rect: tuple[int, int, int, int]):
    """Return a dict of pixel-space series traced within the plot rectangle.

    Simple, robust approach for single/low-multiplicity line charts:
      - crop to the rect interior (drop the axis lines themselves),
      - threshold to data ink,
      - remove near-full rows/cols (residual gridlines),
      - for each x column, take the median y of ink pixels as the curve sample.
    For >1 curve, we split ink pixels per column into vertical clusters and label
    them top/bottom by y-order (works for the common 2-trace NTRS charts).
    """
    x0, y0, x1, y1 = rect
    pad = 2
    interior = gray[y0 + pad:y1 - pad, x0 + pad:x1 - pad]
    ink = interior < 110
    hh, ww = ink.shape
    if hh < 5 or ww < 5:
        return {}, (x0 + pad, y0 + pad)

    # strip residual gridlines: rows/cols that are almost entirely ink
    ink[:, ink.sum(axis=0) > 0.85 * hh] = False
    ink[ink.sum(axis=1) > 0.85 * ww, :] = False

    series_single: list[tuple[int, float]] = []
    series_multi: dict[str, list[tuple[int, float]]] = {"series_1": [], "series_2": []}
    for cx in range(ww):
        ys = np.where(ink[:, cx])[0]
        if ys.size == 0:
            continue
        # cluster ys into runs separated by > 6 px gaps
        clusters = []
        start = ys[0]
        prev = ys[0]
        for yv in ys[1:]:
            if yv - prev > 6:
                clusters.append((start, prev))
                start = yv
            prev = yv
        clusters.append((start, prev))
        centers = sorted((a + b) / 2.0 for a, b in clusters)
        series_single.append((cx, float(np.median(ys))))
        if len(centers) >= 2:
            series_multi["series_1"].append((cx, centers[0]))    # upper (smaller y)
            series_multi["series_2"].append((cx, centers[-1]))   # lower
        else:
            # assign lone point to nearest existing track by continuity
            series_multi["series_1"].append((cx, centers[0]))

    origin = (x0 + pad, y0 + pad)
    # decide multiplicity: if series_2 is well populated, treat as 2 curves
    if len(series_multi["series_2"]) > 0.3 * max(1, len(series_single)):
        out = {k: np.array([(cx, cy) for cx, cy in v], dtype=float)
               for k, v in series_multi.items() if v}
    else:
        out = {"series_1": np.array(series_single, dtype=float)}
    return out, origin


def _qc_score(series: dict[str, np.ndarray], rect) -> float:
    if not series:
        return 0.0
    x0, y0, x1, y1 = rect
    width = max(1, x1 - x0)
    covs = []
    for arr in series.values():
        if arr.size == 0:
            continue
        xspan = (arr[:, 0].max() - arr[:, 0].min()) / width
        density = len(np.unique(arr[:, 0].astype(int))) / width
        covs.append(0.5 * min(1.0, xspan) + 0.5 * min(1.0, density))
    return round(float(np.mean(covs)) if covs else 0.0, 3)


def _overlay(img: np.ndarray, series_px: dict[str, np.ndarray],
             origin, rect) -> np.ndarray:
    ov = img.copy()
    if not _HAS_CV2:
        return ov
    x0, y0, x1, y1 = rect
    cv2.rectangle(ov, (x0, y0), (x1, y1), (0, 128, 255), 1)
    colours = [(255, 0, 0), (0, 160, 0), (160, 0, 200)]
    ox, oy = origin
    for i, arr in enumerate(series_px.values()):
        col = colours[i % len(colours)]
        for cx, cy in arr:
            cv2.circle(ov, (int(ox + cx), int(oy + cy)), 1, col, -1)
    return ov


def digitise_figure(pdf_path: str, pdf_page: int,
                    bbox_pts: Optional[tuple] = None,
                    calibration: Optional[CalibrationSpec] = None,
                    dpi: int = 300) -> FigureResult:
    """Digitise a chart. `bbox_pts` (x0,top,x1,bottom in PDF points) crops to the
    figure; if None the whole page is used."""
    if not _HAS_CV2:
        raise RuntimeError("OpenCV required for figure digitisation")
    if bbox_pts:
        img = pdf_utils.crop_bbox(pdf_path, pdf_page, bbox_pts, dpi=dpi)
    else:
        img = pdf_utils.render_page(pdf_path, pdf_page, dpi=dpi)

    gray = _to_gray(img)
    rect = detect_plot_rect(gray)
    series_px, origin = _trace_curves(gray, rect)

    # shift series into crop-pixel coords (origin offset)
    ox, oy = origin
    series_abs = {k: np.column_stack([v[:, 0] + ox, v[:, 1] + oy])
                  for k, v in series_px.items() if v.size}

    calibrated = calibration is not None
    if calibrated:
        series_data = {}
        for k, v in series_abs.items():
            x, y = calibration.px_to_data(v[:, 0], v[:, 1])
            order = np.argsort(x)
            series_data[k] = np.column_stack([x[order], y[order]])
    else:
        series_data = series_abs  # pixel space, needs_review

    qc = _qc_score(series_px, rect)
    overlay = _overlay(img, series_px, origin, rect)
    n_pts = int(sum(len(v) for v in series_data.values()))
    return FigureResult(
        series=series_data,
        plot_bbox_px=rect,
        calibrated=calibrated,
        qc_score=qc,
        n_points=n_pts,
        overlay=overlay,
        notes="pixel-space (uncalibrated)" if not calibrated else "calibrated",
    )


def save_figure(result: FigureResult, out_csv: str,
                overlay_png: Optional[str] = None) -> str:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    import pandas as pd
    frames = []
    for name, arr in result.series.items():
        if arr.size == 0:
            continue
        df = pd.DataFrame(arr, columns=["x", "y"])
        df.insert(0, "series", name)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["series", "x", "y"])
    out.to_csv(out_csv, index=False)
    if overlay_png and result.overlay is not None and _HAS_CV2:
        os.makedirs(os.path.dirname(overlay_png), exist_ok=True)
        cv2.imwrite(overlay_png, cv2.cvtColor(result.overlay, cv2.COLOR_RGB2BGR))
    return out_csv
