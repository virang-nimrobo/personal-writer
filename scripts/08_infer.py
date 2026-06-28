#!/usr/bin/env python3
"""Serving entrypoint: {context, draft} -> final tweet.

Usage:
  python3 scripts/08_infer.py --context "..." --draft "..."        # one-off
  echo '{"context":"...","draft":"..."}' | python3 scripts/08_infer.py --stdin
  python3 scripts/08_infer.py --smoke                              # run on a held-out test triple
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C          # noqa: E402
from _common import read_jsonl, bucket  # noqa: E402
from editor import load_editor, generate_final  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context")
    ap.add_argument("--draft")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("-n", type=int, default=1)
    args = ap.parse_args()

    adapter = args.adapter or ("out/smoke" if args.smoke else "out/editor-latest")
    if not Path(adapter).exists():
        sys.exit(f"adapter not found: {adapter} (train first)")

    if args.smoke:
        test = [t for t in read_jsonl(C.TRIPLES) if bucket(t["id"]) == 0] or read_jsonl(C.TRIPLES)
        item = test[0]
        ctx, draft, gold = item["context"], item["draft"], item["final"]
    elif args.stdin:
        d = json.loads(sys.stdin.read())
        ctx, draft, gold = d["context"], d["draft"], d.get("final")
    else:
        if not (args.context and args.draft):
            sys.exit("provide --context and --draft (or --stdin / --smoke)")
        ctx, draft, gold = args.context, args.draft, None

    print(f"loading {C.BASE_MODEL} + adapter {adapter} ...", file=sys.stderr)
    model, tok = load_editor(adapter_path=adapter)
    outs = generate_final(model, tok, ctx, draft, n=max(1, args.n))

    print("\n=== DRAFT ===\n" + draft)
    for i, o in enumerate(outs, 1):
        print(f"\n=== EDITOR{(' #'+str(i)) if len(outs)>1 else ''} ===\n{o}")
    if gold:
        print("\n=== GOLD (real tweet) ===\n" + gold)


if __name__ == "__main__":
    main()
