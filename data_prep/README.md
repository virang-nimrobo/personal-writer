# Data Prep

Data Prep is agent-managed. There is no broad `make data-prep` command, but the
Makefile has focused helpers for importing Twitter archives and running
configured draft-generation models.

The job of this area is to turn raw sources, generated samples, usage logs, and
human feedback into the unified `landing_zone/triplets.jsonl` training file.

## What the model is

The writer-model is a **personal writer**: a small local model that takes
`{context, draft}` and returns a polished `final` in the user's voice. The medium
is general — email, articles, tweets, and so on — but the contract is always the
same shape.

In use, a **large model produces `{context, draft}`** and this **small model
returns `final`**. Training rows are `{context, draft, final}` triplets.

The permanent output contract is:

```json
{"id": "...", "context": "...", "draft": "...", "final": "..."}
```

## The 3-step flow

Any user can build training data from this folder in three steps:

1. **Build the core set** — curate seeds into `core/` (the durable seed bank).
   See `core/README.md`.
2. **Build the generation folder** — derive a dated `generation-{date}/` from the
   core set, where configured models generate off-voice drafts. See *Draft
   generation* below.
3. **Build triplets** — run `build_triplets.py` to merge core seeds + generated
   drafts into the unified `landing_zone/triplets.jsonl`. See *Build triplets* below.

For a Twitter/X archive, drop `tweets.js` or `tweet.js` into `data/raw/`, then run:

```bash
make import-twitter
```

This writes posted tweets into `core/no_draft.jsonl` because the archive contains
final text but not the rough drafts that led to it.

After running `build_generation.py`, the importer can also create deterministic
draft output chunks for local bootstrapping:

```bash
.venv/bin/python data_prep/import_twitter_archive.py \
  --create-draft-outputs \
  --generation-date 2026-06-28 \
  --output-start 0 \
  --output-end 250
```

## The data model

Every training row is `{context, draft, final}`. The `final` is always the real
gold piece.

- **context — compulsory on every row.** It **always leads with a terse directive**
  that names the task/medium (`Write an original tweet.` / `Write a reply.` /
  `Write an email.` / `Write a paragraph.` …), so the model always knows *what is
  being written* at both training and inference time. When real source material
  exists (e.g. the parent of a reply), it is **appended after** the directive.
  The agent fills this in. For example:
  - a draftless original tweet → `"Write an original tweet."`
  - a reply with real context → `"Write a reply. Parent from @alice: parallel sub-agents reviewing a diff..."`
- **draft** — the real draft when it exists; otherwise **generated** (see below).
  Invent no facts not present in the final.
- **final** — always the real gold piece.

Every training row has a draft. Draftless seeds are not dropped — they get a
**synthesized draft** instead. Real triplets pass through as gold and also get
alternative drafts for diversity.

### Core set = 2 files (step 1)

Seeds are split by one question: **does a real draft already exist?**

```
data_prep/core/                    # stable, cumulative seed bank (grows over time)
  no_draft.jsonl                   # {id, kind, context, final}
  with_draft.jsonl                 # {id, kind, context, draft, final}
```

- `no_draft.jsonl` rows get a draft **generated** in step 2.
- `with_draft.jsonl` rows keep their real draft as gold **and** get alternative
  drafts in step 2.

See `core/README.md` for the field schema, `kind` values, the terse-directive
mapping, and worked examples.

## Draft generation (step 2)

Step 2 reads the core set and builds a dated `generation-{date}/`. Generation's
job is to **produce off-voice drafts**: a draft for every `no_draft` seed, and
alternative drafts for every `with_draft` seed. To get diverse, realistic
off-voice inputs, each seed can be run through any configured draft model. The
default folders are Codex, Gemini, Sonnet, and Opus. Local models such as Gemma
via LM Studio/Ollama, or MLX models via `mlx_lm`, can be added with `--models`.

Context is already resolved in the core set (step 1's job — terse directive with
real material appended, non-negotiable). Step 2 takes it as-is: it emits generation
inputs `{id, context, final}` straight from the core rows and chunks them. The same
chunks go into every requested model folder.

An **off-voice draft** carries the same substance, facts, and numbers as the
`final`, but is clearly *not yet in voice*: generic, too long, too formal, too
hype, or the wrong angle. The `final` is the voice exemplar to deviate *from*.
Direction is kept light so different models diverge.

### Handoff structure

This mirrors the proven folder handoff pattern: many input chunks per folder,
**one worker per chunk**, each owning one output file.

```
data_prep/generation-{date}/
  README.md
  codex/                    instruction.md  inputs/*.input.jsonl  outputs/*.output.jsonl
  gemma-4-12b-coder-fable5-composer2.5-v1/  ...
  qwen3-8b-mlx/             ...
```

- `instruction.md` is **identical** in all folders; the folder name signals which
  model or runner config runs there.
- Manual mode: a human opens a model folder and runs that model's agent. It fans
  out one worker per `inputs/*.input.jsonl` chunk; each worker writes exactly one
  `outputs/<chunk>.output.jsonl` and never cross-writes another worker's file.
- Automated mode: configure a local draft model in
  `data_prep/draft_models.json`. List configured aliases with:

  ```bash
  make draft-models
  ```

  Then run the Makefile helper:

  ```bash
  make draft-generation \
    MODEL=gemma-4-12b-coder-fable5-composer2.5-v1 \
    GENERATION_DATE=2026-06-28 \
    START=0 \
    END=250
  ```

  `GENERATION_DATE` defaults to today when omitted. The helper validates `MODEL`
  against `data_prep/draft_models.json`, runs `build_generation.py --date
  <date> --models <model>`, then runs:

  ```bash
  .venv/bin/python data_prep/run_draft_generation.py \
    --model gemma-4-12b-coder-fable5-composer2.5-v1 \
    --generation-date 2026-06-28 \
    --start 0 \
    --end 250
  ```

  The runner validates exact ids, schema, non-empty drafts, and `draft != final`
  before writing each output chunk. Existing outputs are not overwritten unless
  `--overwrite` is passed.

  By default, invalid rows fail the chunk so bad training data is not written.
  For long local-model runs, pass `--invalid-row-action skip` to write valid rows
  normally and quarantine rejected rows under `outputs/_invalid_rows/` for
  manual review. The original input rows for rejected rows are also written under
  `outputs/_retry_inputs/` for a second model pass.

  If the provider responds with an empty chat message, the runner saves the full
  response under `outputs/_raw_responses/` and exits with that path. Use
  `--raw-response-dir <dir>` to capture every raw provider response during
  debugging.

  Thinking models may put all generated text into a provider-specific reasoning
  field and never emit final JSONL, especially when `finish_reason` is `length`.
  For providers that support it, retry with `--think off`.

### Draft model config

Automated draft generation reads `data_prep/draft_models.json`. Each key is both
the model folder name and the `--model` value. `openai-compatible` entries call
LM Studio, Ollama, or similar servers; `mlx` entries run through `mlx_lm`.

```json
{
  "models": {
    "gemma-4-12b-coder-fable5-composer2.5-v1": {
      "backend": "openai-compatible",
      "provider": "LM Studio (local)",
      "base_url": "http://localhost:1234/v1",
      "model": "gemma-4-12b-coder-fable5-composer2.5-v1",
      "temperature": 0.8,
      "max_tokens": 220
    }
  }
}
```

LM Studio defaults to `http://localhost:1234/v1`; Ollama defaults to
`http://localhost:11434/v1`. For ad hoc models that are not in the config:

```bash
.venv/bin/python data_prep/run_draft_generation.py \
  --model gemma3:27b \
  --provider ollama \
  --base-url http://laforge.local:11434/v1 \
  --generation-date 2026-06-28 \
  --start 0 \
  --end 10
```

For MLX:

```bash
.venv/bin/python data_prep/run_draft_generation.py \
  --model qwen3-8b-mlx \
  --generation-date 2026-06-28 \
  --start 0 \
  --end 10
```

Schemas:

- **Generation input** row — context is pre-resolved (terse directive, with real
  material appended), `final` is the gold target:

  ```json
  {"id": "...", "context": "...", "final": "..."}
  ```

- **Generation output** row — the off-voice draft only; preserve `id` exactly, no
  other fields:

  ```json
  {"id": "...", "draft": "..."}
  ```

After generation, drafts are merged back with their `{context, final}` seeds to
form `{context, draft, final}` triplets for the landing zone — that's step 3.

## Build triplets (step 3)

Step 3 is a deterministic **full rebuild**: `data_prep/build_triplets.py`. It reads
the whole core set + **all** `generation-*` rounds, joins each core seed with its
generated drafts, and **overwrites one unified file**, `landing_zone/triplets.jsonl`.

```bash
python3 data_prep/build_triplets.py
```

No arguments, no shards, no manifest, no active flag. Models are auto-discovered
(any `generation-*/<model>/outputs/` folder). Because it rebuilds from source and
dedups by id, **re-running can't double rows** — it just reproduces the same file.

`context` and `final` always come from the core seed; only `draft` varies. The id
scheme keeps every row unique and traceable to its source:

- each `with_draft` seed → a **gold** row `{id: "real:<id>", draft: <real draft>}`
- each model's draft of a seed → `{id: "<model>:<id>", draft: <generated draft>}`
  (`no_draft` seeds get only model rows; `with_draft` seeds get gold + alt-draft rows)

The script validates required fields, duplicate ids, and `draft != final` before
writing. Training reads `landing_zone/triplets.jsonl` directly.

> The old `scripts/13_merge_generation_outputs.py` + `scripts/14_build_triples.py`,
> and the `landing_zone/triplets/` shards + `manifest.json`, are **legacy** (the old
> shard/active design). `build_triplets.py` + the unified file supersede them.

## Durable handoff

The durable handoff is the single unified file:

- `data_prep/build_triplets.py` overwrites `landing_zone/triplets.jsonl`.
- `scripts/05_build_dataset.py` reads it directly to build the MLX train/valid/test splits.
- Validate any time with `python3 scripts/validate_landing_zone.py`.

See `triplets.md` for the row contract and `retrain.md` for the feedback loop.
