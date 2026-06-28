#!/usr/bin/env python3
"""Build minimal trusted SFT targets from training_data_raw.json.

Output rows are intentionally small:
  {id, context, draft, final}

`draft` is only kept when it is a true LLM draft from the Xgrowth workflow.
Timeline-fetched rows copy real_post_text into draft, so those become draft=null
and get synthetic drafts later.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C  # noqa: E402
from scripts._common import write_jsonl  # noqa: E402

RAW_EXPORT = C.ROOT / "training_data_raw.json"
TIMELINE_RUN_ID = "timeline-fetch-2026-06-16"
LINK_RESOLUTIONS = C.CURATED / "link_resolutions.json"


def clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_link_resolutions():
    if not LINK_RESOLUTIONS.exists():
        return {}
    return json.loads(LINK_RESOLUTIONS.read_text())


def expand_links(text, resolutions):
    if not text:
        return text
    for src, dst in resolutions.items():
        text = text.replace(src, dst)
    return text


def row_kind(row):
    if row.get("run_id") != TIMELINE_RUN_ID:
        return "workflow"
    if row.get("type") == "post":
        return "quote"
    return "timeline_reply"


def build_context(row):
    parent = clean_text(row.get("parent_text"))
    if not parent:
        return None
    author = clean_text(row.get("parent_author"))
    if author:
        return f"Reply to @{author}. Parent: {parent}"
    return f"Reply to this post. Parent: {parent}"


def main():
    if not RAW_EXPORT.exists():
        sys.exit(f"missing {RAW_EXPORT}")

    data = json.loads(RAW_EXPORT.read_text())
    rows = data.get("training_data") or []
    link_resolutions = load_link_resolutions()

    targets = []
    seen_tweet_ids = set()
    skipped = {
        "not_posted": 0,
        "missing_final": 0,
        "missing_context": 0,
        "duplicate_tweet_id": 0,
    }

    for row in rows:
        if not row.get("was_posted"):
            skipped["not_posted"] += 1
            continue

        final = expand_links(clean_text(row.get("real_post_text")), link_resolutions)
        if not final:
            skipped["missing_final"] += 1
            continue

        context = expand_links(build_context(row), link_resolutions)
        if not context:
            skipped["missing_context"] += 1
            continue

        tweet_id = clean_text(row.get("real_tweet_id"))
        if tweet_id and tweet_id in seen_tweet_ids:
            skipped["duplicate_tweet_id"] += 1
            continue
        if tweet_id:
            seen_tweet_ids.add(tweet_id)

        kind = row_kind(row)
        draft = clean_text(row.get("draft")) if kind == "workflow" else None
        draft = expand_links(draft, link_resolutions)
        targets.append({
            "id": f"tweet:{tweet_id}" if tweet_id else f"raw:{len(targets) + 1}",
            "context": context,
            "draft": draft,
            "final": final,
        })

    write_jsonl(C.TARGETS, targets)

    with_draft = sum(bool(t["draft"]) for t in targets)
    without_draft = len(targets) - with_draft
    print(f"wrote {len(targets)} targets -> {C.TARGETS}")
    print(f"with real draft={with_draft}, needs synthetic draft={without_draft}")
    print("skipped: " + ", ".join(f"{k}={v}" for k, v in skipped.items()))


if __name__ == "__main__":
    main()
