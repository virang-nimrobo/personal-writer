#!/usr/bin/env python3
"""Promote a challenger adapter when it does not regress scorecard gates."""

import argparse
import json
import shutil
import sys
from pathlib import Path


def load_scorecard(adapter):
    path = Path(adapter) / "scorecard.json"
    if not path.exists():
        raise FileNotFoundError(f"missing scorecard: {path}")
    return json.loads(path.read_text())


def better(candidate, champion):
    if champion is None:
        return True
    if candidate["gate_pass_rate"] < champion["gate_pass_rate"]:
        return False
    for key in ("voice_winrate_vs_draft", "similarity"):
        cand_val = candidate.get(key)
        champ_val = champion.get(key)
        if cand_val is not None and champ_val is not None and cand_val != champ_val:
            return cand_val > champ_val
    return candidate["gate_pass_rate"] > champion["gate_pass_rate"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default="out/editor-candidate")
    ap.add_argument("--champion", default="out/editor-latest")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    candidate_path = Path(args.candidate)
    champion_path = Path(args.champion)
    candidate = load_scorecard(candidate_path)
    champion = load_scorecard(champion_path) if (champion_path / "scorecard.json").exists() else None

    if not better(candidate, champion):
        champ_gate = champion and champion.get("gate_pass_rate")
        print(
            "kept champion: "
            f"candidate gate={candidate.get('gate_pass_rate')} "
            f"champion gate={champ_gate}"
        )
        return 1

    print(f"promote {candidate_path} -> {champion_path}")
    if args.dry_run:
        return 0

    if not candidate_path.exists():
        sys.exit(f"candidate adapter does not exist: {candidate_path}")
    if champion_path.exists():
        shutil.rmtree(champion_path)
    shutil.copytree(candidate_path, champion_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
