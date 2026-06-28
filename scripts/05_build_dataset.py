#!/usr/bin/env python3
"""Landing-zone triplets -> MLX chat JSONL (train/valid/test).

mlx_lm.lora reads train.jsonl + valid.jsonl from a --data dir; we also emit test.jsonl for eval.
Split is deterministic (hash of record id) so re-runs are stable and the test set never leaks.

--records-only : just merge runs+archive into records_all.jsonl (no dataset build).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C          # noqa: E402
from _common import (  # noqa: E402
    active_landing_triplets,
    bucket,
    chat_record,
    read_jsonl,
    validate_triplets,
    write_jsonl,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records-only", action="store_true")
    args = ap.parse_args()

    if args.records_only:
        allrecs = read_jsonl(C.RECORDS_RUNS) + read_jsonl(C.RECORDS_ARCHIVE)
        write_jsonl(C.RECORDS_ALL, allrecs)
        print(f"merged -> {len(allrecs)} records -> {C.RECORDS_ALL}")
        return

    triples = active_landing_triplets(C)
    if not triples:
        sys.exit("no landing-zone triples - run data_prep/build_triplets.py first")

    errors = validate_triplets(triples)
    if errors:
        sys.exit("invalid triplets:\n" + "\n".join(errors[:50]))

    train, valid, test = [], [], []
    for t in triples:
        rec = chat_record(t["context"], t["draft"], t["final"])
        b = bucket(t["id"])
        (test if b == 0 else valid if b == 1 else train).append(rec)

    # tiny-data safety: never leave valid empty (mlx_lm requires it)
    if not valid and train:
        valid.append(train.pop())
    if not test and len(train) > 1:
        test.append(train.pop())

    write_jsonl(C.DATASET_TRAIN, train)
    write_jsonl(C.DATASET_VALID, valid)
    write_jsonl(C.DATASET_TEST, test)
    print(f"dataset: train={len(train)} valid={len(valid)} test={len(test)} -> {C.SYNTH}")


if __name__ == "__main__":
    main()
