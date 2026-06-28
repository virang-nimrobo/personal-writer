# writer-model

A local editor model that turns `{context, draft}` into Virang's final tweet.
Claude or another planner owns the substance and angle. This model owns the edit:
voice, structure, and final wording.

The repo is organized around three operating areas:

```text
data_prep/      agent-managed instructions for preparing training triplets
landing_zone/   append-only handoff from Data Prep to Training
training/       deterministic train/eval/promote operations
use/            runtime and feedback-capture notes
```

## Core Contract

Data Prep publishes immutable JSONL shards under `landing_zone/triplets/`.
Each row is one editor triplet:

```json
{"id": "...", "context": "...", "draft": "...", "final": "..."}
```

`landing_zone/manifest.json` is the source of truth for which shards are active.
Training consumes all entries with `active: true`.

## Workflow

```text
new data / usage / feedback
  -> Data Prep agent creates a triplet shard
  -> landing_zone manifest marks it active
  -> make train
  -> make eval
  -> make promote
  -> use via writer-model-edit / writer_model
  -> usage + feedback feeds the next Data Prep pass
```

Retraining is governed by `data_prep/retrain.md`. There is no `retrain/` folder
and no `make retrain` target.

## Commands

```bash
make install
make train                 # builds MLX data from active landing-zone shards, trains candidate
make eval                  # evaluates out/editor-candidate by default
make promote               # promotes candidate to out/editor-latest if gates do not regress
```

For quick legacy validation:

```bash
make smoke
```

## Use

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --json
```

Record reviewed feedback at use time:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --feedback accepted
```

For edited output:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --feedback edited \
  --final-used-file final.md
```

Raw calls append to `data/usage/usage.jsonl`. Reviewed outcomes append to
`data/feedback/feedback.jsonl`.

## Existing Helpers

The old numbered scripts remain available as helper implementation details.
They are intentionally not the main mental model anymore:

- parsing and synthesis helpers live in `scripts/`
- LoRA training still uses `scripts/06_train_lora.sh`
- evaluation still uses `scripts/07_eval.py`
- the stable runtime package is `writer_model`
