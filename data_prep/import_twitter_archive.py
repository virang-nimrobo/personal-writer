#!/usr/bin/env python3
"""Import a local Twitter/X archive into the core no-draft seed bank.

Reads data/raw/tweets.js or data/raw/tweet.js and writes:
  data_prep/core/no_draft.jsonl   {id, kind, context, final}
  data_prep/core/with_draft.jsonl empty file if it does not exist

The archive has only posted text, not the rough drafts that produced it, so every
imported row is a no-draft seed. Downstream generation creates off-voice drafts.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from config import C  # noqa: E402
from scripts._common import write_jsonl  # noqa: E402

CORE = HERE / "core"
NO_DRAFT = CORE / "no_draft.jsonl"
WITH_DRAFT = CORE / "with_draft.jsonl"

RT_PREFIX = re.compile(r"^RT @\w+:")
MENTION_PREFIX = re.compile(r"^@\w+\b")


def clean_text(value):
    text = str(value or "").replace("\r\n", "\n").strip()
    return re.sub(r"[ \t]+", " ", text)


def find_archive_file(raw_dir):
    candidates = (
        raw_dir / "tweets.js",
        raw_dir / "tweet.js",
        raw_dir / "data" / "tweets.js",
        raw_dir / "data" / "tweet.js",
    )
    for path in candidates:
        if path.exists():
            return path
    sys.exit(f"missing Twitter archive file under {raw_dir} (expected tweets.js or tweet.js)")


def load_tweets(path):
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"=\s*(\[.+\])\s*;?\s*$", raw, re.DOTALL)
    if not match:
        sys.exit(f"could not parse {path}: expected JS assignment wrapping a JSON array")

    items = json.loads(match.group(1))
    tweets = []
    for item in items:
        tweets.append(item.get("tweet", item))
    return tweets


def expand_urls(text, entities):
    for url_obj in entities.get("urls", []):
        short = url_obj.get("url", "")
        expanded = url_obj.get("expanded_url") or url_obj.get("display_url") or short
        if short and expanded:
            text = text.replace(short, expanded)
    return text


def strip_trailing_media_urls(text, entities):
    media_urls = {
        media.get("url")
        for media in entities.get("media", [])
        if media.get("url")
    }
    for short in sorted(media_urls, key=len, reverse=True):
        text = re.sub(rf"\s*{re.escape(short)}\s*$", "", text)
    return text.strip()


def visible_text(tweet):
    text = clean_text(tweet.get("full_text") or tweet.get("text"))
    entities = tweet.get("entities") or {}
    text = expand_urls(text, entities)
    text = strip_trailing_media_urls(text, entities)
    return clean_text(text)


def seed_kind_and_context(text):
    if MENTION_PREFIX.match(text):
        return "reply", "Write a reply."
    return "tweet", "Write an original tweet."


def build_rows(tweets, *, include_retweets, include_empty):
    rows = []
    seen = set()
    skipped = {
        "duplicate_id": 0,
        "empty_text": 0,
        "retweet": 0,
    }

    for tweet in tweets:
        tweet_id = clean_text(tweet.get("id_str") or tweet.get("id"))
        if not tweet_id:
            tweet_id = f"archive:{len(rows) + 1}"
        if tweet_id in seen:
            skipped["duplicate_id"] += 1
            continue
        seen.add(tweet_id)

        text = visible_text(tweet)
        if not text:
            skipped["empty_text"] += 1
            if not include_empty:
                continue

        if not include_retweets and (tweet.get("retweeted") is True or RT_PREFIX.match(text)):
            skipped["retweet"] += 1
            continue

        kind, context = seed_kind_and_context(text)
        rows.append({
            "id": f"tweet:{tweet_id}",
            "kind": kind,
            "context": context,
            "final": text,
        })

    return rows, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, default=C.RAW)
    ap.add_argument("--include-retweets", action="store_true")
    ap.add_argument("--include-empty", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    archive_file = find_archive_file(args.raw_dir)
    tweets = load_tweets(archive_file)
    rows, skipped = build_rows(
        tweets,
        include_retweets=args.include_retweets,
        include_empty=args.include_empty,
    )

    if args.dry_run:
        print(f"would write {len(rows)} rows -> {NO_DRAFT}")
    else:
        write_jsonl(NO_DRAFT, rows)
        if not WITH_DRAFT.exists():
            write_jsonl(WITH_DRAFT, [])
        print(f"wrote {len(rows)} rows -> {NO_DRAFT}")
        print(f"ensured {WITH_DRAFT}")

    print(f"source: {archive_file}")
    print("skipped: " + ", ".join(f"{key}={value}" for key, value in skipped.items()))


if __name__ == "__main__":
    main()
