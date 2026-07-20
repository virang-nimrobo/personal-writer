# Training

Training is Make-driven and consumes the unified landing-zone file:

```text
landing_zone/triplets.jsonl
```

That file is rebuilt by:

```bash
.venv/bin/python data_prep/build_triplets.py
```

The legacy `landing_zone/manifest.json` and `landing_zone/triplets/` shard flow
is no longer the primary path.

## Setup

From the repository root:

```bash
make install
```

Optional, but useful for runtime CLI commands:

```bash
.venv/bin/python -m pip install -e .
```

## Train

```bash
make train
```

This validates the landing zone, builds MLX chat data, then trains a LoRA
adapter.

Equivalent stages:

```bash
.venv/bin/python scripts/validate_landing_zone.py
.venv/bin/python scripts/05_build_dataset.py
ADAPTER=out/editor-candidate bash scripts/06_train_lora.sh
```

Outputs:

```text
data/synth/train.jsonl
data/synth/valid.jsonl
data/synth/test.jsonl
out/editor-candidate/
```

Common overrides:

```bash
ADAPTER=out/editor-candidate ITERS=600 BATCH=2 LAYERS=8 MAXSEQ=512 make train
```

Tiny smoke run:

```bash
make smoke
```

## Eval

```bash
make eval
```

By default, `make eval` evaluates `out/editor-candidate` and writes:

```text
out/editor-candidate/scorecard.json
```

Evaluate another adapter:

```bash
make eval EVAL_ADAPTER=out/editor-latest
```

Run optional LLM judge metrics:

```bash
ANTHROPIC_API_KEY=... .venv/bin/python scripts/07_eval.py --adapter out/editor-candidate --judge
```

The scorecard includes deterministic gate pass rate and embedding similarity
when `sentence-transformers` is installed. With `--judge`, it also includes voice
win rate and hallucination rate.

## Promote

```bash
make promote
```

Promotion compares:

```text
out/editor-candidate/scorecard.json
out/editor-latest/scorecard.json
```

If there is no champion scorecard yet, the candidate can promote. Otherwise,
promotion only proceeds when the candidate does not regress gate pass rate and
wins any comparable tie-break metrics.

Dry-run:

```bash
.venv/bin/python training/promote.py --candidate out/editor-candidate --champion out/editor-latest --dry-run
```

## Runtime After Training

Use the promoted adapter:

```bash
writer-model-edit \
  --adapter out/editor-latest \
  --context-file context.md \
  --draft-file draft.md
```

Launch the inference studio:

```bash
writer-model-studio --adapter out/editor-latest --port 7860
```

Note: the package default adapter is currently `out/editor-candidate`; pass
`--adapter out/editor-latest` when you specifically want the promoted champion.
