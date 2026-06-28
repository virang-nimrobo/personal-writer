#!/usr/bin/env python3
"""Create two context-only generation input files from curated targets.

Each output row has:
  {id, context}

No draft/final/real text is included. The two files are intentionally separate so
later generation can run two passes with different sampling or instructions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C  # noqa: E402
from scripts._common import read_jsonl, write_jsonl  # noqa: E402


def make_rows(targets, suffix):
    return [
        {
            "id": f"{target['id']}:{suffix}",
            "context": target["context"],
        }
        for target in targets
    ]


def main():
    targets = read_jsonl(C.TARGETS)
    if not targets:
        sys.exit(f"no targets found at {C.TARGETS}; run scripts/00_build_targets.py first")

    write_jsonl(C.GENERATIONJSON1, make_rows(targets, "gen1"))
    write_jsonl(C.GENERATIONJSON2, make_rows(targets, "gen2"))
    print(f"wrote {len(targets)} rows -> {C.GENERATIONJSON1}")
    print(f"wrote {len(targets)} rows -> {C.GENERATIONJSON2}")


if __name__ == "__main__":
    main()
