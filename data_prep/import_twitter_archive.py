#!/usr/bin/env python3
"""Import a local Twitter/X archive into the core no-draft seed bank.

Reads data/raw/tweets.js or data/raw/tweet.js and writes:
  data_prep/core/no_draft.jsonl   {id, kind, context, final}
  data_prep/core/with_draft.jsonl empty file if it does not exist

The archive has only posted text, not the rough drafts that produced it, so every
imported row is a no-draft seed. Downstream generation creates off-voice drafts.

Optionally, this can also create deterministic draft-generation output files for
an existing data_prep/generation-*/<model>/inputs directory:
  data_prep/generation-*/<model>/outputs/*.output.jsonl   {id, draft}
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from config import C  # noqa: E402
from scripts._common import write_jsonl  # noqa: E402

CORE = HERE / "core"
NO_DRAFT = CORE / "no_draft.jsonl"
WITH_DRAFT = CORE / "with_draft.jsonl"
DEFAULT_MODEL = "codex"

RT_PREFIX = re.compile(r"^RT @\w+:")
MENTION_PREFIX = re.compile(r"^@\w+\b")


def clean_text(value):
    text = str(value or "").replace("\r\n", "\n").strip()
    return re.sub(r"[ \t]+", " ", text)


def one_line(text):
    text = str(text or "").replace("\r\n", "\n").strip()
    text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    return text.strip()


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


def split_handles(text):
    handles = []
    rest = text.strip()
    while True:
        match = re.match(r"^(@[A-Za-z0-9_]+)\s+", rest)
        if not match:
            break
        handles.append(match.group(1))
        rest = rest[match.end():].strip()
    return " ".join(handles), rest


def soften(text):
    replacements = [
        (r"\bcan't\b", "cannot"),
        (r"\bdon't\b", "do not"),
        (r"\bdoesn't\b", "does not"),
        (r"\bwon't\b", "will not"),
        (r"\bit's\b", "it is"),
        (r"\bthat's\b", "that is"),
        (r"\byou're\b", "you are"),
        (r"\bI'm\b", "I am"),
        (r"\bI've\b", "I have"),
        (r"\bdoesn’t\b", "does not"),
        (r"\bdon’t\b", "do not"),
        (r"\bcan’t\b", "cannot"),
        (r"\byou’re\b", "you are"),
        (r"\bIt’s\b", "It is"),
        (r"\bThey're\b", "They are"),
    ]
    out = text
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def draft_for(row, variant):
    final = one_line(row["final"])
    handles, body = split_handles(final)
    body = soften(body)

    if not body:
        body = final

    if len(body) < 90:
        templates = [
            "I think the main point is that {body}",
            "Basically, {body}",
            "The way I would say it is: {body}",
            "My rough take is that {body}",
        ]
    elif "?" in body:
        templates = [
            "I would frame the question this way: {body}",
            "The practical question here is: {body}",
            "A clearer way to ask this is: {body}",
            "The issue I am trying to raise is: {body}",
        ]
    else:
        templates = [
            "The point I am trying to make is that {body}",
            "A more explicit version would be: {body}",
            "I think this is mainly about the fact that {body}",
            "In plain terms, {body}",
        ]

    draft = templates[variant % len(templates)].format(body=body)
    draft = one_line(draft)
    if handles:
        draft = f"{handles} {draft}"
    return draft


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


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def resolve_generation_dir(args):
    if args.generation_dir:
        return args.generation_dir
    return HERE / f"generation-{args.generation_date}"


def input_indexes(inputs_dir):
    indexes = []
    for path in sorted(inputs_dir.glob("*.input.jsonl")):
        try:
            indexes.append(int(path.stem.split(".")[0]))
        except ValueError:
            continue
    return indexes


def write_draft_outputs(args):
    gen_dir = resolve_generation_dir(args)
    model_dir = gen_dir / args.model
    inputs_dir = model_dir / "inputs"
    outputs_dir = model_dir / "outputs"

    if not inputs_dir.exists():
        sys.exit(
            f"missing generation inputs: {inputs_dir} "
            "(run data_prep/build_generation.py first)"
        )

    indexes = input_indexes(inputs_dir)
    if not indexes:
        sys.exit(f"no input chunks found under {inputs_dir}")

    start = args.output_start if args.output_start is not None else min(indexes)
    end = args.output_end if args.output_end is not None else max(indexes)
    selected = [idx for idx in indexes if start <= idx <= end]
    if not selected:
        sys.exit(f"no input chunks found in range {start:03d}..{end:03d}")

    written = 0
    rows_written = 0
    if not args.dry_run:
        outputs_dir.mkdir(parents=True, exist_ok=True)

    for idx in selected:
        input_path = inputs_dir / f"{idx:03d}.input.jsonl"
        output_path = outputs_dir / f"{idx:03d}.output.jsonl"
        rows = read_jsonl(input_path)
        output_rows = [
            {"id": row["id"], "draft": draft_for(row, idx + pos)}
            for pos, row in enumerate(rows)
        ]
        if not args.dry_run:
            write_jsonl(output_path, output_rows)
        written += 1
        rows_written += len(output_rows)

    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} output files, {rows_written} draft rows -> {outputs_dir}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, default=C.RAW)
    ap.add_argument("--include-retweets", action="store_true")
    ap.add_argument("--include-empty", action="store_true")
    ap.add_argument("--create-draft-outputs", action="store_true")
    ap.add_argument("--generation-date", default=date.today().isoformat())
    ap.add_argument("--generation-dir", type=Path, default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--output-start", type=int, default=None)
    ap.add_argument("--output-end", type=int, default=None)
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

    if args.create_draft_outputs:
        write_draft_outputs(args)


if __name__ == "__main__":
    main()
