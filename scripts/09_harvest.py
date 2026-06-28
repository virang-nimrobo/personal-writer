#!/usr/bin/env python3
"""Harvest preference pairs from Xgrowth runs -> data/feedback/feedback.jsonl (the flywheel fuel).

Two sources of {chosen, rejected} edit-pairs:
  1. posts.md `~~superseded~~` drafts vs the chosen final  (available now; real human edits)
  2. reconcile.json (when present): the editor's draft vs what you actually posted  (Phase 2 live loop)

Each pair: {id, context, chosen, rejected, source, run_id}. Deduped by (chosen, rejected) hash so
re-running is idempotent. Feeds the DPO dataset (10_train_dpo.sh) and the retrain loop (11).
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C          # noqa: E402
from _common import read_jsonl, write_jsonl  # noqa: E402

FEEDBACK_FILE = C.FEEDBACK / "feedback.jsonl"


def pair_key(chosen, rejected):
    return hashlib.md5((chosen.strip() + "||" + rejected.strip()).encode()).hexdigest()


def pairs_from_records():
    """Edit-pairs from the run records' `rejected` spans (superseded posts.md drafts)."""
    pairs = []
    for r in read_jsonl(C.RECORDS_RUNS):
        for rej in r.get("rejected", []):
            if rej and len(rej) >= 20 and rej.strip() != r["final"].strip():
                pairs.append({
                    "id": r["id"], "context": r["context"],
                    "chosen": r["final"], "rejected": rej,
                    "source": "edit", "run_id": r.get("run_id"),
                })
    return pairs


def pairs_from_reconcile():
    """Placeholder for the live loop: match editor draft -> posted text via reconcile.json.

    Populated in Phase 2 once the editor runs inside Xgrowth and runs persist reconcile.json with
    {draft_text, posted_text} (or draft->tweet-id resolvable to posted text).
    """
    pairs = []
    for loop in C.LOOP_DIRS:
        for rec in sorted((loop / "runs").glob("*/reconcile.json")):
            try:
                data = json.loads(rec.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            for m in (data.get("matches") or []):
                d, p = (m.get("draft") or "").strip(), (m.get("posted") or "").strip()
                if d and p and d != p and len(p) >= 20:
                    pairs.append({
                        "id": f"reconcile:{rec.parent.name}:{pair_key(p, d)[:8]}",
                        "context": m.get("context", ""), "chosen": p, "rejected": d,
                        "source": "reconcile", "run_id": rec.parent.name,
                    })
    return pairs


def main():
    existing = read_jsonl(FEEDBACK_FILE)
    seen = {pair_key(p["chosen"], p["rejected"]) for p in existing}

    new = []
    for p in pairs_from_records() + pairs_from_reconcile():
        k = pair_key(p["chosen"], p["rejected"])
        if k not in seen:
            seen.add(k)
            new.append(p)

    write_jsonl(FEEDBACK_FILE, existing + new)
    print(f"harvested {len(new)} new pairs (total {len(existing) + len(new)}) -> {FEEDBACK_FILE}")


if __name__ == "__main__":
    main()
