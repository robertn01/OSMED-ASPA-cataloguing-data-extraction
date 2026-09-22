"""Load the corpus registry (config/corpus.yaml) into typed objects."""
from __future__ import annotations

import os
from typing import Optional

from .schema import DocumentSpec, Program, PROGRAMS

try:
    import yaml
    _HAS_YAML = True
except Exception:  # pragma: no cover
    _HAS_YAML = False


def _minimal_yaml_load(text: str) -> dict:
    """Tiny fallback parser for the specific corpus.yaml shape (no PyYAML).

    Not a general YAML parser - only used if PyYAML is unavailable.
    """
    import re
    programs: dict = {}
    cur_prog = None
    cur_doc = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 2 and line.endswith(":"):
            cur_prog = line[:-1]
            programs[cur_prog] = {"documents": []}
            cur_doc = None
        elif indent == 4 and ":" in line and not line.startswith("- "):
            k, v = line.split(":", 1)
            programs[cur_prog][k.strip()] = v.strip().strip('"')
        elif indent == 6 and line.startswith("- "):
            cur_doc = {}
            programs[cur_prog]["documents"].append(cur_doc)
            line = line[2:]
            if ":" in line:
                k, v = line.split(":", 1)
                cur_doc[k.strip()] = v.strip().strip('"')
        elif indent >= 8 and ":" in line and cur_doc is not None:
            k, v = line.split(":", 1)
            cur_doc[k.strip()] = v.strip().strip('"')
    return {"programs": programs}


def load_corpus(path: str = "config/corpus.yaml") -> dict[str, list[DocumentSpec]]:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    data = yaml.safe_load(text) if _HAS_YAML else _minimal_yaml_load(text)
    out: dict[str, list[DocumentSpec]] = {}
    for pkey, pblock in (data.get("programs") or {}).items():
        docs = []
        for d in pblock.get("documents", []):
            docs.append(DocumentSpec(
                doc_id=str(d["doc_id"]),
                program_key=pkey,
                pdf_filename=str(d["pdf_filename"]),
                title=str(d.get("title", "")),
                ntrs_id=str(d.get("ntrs_id", "")),
                printed_offset=int(d.get("printed_offset", 0) or 0),
                notes=str(d.get("notes", "")),
            ))
        out[pkey] = docs
    return out


def program_for(key: str) -> Program:
    return PROGRAMS.get(key, Program(key, key.title(), key[:2].upper()))
