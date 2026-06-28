#!/usr/bin/env python3
"""Validate and merge agent-generated chunk outputs."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C  # noqa: E402
from scripts._common import read_jsonl, write_jsonl  # noqa: E402


GROUPS = {
    "gen1": (C.GENERATIONJSON1, C.GENERATION1_OUTPUTS),
    "gen2": (C.GENERATIONJSON2, C.GENERATION2_OUTPUTS),
}


def load_output_file(path):
    rows = []
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{n}: invalid JSON: {exc}") from exc
        if set(row) != {"id", "generated"}:
            raise SystemExit(f"{path}:{n}: expected only id/generated fields, got {sorted(row)}")
        if not str(row["id"]).strip() or not str(row["generated"]).strip():
            raise SystemExit(f"{path}:{n}: id and generated must be non-empty")
        rows.append({"id": str(row["id"]).strip(), "generated": str(row["generated"]).strip()})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=sorted(GROUPS), required=True)
    args = ap.parse_args()

    source_path, out_path = GROUPS[args.group]
    expected = [r["id"] for r in read_jsonl(source_path)]
    expected_set = set(expected)

    rows = []
    for path in sorted(C.GENERATED_CHUNKS.glob(f"{args.group}_*.output.jsonl")):
        rows.extend(load_output_file(path))

    seen = set()
    dupes = []
    unexpected = []
    by_id = {}
    for row in rows:
        rid = row["id"]
        if rid in seen:
            dupes.append(rid)
        seen.add(rid)
        if rid not in expected_set:
            unexpected.append(rid)
        by_id[rid] = row

    missing = [rid for rid in expected if rid not in seen]
    if missing or dupes or unexpected:
        print(f"missing={len(missing)} duplicate={len(dupes)} unexpected={len(unexpected)}", file=sys.stderr)
        if missing:
            print("missing ids:", *missing[:20], sep="\n  ", file=sys.stderr)
        if dupes:
            print("duplicate ids:", *dupes[:20], sep="\n  ", file=sys.stderr)
        if unexpected:
            print("unexpected ids:", *unexpected[:20], sep="\n  ", file=sys.stderr)
        sys.exit(1)

    merged = [by_id[rid] for rid in expected]
    write_jsonl(out_path, merged)
    print(f"merged {len(merged)} rows -> {out_path}")


if __name__ == "__main__":
    main()
