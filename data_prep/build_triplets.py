#!/usr/bin/env python3
"""Step 3 of data prep: merge core seeds with generated drafts into one unified
landing-zone file.

Full rebuild, deterministic and idempotent: reads the WHOLE core set + ALL
generation rounds, dedups by id, and OVERWRITES landing_zone/triplets.jsonl.
Re-running can't double rows. (No shards, no manifest, no active flag.)

Inputs:
  data_prep/core/no_draft.jsonl      {id, kind, context, final}
  data_prep/core/with_draft.jsonl    {id, kind, context, draft, final}
  data_prep/generation-*/<model>/outputs/*.output.jsonl   {id, draft}
    (models are auto-discovered: any subdir of a generation-* dir with outputs)

Build rules (context/final always come from the core seed; only draft varies):
  - each with_draft seed -> gold row  {id: "real:"+id,   draft: <real draft>}
  - each model draft of a seed id ->  {id: "<model>:"+id, draft: <gen draft>}
    (no_draft seeds get only model rows; with_draft seeds get gold + alt rows)

Usage:
  python3 data_prep/build_triplets.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # data_prep/
sys.path.insert(0, str(HERE.parent))            # repo root
from config import C  # noqa: E402
from scripts._common import read_jsonl, write_jsonl, validate_triplets  # noqa: E402


def load_core_seeds():
    """Return {id: {context, final, draft?}} from the two core files."""
    seeds = {}
    for path, has_draft in ((HERE / "core" / "no_draft.jsonl", False),
                            (HERE / "core" / "with_draft.jsonl", True)):
        for n, row in enumerate(read_jsonl(path), 1):
            rid = str(row.get("id", "")).strip()
            context = str(row.get("context", "")).strip()
            final = str(row.get("final", "")).strip()
            if not rid or not context or not final:
                sys.exit(f"{path}:{n}: every core row needs id, context, final")
            if rid in seeds:
                sys.exit(f"{path}:{n}: duplicate core id {rid}")
            seed = {"context": context, "final": final}
            if has_draft:
                draft = str(row.get("draft", "")).strip()
                if not draft:
                    sys.exit(f"{path}:{n}: with_draft row {rid} has no draft")
                seed["draft"] = draft
            seeds[rid] = seed
    return seeds


def load_model_drafts():
    """Return {(model, id): draft} across ALL generation-* rounds.

    A repeated (model, id) across rounds keeps the newest (later sorted dir wins).
    """
    drafts = {}
    for gen_dir in sorted(HERE.glob("generation-*")):
        if not gen_dir.is_dir():
            continue
        for model_dir in sorted(gen_dir.iterdir()):
            outputs_dir = model_dir / "outputs"
            if not (model_dir.is_dir() and outputs_dir.is_dir()):
                continue
            model = model_dir.name
            for path in sorted(outputs_dir.glob("*.output.jsonl")):
                for n, line in enumerate(path.read_text().splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        sys.exit(f"{path}:{n}: invalid JSON: {exc}")
                    if set(row) != {"id", "draft"}:
                        sys.exit(f"{path}:{n}: expected only id/draft, got {sorted(row)}")
                    rid = str(row["id"]).strip()
                    draft = str(row["draft"]).strip()
                    if not rid or not draft:
                        sys.exit(f"{path}:{n}: id and draft must be non-empty")
                    drafts[(model, rid)] = draft
    return drafts


def build_triplets(seeds, model_drafts):
    triplets = []
    unknown = []

    # Gold rows from real drafts.
    for rid, seed in seeds.items():
        if "draft" in seed:
            triplets.append({
                "id": f"real:{rid}",
                "context": seed["context"],
                "draft": seed["draft"],
                "final": seed["final"],
            })

    # Generated draft rows, one per (model, seed).
    for (model, rid), draft in sorted(model_drafts.items()):
        seed = seeds.get(rid)
        if not seed:
            unknown.append(f"{model}:{rid}")
            continue
        triplets.append({
            "id": f"{model}:{rid}",
            "context": seed["context"],
            "draft": draft,
            "final": seed["final"],
        })

    if unknown:
        sys.exit("generated ids with no matching core seed:\n  " + "\n  ".join(unknown[:20]))
    return triplets


def main():
    seeds = load_core_seeds()
    if not seeds:
        sys.exit("no core seeds found in data_prep/core/{no_draft,with_draft}.jsonl")

    model_drafts = load_model_drafts()
    if not model_drafts:
        sys.exit("no generated drafts found under data_prep/generation-*/<model>/outputs/")

    triplets = build_triplets(seeds, model_drafts)

    errors = validate_triplets(triplets)
    # Gold rows may intentionally be identity pairs (a real draft posted verbatim);
    # only flag draft==final for model-generated drafts, where it signals a copy.
    errors += [f"draft equals final: {t['id']}" for t in triplets
               if t["draft"].strip() == t["final"].strip() and not t["id"].startswith("real:")]
    if errors:
        sys.exit("triplet validation failed:\n  " + "\n  ".join(errors[:20]))

    write_jsonl(C.LANDING_FILE, triplets)

    models = sorted({m for (m, _rid) in model_drafts})
    counts = {"real": sum(t["id"].startswith("real:") for t in triplets)}
    for model in models:
        counts[model] = sum(t["id"].startswith(f"{model}:") for t in triplets)
    print(f"wrote {len(triplets)} triplets -> {C.LANDING_FILE}")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
