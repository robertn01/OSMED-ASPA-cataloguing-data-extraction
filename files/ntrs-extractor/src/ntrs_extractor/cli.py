"""Command-line orchestrator for the three-pass pipeline.

Examples
--------
    # Pass 1 - catalogue everything in the corpus
    python -m ntrs_extractor.cli catalogue --config config/corpus.yaml

    # Pass 2 - extract tables for one program
    python -m ntrs_extractor.cli tables --program apollo

    # Pass 3 - digitise figures (uncalibrated trace + overlays for review)
    python -m ntrs_extractor.cli figures --program mercury

    # Everything for one document
    python -m ntrs_extractor.cli all --doc MR4
"""
from __future__ import annotations

import argparse
import os
import sys

from . import catalogue as cat_pass
from . import catalogue_io, tables, figures, qc
from .config import load_corpus, program_for
from .schema import DATA_BEARING_FIGURE_SUBTYPES


def _iter_docs(corpus, program=None, doc=None):
    for pkey, docs in corpus.items():
        if program and pkey != program:
            continue
        for d in docs:
            if doc and d.doc_id != doc:
                continue
            yield d


def _pdf_path(spec) -> str:
    prog = program_for(spec.program_key)
    return os.path.join(prog.raw_dir, spec.pdf_filename)


def cmd_catalogue(args, corpus):
    for spec in _iter_docs(corpus, args.program, args.doc):
        prog = program_for(spec.program_key)
        pdf = _pdf_path(spec)
        if not os.path.exists(pdf):
            print(f"[skip] missing PDF: {pdf}", file=sys.stderr)
            continue
        entries = cat_pass.catalogue_document(spec, pdf)
        out = os.path.join(prog.catalogue_dir, f"{spec.doc_id}_catalogue.xlsx")
        catalogue_io.write_catalogue(entries, out, doc_title=spec.title)
        n_t = sum(1 for e in entries if e.kind == "table")
        n_f = sum(1 for e in entries if e.kind == "figure")
        print(f"[catalogue] {spec.doc_id}: {n_t} tables, {n_f} figures -> {out}")


def cmd_tables(args, corpus):
    for spec in _iter_docs(corpus, args.program, args.doc):
        prog = program_for(spec.program_key)
        pdf = _pdf_path(spec)
        cat_path = os.path.join(prog.catalogue_dir, f"{spec.doc_id}_catalogue.xlsx")
        if not (os.path.exists(pdf) and os.path.exists(cat_path)):
            print(f"[skip] need PDF+catalogue for {spec.doc_id}", file=sys.stderr)
            continue
        rows = catalogue_io.read_catalogue(cat_path, sheet="A_tabular")
        qc_records = []
        for r in rows:
            page = int(r["pdf_page_number"])
            res = tables.extract_table(pdf, page, item_hint=r.get("item_number", ""))
            out_csv = os.path.join(prog.output_dir, "tables",
                                   f"{r['catalogue_id']}.csv")
            rec = qc.table_qc(res)
            rec["catalogue_id"] = r["catalogue_id"]
            rec["item_number"] = r["item_number"]
            if res is not None and res.qc_score > 0:
                tables.save_table(res, out_csv)
                rec["output_path"] = out_csv
            qc_records.append(rec)
            print(f"[tables] {r['catalogue_id']} {rec['qc_flag']:5s} "
                  f"score={rec['qc_score']} ({rec.get('method','-')})")
        qc.write_qc_report(qc_records,
                           os.path.join(prog.qc_dir, f"{spec.doc_id}_tables_qc.xlsx"),
                           doc_title=spec.title)


def cmd_figures(args, corpus):
    for spec in _iter_docs(corpus, args.program, args.doc):
        prog = program_for(spec.program_key)
        pdf = _pdf_path(spec)
        cat_path = os.path.join(prog.catalogue_dir, f"{spec.doc_id}_catalogue.xlsx")
        if not (os.path.exists(pdf) and os.path.exists(cat_path)):
            print(f"[skip] need PDF+catalogue for {spec.doc_id}", file=sys.stderr)
            continue
        rows = catalogue_io.read_catalogue(cat_path, sheet="B_graphical")
        qc_records = []
        for r in rows:
            if r.get("figure_subtype") not in DATA_BEARING_FIGURE_SUBTYPES:
                continue
            page = int(r["pdf_page_number"])
            try:
                res = figures.digitise_figure(pdf, page)  # uncalibrated trace
            except Exception as exc:  # keep going
                print(f"[figures] {r['catalogue_id']} ERROR {exc}", file=sys.stderr)
                continue
            out_csv = os.path.join(prog.output_dir, "figures",
                                   f"{r['catalogue_id']}.csv")
            overlay = os.path.join(prog.qc_dir, "overlays",
                                   f"{r['catalogue_id']}.png")
            figures.save_figure(res, out_csv, overlay_png=overlay)
            rec = qc.figure_qc(res)
            rec["catalogue_id"] = r["catalogue_id"]
            rec["item_number"] = r["item_number"]
            rec["output_path"] = out_csv
            qc_records.append(rec)
            print(f"[figures] {r['catalogue_id']} {rec['qc_flag']:5s} "
                  f"score={rec['qc_score']} pts={rec['n_points']} "
                  f"(overlay: {overlay})")
        qc.write_qc_report(qc_records,
                           os.path.join(prog.qc_dir, f"{spec.doc_id}_figures_qc.xlsx"),
                           doc_title=spec.title)


def build_parser():
    p = argparse.ArgumentParser(prog="ntrs_extractor")
    p.add_argument("--config", default="config/corpus.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("catalogue", "tables", "figures", "all"):
        sp = sub.add_parser(name)
        sp.add_argument("--program", default=None)
        sp.add_argument("--doc", default=None)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    corpus = load_corpus(args.config)
    if args.cmd in ("catalogue", "all"):
        cmd_catalogue(args, corpus)
    if args.cmd in ("tables", "all"):
        cmd_tables(args, corpus)
    if args.cmd in ("figures", "all"):
        cmd_figures(args, corpus)


if __name__ == "__main__":
    main()
