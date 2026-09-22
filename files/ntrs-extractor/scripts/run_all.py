#!/usr/bin/env python3
"""Run the full pipeline across the whole corpus (or one program) and print a
consolidated status table. Thin wrapper over the CLI so large runs are one call.

Usage
-----
    python scripts/run_all.py                 # every program, all three passes
    python scripts/run_all.py --program apollo
    python scripts/run_all.py --pass catalogue   # just Pass 1 across the corpus

For very large corpora, prefer GNU parallel over the per-document CLI, e.g.:
    ls data/raw/*/ | ... | parallel ntrs-extract all --doc {}
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=ROOT)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", default=None)
    ap.add_argument("--pass", dest="which", default="all",
                    choices=["all", "catalogue", "tables", "figures"])
    args = ap.parse_args(argv)

    base = [sys.executable, "-m", "ntrs_extractor.cli"]
    passes = (["catalogue", "tables", "figures"]
              if args.which == "all" else [args.which])

    env_ok = os.path.join(ROOT, "src")
    os.environ["PYTHONPATH"] = env_ok + os.pathsep + os.environ.get("PYTHONPATH", "")

    rc = 0
    for p in passes:
        cmd = base + [p]
        if args.program:
            cmd += ["--program", args.program]
        rc |= run(cmd)
    print("\nDone." if rc == 0 else "\nCompleted with errors.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
