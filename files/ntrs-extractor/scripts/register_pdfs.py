#!/usr/bin/env python3
"""Bulk-register PDFs into config/corpus.yaml.

Scans data/raw/<program>/ for *.pdf and appends any not already registered,
generating a sensible doc_id and title. Existing entries are never overwritten,
so it is safe to re-run as the corpus grows.

Usage
-----
    # scan every program folder under data/raw and update corpus.yaml
    python scripts/register_pdfs.py

    # only a single program, and preview without writing
    python scripts/register_pdfs.py --program gemini --dry-run

Notes
-----
- doc_id is derived from the filename (e.g. 'gemini_7_results.pdf' -> 'GT7RESULTS'
  trimmed) but you should shorten it to a clean key like 'GT7' afterwards.
- title / ntrs_id / printed_offset are left as best-effort placeholders for you
  to refine; nothing downstream breaks if they stay as-is.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CORPUS = os.path.join(ROOT, "config", "corpus.yaml")

# program slug -> (label, id_prefix). Mirror src/ntrs_extractor/schema.PROGRAMS.
KNOWN = {
    "mercury": ("Project Mercury", "MR"),
    "gemini": ("Project Gemini", "GT"),
    "apollo": ("Project Apollo", "AP"),
    "skylab": ("Skylab", "SL"),
}


def _load_yaml(path):
    try:
        import yaml
        with open(path) as fh:
            return yaml.safe_load(fh) or {"programs": {}}
    except Exception:
        return None  # signal: fall back to text merge


def _existing_filenames(data, program):
    out = set()
    prog = (data.get("programs") or {}).get(program) or {}
    for d in prog.get("documents", []) or []:
        out.add(d.get("pdf_filename"))
    return out


def _doc_id_from_filename(fname, prefix):
    stem = os.path.splitext(os.path.basename(fname))[0]
    nums = re.findall(r"\d+", stem)
    tag = nums[0] if nums else re.sub(r"[^A-Za-z0-9]", "", stem)[:4].upper()
    return f"{prefix}{tag}"


def _title_from_filename(fname):
    stem = os.path.splitext(os.path.basename(fname))[0]
    return re.sub(r"[_\-]+", " ", stem).strip().title()


def build_entries(program, prefix, existing):
    folder = os.path.join(RAW, program)
    if not os.path.isdir(folder):
        return []
    entries = []
    for fn in sorted(os.listdir(folder)):
        if not fn.lower().endswith(".pdf") or fn in existing:
            continue
        entries.append({
            "doc_id": _doc_id_from_filename(fn, prefix),
            "pdf_filename": fn,
            "title": _title_from_filename(fn),
            "ntrs_id": "",
            "printed_offset": 0,
            "notes": "auto-registered; refine title/offset/ntrs_id",
        })
    return entries


def render_yaml(programs):
    """Emit corpus.yaml text from a {slug: {label,id_prefix,documents}} dict."""
    lines = [
        "# Corpus registry: one entry per PDF, grouped by space program.",
        "# Auto-managed by scripts/register_pdfs.py; hand-edit titles/offsets freely.",
        "",
        "programs:",
    ]
    for slug, blk in programs.items():
        lines.append(f"  {slug}:")
        lines.append(f"    label: {blk['label']}")
        lines.append(f"    id_prefix: {blk['id_prefix']}")
        lines.append("    documents:")
        for d in blk["documents"]:
            lines.append(f"      - doc_id: {d['doc_id']}")
            lines.append(f"        pdf_filename: {d['pdf_filename']}")
            lines.append(f"        title: \"{d.get('title','')}\"")
            lines.append(f"        ntrs_id: \"{d.get('ntrs_id','')}\"")
            lines.append(f"        printed_offset: {int(d.get('printed_offset', 0) or 0)}")
            lines.append(f"        notes: \"{d.get('notes','')}\"")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", default=None, help="only this program slug")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    data = _load_yaml(CORPUS)
    if data is None:
        print("PyYAML required for merge; install it or edit corpus.yaml by hand.",
              file=sys.stderr)
        return 2

    programs = data.get("programs") or {}
    slugs = [args.program] if args.program else sorted(
        set(list(KNOWN) + os.listdir(RAW) if os.path.isdir(RAW) else list(KNOWN)))

    added_total = 0
    for slug in slugs:
        if not os.path.isdir(os.path.join(RAW, slug)):
            continue
        label, prefix = KNOWN.get(slug, (slug.title(), slug[:2].upper()))
        blk = programs.setdefault(slug, {"label": label, "id_prefix": prefix,
                                         "documents": []})
        blk.setdefault("label", label)
        blk.setdefault("id_prefix", prefix)
        blk.setdefault("documents", [])
        new = build_entries(slug, blk["id_prefix"], _existing_filenames(data, slug))
        for e in new:
            blk["documents"].append(e)
            added_total += 1
            print(f"[+] {slug}: {e['doc_id']}  <-  {e['pdf_filename']}")

    if added_total == 0:
        print("No new PDFs to register.")
        return 0

    text = render_yaml(programs)
    if args.dry_run:
        print("\n----- corpus.yaml (preview) -----\n")
        print(text)
    else:
        with open(CORPUS, "w") as fh:
            fh.write(text)
        print(f"\nWrote {CORPUS} (+{added_total} document(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
