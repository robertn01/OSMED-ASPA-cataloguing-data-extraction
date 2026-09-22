#!/usr/bin/env python3
"""Fetch source PDFs from the NASA Technical Reports Server (NTRS) by accession id.

NTRS exposes a public JSON API. Each report has a numeric accession id (the digits
in an ntrs.nasa.gov/citations/<id> URL). This helper downloads the primary PDF for
each id into data/raw/<program>/.

Usage
-----
    python scripts/fetch_ntrs.py --program apollo 19710021329 19720005957
    python scripts/fetch_ntrs.py --program gemini --ids-file gemini_ids.txt

Requires: requests  (pip install requests)

This is intentionally conservative: it only downloads, verifies the file is a PDF,
and skips anything already present. Respect NTRS terms of use and rate limits.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://ntrs.nasa.gov/api/citations/{id}/downloads"
META = "https://ntrs.nasa.gov/api/citations/{id}"


def _fetch(url, **kw):
    import requests
    r = requests.get(url, timeout=60, **kw)
    r.raise_for_status()
    return r


def download_one(acc_id: str, out_dir: str, sleep: float = 1.0) -> str | None:
    import requests
    os.makedirs(out_dir, exist_ok=True)
    try:
        meta = _fetch(META.format(id=acc_id)).json()
    except Exception as exc:
        print(f"[skip] {acc_id}: metadata error {exc}", file=sys.stderr)
        return None
    title = (meta.get("title") or acc_id).strip()
    # Find the primary STI PDF link.
    pdf_url = None
    for d in meta.get("downloads", []) or []:
        link = d.get("links", {}).get("pdf") or d.get("links", {}).get("original")
        if link:
            pdf_url = link if link.startswith("http") else f"https://ntrs.nasa.gov{link}"
            break
    if not pdf_url:
        print(f"[skip] {acc_id}: no PDF download link", file=sys.stderr)
        return None
    fname = f"{acc_id}.pdf"
    dest = os.path.join(out_dir, fname)
    if os.path.exists(dest):
        print(f"[have] {acc_id} -> {dest}")
        return dest
    try:
        r = _fetch(pdf_url, stream=True)
        if "pdf" not in r.headers.get("Content-Type", "").lower():
            print(f"[warn] {acc_id}: content not PDF ({r.headers.get('Content-Type')})",
                  file=sys.stderr)
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
        print(f"[ok]   {acc_id}: {title[:60]} -> {dest}")
        time.sleep(sleep)
        return dest
    except Exception as exc:
        print(f"[fail] {acc_id}: {exc}", file=sys.stderr)
        return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("ids", nargs="*", help="NTRS accession ids")
    ap.add_argument("--ids-file", help="text file, one accession id per line")
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args(argv)

    ids = list(args.ids)
    if args.ids_file:
        with open(args.ids_file) as fh:
            ids += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    if not ids:
        ap.error("provide accession ids or --ids-file")

    out_dir = os.path.join(ROOT, "data", "raw", args.program)
    ok = 0
    for acc in ids:
        if download_one(acc, out_dir, sleep=args.sleep):
            ok += 1
    print(f"\nDownloaded/verified {ok}/{len(ids)} into {out_dir}")
    print("Next: python scripts/register_pdfs.py --program", args.program)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
