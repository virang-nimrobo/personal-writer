# Retrain Workflow

Retrain is not a separate folder or Make target. It is this loop:

1. Review `data/usage/usage.jsonl`, `data/feedback/feedback.jsonl`, and any new
   external source data.
2. Add seeds to `core/`, generate drafts, then run `data_prep/build_triplets.py`
   (steps 1–3 in `README.md`). It rebuilds `landing_zone/triplets.jsonl` from the
   whole core set + all generation rounds.
3. Run `make train`.
4. Run `make eval ADAPTER=out/editor-candidate` or evaluate the configured
   challenger adapter.
5. Run `make promote` only when the challenger scorecard is acceptable.

The core set is cumulative, so each rebuild includes all prior seeds plus the new
ones — no shards to track, no active flags to flip.
