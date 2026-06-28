#!/usr/bin/env python3
"""Split generation context files into chunk inputs for parallel agents."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C  # noqa: E402
from scripts._common import read_jsonl, write_jsonl  # noqa: E402


SOURCES = {
    "gen1": C.GENERATIONJSON1,
    "gen2": C.GENERATIONJSON2,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk-size", type=int, default=10)
    args = ap.parse_args()

    C.GENERATED_CHUNKS.mkdir(parents=True, exist_ok=True)
    total = 0
    for group, path in SOURCES.items():
        rows = read_jsonl(path)
        if not rows:
            sys.exit(f"no rows in {path}")
        for idx in range(0, len(rows), args.chunk_size):
            chunk = rows[idx:idx + args.chunk_size]
            out = C.GENERATED_CHUNKS / f"{group}_{idx // args.chunk_size:03d}.input.jsonl"
            write_jsonl(out, chunk)
            total += 1
            print(f"wrote {len(chunk)} rows -> {out}")
    print(f"chunks={total}")


if __name__ == "__main__":
    main()
