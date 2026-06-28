#!/usr/bin/env python3
"""Build editor triples from curated real tuples and generated final-style replies.

Output: data/synth/triples.jsonl

Rows:
- real tuples with an actual draft+final keep the real draft and real final
- generated rows use generated text as final and a deterministic off-voice draft
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C  # noqa: E402
from scripts._common import read_jsonl, write_jsonl  # noqa: E402


GENERATED_SOURCES = [
    ("local-gen1", C.GENERATION1_OUTPUTS),
    ("local-gen2", C.GENERATION2_OUTPUTS),
    ("gemini-gen1", C.GEMINI_GENERATION1_OUTPUTS),
    ("gemini-gen2", C.GEMINI_GENERATION2_OUTPUTS),
]

OPENERS = ["This is huge.", "Love this.", "So true.", "Honestly?", "Hot take:"]
HYPE = ["absolutely", "game-changing", "incredible", "massive", "next-level"]


def seed(text):
    return int(hashlib.md5(text.encode()).hexdigest(), 16)


def target_id_from_generated_id(generated_id):
    # tweet:<id>:gen1 -> tweet:<id>
    parts = generated_id.split(":")
    if len(parts) >= 3 and parts[-1].startswith("gen"):
        return ":".join(parts[:-1])
    return generated_id


def make_draft(final, rec_id):
    """Create a rough/off-voice draft with same substance."""
    s = seed(rec_id)
    text = final.strip()

    text = re.sub(r"(\w)\. ", r"\1 — ", text, count=1)
    text = re.sub(r"(\w), ", r"\1 — ", text, count=1)

    hype = HYPE[s % len(HYPE)]
    text = re.sub(
        r"\b(outcome|run|session|agent|loop|metric|signal|model|cost)\b",
        rf"{hype} \1",
        text,
        count=1,
        flags=re.IGNORECASE,
    )

    opener = OPENERS[(s // 7) % len(OPENERS)]
    text = f"{opener} {text}"

    if "github.com/Nimrobo/superdense" not in text:
        text = text.rstrip(".") + ". Check it out!"

    return text


def main():
    targets = read_jsonl(C.TARGETS)
    targets_by_id = {row["id"]: row for row in targets}

    triples = []

    for target in targets:
        if not target.get("draft"):
            continue
        triples.append({
            "id": f"real-draft:{target['id']}",
            "context": target["context"],
            "draft": target["draft"],
            "final": target["final"],
        })

    for source_name, path in GENERATED_SOURCES:
        rows = read_jsonl(path)
        if not rows:
            sys.exit(f"missing generated rows: {path}")
        for row in rows:
            target_id = target_id_from_generated_id(row["id"])
            target = targets_by_id.get(target_id)
            if not target:
                sys.exit(f"{path}: cannot find target context for {row['id']}")
            rec_id = f"{source_name}:{row['id']}"
            final = row["generated"].strip()
            triples.append({
                "id": rec_id,
                "context": target["context"],
                "draft": make_draft(final, rec_id),
                "final": final,
            })

    seen = set()
    dupes = []
    for triple in triples:
        if triple["id"] in seen:
            dupes.append(triple["id"])
        seen.add(triple["id"])
    if dupes:
        sys.exit("duplicate triple ids:\n" + "\n".join(dupes[:20]))

    write_jsonl(C.TRIPLES, triples)
    counts = {
        "real_draft": sum(t["id"].startswith("real-draft:") for t in triples),
        "local_gen": sum(t["id"].startswith("local-") for t in triples),
        "gemini_gen": sum(t["id"].startswith("gemini-") for t in triples),
    }
    print(f"wrote {len(triples)} triples -> {C.TRIPLES}")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
