"""Smoke + correctness tests for the three passes.

Run: pytest -q
These generate tiny synthetic PDFs on the fly so CI needs no binary fixtures.
"""
import math
import os
import numpy as np
import pytest

from ntrs_extractor import catalogue, catalogue_io, tables, figures, qc
from ntrs_extractor.schema import DocumentSpec

reportlab = pytest.importorskip("reportlab")
from reportlab.lib.pagesizes import letter          # noqa: E402
from reportlab.lib.units import inch                # noqa: E402
from reportlab.pdfgen import canvas                 # noqa: E402


def _grid(c, x, y, data, col_w=1.4 * inch, row_h=0.24 * inch):
    rows, cols = len(data), len(data[0])
    for i in range(rows + 1):
        c.line(x, y - i * row_h, x + cols * col_w, y - i * row_h)
    for j in range(cols + 1):
        c.line(x + j * col_w, y, x + j * col_w, y - rows * row_h)
    c.setFont("Times-Roman", 8)
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            c.drawString(x + j * col_w + 3, y - (i + 1) * row_h + 7, str(v))


@pytest.fixture(scope="module")
def sample_pdf(tmp_path_factory):
    p = tmp_path_factory.mktemp("pdf") / "sample.pdf"
    c = canvas.Canvas(str(p), pagesize=letter)
    # page 1: a table
    c.setFont("Times-Bold", 10)
    c.drawCentredString(letter[0] / 2, 9 * inch, "Table 1")
    c.drawCentredString(letter[0] / 2, 8.7 * inch, "Sample Metrics")
    _grid(c, 1.2 * inch, 8.4 * inch,
          [["Name", "A", "B"], ["r1", "1.0", "2.0"], ["r2", "3.0", "4.0"],
           ["r3", "5.0", "6.0"]])
    c.drawCentredString(letter[0] / 2, 0.5 * inch, "1")
    c.showPage()
    # page 2: a line chart
    ax_x, ax_y, ax_w, ax_h = 1.4 * inch, 2 * inch, 5 * inch, 5 * inch
    c.line(ax_x, ax_y, ax_x + ax_w, ax_y)
    c.line(ax_x, ax_y, ax_x, ax_y + ax_h)
    pts = []
    for i in range(120):
        t = i / 12.0
        yy = ax_y + (50 + 20 * math.sin(t)) / 100 * ax_h
        xx = ax_x + t / 10.0 * ax_w
        pts.append((xx, yy))
    c.lines([(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
             for i in range(len(pts) - 1)])
    c.setFont("Times-Roman", 9)
    c.drawCentredString(letter[0] / 2, 1.2 * inch,
                        "Figure 2. Sample rate history versus time")
    c.drawCentredString(letter[0] / 2, 0.5 * inch, "2")
    c.showPage()
    c.save()
    return str(p)


def test_pass1_catalogue(sample_pdf):
    spec = DocumentSpec("TST", "mercury", "sample.pdf", "Test Doc")
    entries = catalogue.catalogue_document(spec, sample_pdf)
    kinds = {e.kind for e in entries}
    assert "table" in kinds and "figure" in kinds
    t = next(e for e in entries if e.kind == "table")
    assert t.approx_rows and t.approx_cols >= 3
    f = next(e for e in entries if e.kind == "figure")
    assert f.figure_subtype == "line"
    assert f.printed_page_number == "2"


def test_pass1_catalogue_io_roundtrip(sample_pdf, tmp_path):
    spec = DocumentSpec("TST", "mercury", "sample.pdf", "Test Doc")
    entries = catalogue.catalogue_document(spec, sample_pdf)
    out = tmp_path / "cat.xlsx"
    catalogue_io.write_catalogue(entries, str(out), "Test Doc")
    rows = catalogue_io.read_catalogue(str(out), "All")
    assert len(rows) == len(entries)
    assert {"A_tabular", "B_graphical"} <= {r["sub_catalogue"] for r in rows}


def test_pass2_tables(sample_pdf):
    res = tables.extract_table(sample_pdf, 1)
    assert res is not None and res.n_cols >= 3
    rec = qc.table_qc(res)
    assert rec["qc_flag"] in ("green", "amber")


def test_pass3_figure_trace_and_calibration(sample_pdf):
    res = figures.digitise_figure(sample_pdf, 2)
    assert res.n_points > 20
    assert not res.calibrated
    rec = qc.figure_qc(res)
    assert rec["qc_flag"] in ("amber", "red")  # uncalibrated capped
    # calibrate and confirm data-space conversion runs
    x0, y0, x1, y1 = res.plot_bbox_px
    cal = figures.CalibrationSpec(x_px=(x0, x1), x_val=(0, 10),
                                  y_px=(y1, y0), y_val=(0, 100))
    res2 = figures.digitise_figure(sample_pdf, 2, calibration=cal)
    assert res2.calibrated
    arr = next(iter(res2.series.values()))
    assert arr[:, 0].max() <= 11 and arr[:, 1].max() <= 110


def test_qc_flag_thresholds():
    assert qc.flag_from_score(0.9) == "green"
    assert qc.flag_from_score(0.5) == "amber"
    assert qc.flag_from_score(0.1) == "red"
