# writer-model

A local personal writer that turns `{context, draft}` into a polished `final` in
Virang's voice.

The intended split is simple:

- A planner, human, or larger model decides the substance and writes a rough
  draft.
- `writer-model` owns the edit: voice, shape, wording, compression, and polish.
- The model must not invent facts, numbers, claims, or source material that are
  not supported by the context or draft.

## Repository Map

```text
data_prep/      source-of-truth training-data workflow
landing_zone/   generated handoff file consumed by training
training/       promote/evaluation notes and promotion helper
writer_model/   stable runtime package, CLI, API, and browser studio
use/            focused runtime examples
scripts/        implementation helpers for train/eval/infer
out/            local LoRA adapters and scorecards
data/           generated datasets, usage logs, feedback, and labels
```

## Data Contract

Every training and inference example has the same shape:

```json
{"context": "...", "draft": "...", "final": "..."}
```

For training rows, `id` is also required:

```json
{"id": "source:stable-id", "context": "...", "draft": "...", "final": "..."}
```

`context` should start with a terse directive naming the task or medium, then add
any source material the model is allowed to rely on.

Examples:

```text
Write an original tweet.
```

```text
Write a reply. Parent from @alice: shipping small deltas beats waiting for a grand rewrite.
```

```text
Write an email. To a collaborator about slipping the launch by one day because the eval is not clean yet.
```

`draft` is the rough or off-voice version to transform. `final` is the desired
output in the user's voice.

## Environment Setup

This project is designed for local macOS/Apple Silicon use with MLX.

Prerequisites:

- Python 3.10 or newer
- Apple Silicon Mac recommended for `mlx` / `mlx-lm`
- Enough free disk space for the base model and LoRA adapters
- Optional: `ANTHROPIC_API_KEY` if you run LLM-judge evaluation with `--judge`

Create the virtual environment and install dependencies:

```bash
make install
```

That creates `.venv/` and installs `requirements.txt`.

Install the package in editable mode if you want the console scripts
(`writer-model-edit` and `writer-model-studio`) on your PATH:

```bash
.venv/bin/python -m pip install -e .
```

If you skip the editable install, run the same tools as Python modules:

```bash
.venv/bin/python -m writer_model.cli --help
.venv/bin/python -m writer_model.studio --help
```

## Full Workflow

The normal lifecycle is:

```text
new examples, usage, or feedback
  -> update data_prep/core/*.jsonl
  -> scaffold a dated generation folder
  -> run model agents to produce off-voice drafts
  -> build landing_zone/triplets.jsonl
  -> train a candidate adapter
  -> evaluate the candidate
  -> promote if it does not regress
  -> use from CLI, API, or WebUI
  -> log usage/feedback for the next pass
```

## Stage 1: Build The Core Set

The durable seed bank lives in:

```text
data_prep/core/no_draft.jsonl
data_prep/core/with_draft.jsonl
```

Use `no_draft.jsonl` when you have a real final but no real rough draft:

```json
{"id": "tweet:0001", "kind": "tweet", "context": "Write an original tweet.", "final": "The finished piece in the user's voice."}
```

Use `with_draft.jsonl` when you have both a rough draft and the final:

```json
{"id": "email:0002", "kind": "email", "context": "Write an email. To Sam about moving the review to Friday.", "draft": "Hey Sam, maybe we should push the review because I need more time.", "final": "Hey Sam - can we move the review to Friday? I want one more pass before we make the call."}
```

See `data_prep/core/README.md` for the full schema and supported `kind` values.

## Stage 2: Scaffold Draft Generation

Build a dated generation folder from the core set:

```bash
.venv/bin/python data_prep/build_generation.py
```

Useful options:

```bash
.venv/bin/python data_prep/build_generation.py --date 2026-06-29 --chunk-size 10
.venv/bin/python data_prep/build_generation.py \
  --models codex gemma-4-12b-coder-fable5-composer2.5-v1 qwen3-8b-mlx
```

This creates:

```text
data_prep/generation-YYYY-MM-DD/
  codex/
    instruction.md
    inputs/*.input.jsonl
    outputs/
  gemini/
  sonnet/
  opus/
```

Model names are folder/config aliases. The default set is still
`codex gemini sonnet opus`, but you can add any model folder name. For local
OpenAI-compatible or MLX providers, configure aliases in:

```text
data_prep/draft_models.json
```

That file contains OpenAI-compatible provider settings for examples such as
Gemma via Ollama or LM Studio, plus MLX-backed local models.

To list configured local aliases:

```bash
make draft-models
```

Manual workflow: open each model folder and have that model's agent fill
`outputs/*.output.jsonl`. Each output row must contain only `id` and `draft`:

```json
{"id": "tweet:0001", "draft": "A plausible but off-voice draft with the same facts as the final."}
```

Automated local-model workflow: run the Makefile helper with a configured alias:

```bash
make draft-generation \
  MODEL=gemma-4-12b-coder-fable5-composer2.5-v1 \
  START=0 \
  END=10
```

By default, `GENERATION_DATE` is today. To rerun or backfill a specific dated
folder, pass it explicitly:

```bash
make draft-generation \
  MODEL=gemma-4-12b-coder-fable5-composer2.5-v1 \
  GENERATION_DATE=2026-06-29 \
  START=0 \
  END=10
```

The helper validates `MODEL` against `data_prep/draft_models.json`, scaffolds
`data_prep/generation-<date>/` for that model, then runs the draft generator:

```bash
.venv/bin/python data_prep/build_generation.py \
  --date 2026-06-29 \
  --models gemma-4-12b-coder-fable5-composer2.5-v1

.venv/bin/python data_prep/run_draft_generation.py \
  --model gemma-4-12b-coder-fable5-composer2.5-v1 \
  --generation-date 2026-06-29 \
  --start 0 \
  --end 10
```

The runner writes `outputs/<chunk>.output.jsonl`, preserves input ids/order, and
fails fast on invalid output instead of writing bad training data.

For long local-model runs, you can quarantine bad rows instead of stopping the
whole run. Valid rows are written normally; invalid rows go to
`outputs/_invalid_rows/<chunk>.output.invalid.jsonl` for manual review or a
second pass. The original input rows for those rejected rows are also written to
`outputs/_retry_inputs/<chunk>.input.retry.jsonl`:

```bash
.venv/bin/python data_prep/run_draft_generation.py \
  --model gemma4-26b \
  --generation-date 2026-06-30 \
  --start 25 \
  --end 2500 \
  --invalid-row-action skip \
  --overwrite
```

If a local server returns an empty chat message, the runner saves the full raw
response under `outputs/_raw_responses/` and exits with that path. To save raw
responses for every chunk while debugging a provider, pass `--raw-response-dir`:

```bash
.venv/bin/python data_prep/run_draft_generation.py \
  --model gemma4-26b \
  --generation-date 2026-06-30 \
  --start 0 \
  --end 0 \
  --raw-response-dir data_prep/debug/raw-responses
```

For thinking models that spend the whole completion budget in reasoning and
return empty content, disable thinking when the provider supports it:

```bash
.venv/bin/python data_prep/run_draft_generation.py \
  --model gemma4-26b \
  --generation-date 2026-06-30 \
  --start 0 \
  --end 0 \
  --think off \
  --max-tokens 2500 \
  --overwrite
```

LM Studio defaults to `http://localhost:1234/v1`; Ollama defaults to
`http://localhost:11434/v1`. Use `--base-url` for another machine:

```bash
.venv/bin/python data_prep/run_draft_generation.py \
  --model gemma3:27b \
  --provider ollama \
  --base-url http://laforge.local:11434/v1 \
  --generation-date 2026-06-29 \
  --start 0 \
  --end 10
```

For an MLX model:

```bash
.venv/bin/python data_prep/run_draft_generation.py \
  --model qwen3-8b-mlx \
  --generation-date 2026-06-29 \
  --start 0 \
  --end 10
```

## Stage 3: Build Triplets

After generated drafts exist, rebuild the unified landing-zone file:

```bash
.venv/bin/python data_prep/build_triplets.py
```

The script reads all core seeds and all `data_prep/generation-*/*/outputs/`
files, then overwrites:

```text
landing_zone/triplets.jsonl
```

Validate the landing zone any time:

```bash
.venv/bin/python scripts/validate_landing_zone.py
```

## Stage 4: Train

Train a candidate adapter:

```bash
make train
```

`make train` runs:

```text
scripts/validate_landing_zone.py
scripts/05_build_dataset.py
scripts/06_train_lora.sh
```

The dataset builder writes deterministic MLX splits to:

```text
data/synth/train.jsonl
data/synth/valid.jsonl
data/synth/test.jsonl
```

By default the Makefile writes the challenger to `out/editor-candidate`.
Override training parameters with environment variables:

```bash
ADAPTER=out/editor-candidate ITERS=600 BATCH=2 LAYERS=8 make train
```

For a tiny end-to-end sanity check:

```bash
make smoke
```

## Stage 5: Evaluate

Evaluate the candidate:

```bash
make eval
```

By default this evaluates `out/editor-candidate` and writes:

```text
out/editor-candidate/scorecard.json
```

Evaluate a specific adapter:

```bash
make eval EVAL_ADAPTER=out/editor-latest
```

Run the optional Anthropic judge metrics:

```bash
ANTHROPIC_API_KEY=... .venv/bin/python scripts/07_eval.py --adapter out/editor-candidate --judge
```

## Stage 6: Promote

Promote the candidate to `out/editor-latest` only if its scorecard does not
regress the champion:

```bash
make promote
```

Dry-run the promotion decision:

```bash
.venv/bin/python training/promote.py --candidate out/editor-candidate --champion out/editor-latest --dry-run
```

## Use From The CLI

With editable install:

```bash
writer-model-edit \
  --context "Write an original tweet. Topic: small models as personal editors." \
  --draft "Small models can be useful because they remember how you write and make text better." \
  --json
```

With files:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --json
```

With JSON on stdin:

```bash
printf '%s\n' '{"context":"Write a reply. Parent: local models are too much work.","draft":"I disagree, they are actually useful when scoped well.","metadata":{"thread":"demo"}}' \
  | writer-model-edit --stdin --json
```

Generate multiple candidates:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  -n 3 \
  --temp 0.9 \
  --max-tokens 220 \
  --json
```

Use a specific adapter or base model:

```bash
writer-model-edit \
  --adapter out/editor-latest \
  --base-model mlx-community/Qwen2.5-3B-Instruct-4bit \
  --context-file context.md \
  --draft-file draft.md
```

Raw usage appends to `data/usage/usage.jsonl` unless `--no-log` is passed.

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

Reviewed outcomes append to `data/feedback/feedback.jsonl`.

## Use From The WebUI

Launch the inference studio:

```bash
writer-model-studio --adapter out/editor-latest --port 7860
```

Or without editable install:

```bash
.venv/bin/python -m writer_model.studio --adapter out/editor-latest --port 7860
```

Open:

```text
http://localhost:7860
```

Paste a `context`, paste a `draft`, choose `n` and `temp`, then generate. The
studio logs usage with `source="studio"`.

To avoid auto-opening a browser:

```bash
writer-model-studio --adapter out/editor-latest --port 7860 --no-open
```

The older preference-labeling UI is still available for A/B labels:

```bash
make ui
```

That Gradio app reads queue items from `data/synth/triples.jsonl` and appends
labels to `data/prefs/prefs.jsonl`.

## Runtime Defaults

Defaults are centralized in `config.py` and read by `writer_model/settings.py`.

- Base model: `mlx-community/Qwen2.5-3B-Instruct-4bit`
- CLI/API default adapter: `out/editor-candidate`
- Promoted champion adapter: `out/editor-latest`
- Usage log: `data/usage/usage.jsonl`
- Feedback log: `data/feedback/feedback.jsonl`

Use `--adapter out/editor-latest` when you want the promoted champion rather
than the current candidate.

## Legacy Helpers

Some numbered scripts remain for compatibility and implementation detail:

- `scripts/06_train_lora.sh` runs MLX LoRA training.
- `scripts/07_eval.py` writes adapter scorecards.
- `scripts/08_infer.py` is a legacy inference entry point.
- `scripts/13_merge_generation_outputs.py` and `scripts/14_build_triples.py`
  belong to the old shard-based pipeline.

The current training source of truth is `landing_zone/triplets.jsonl`, rebuilt by
`data_prep/build_triplets.py`.
