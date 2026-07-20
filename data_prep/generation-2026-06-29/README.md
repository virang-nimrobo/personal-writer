# Generation 2026-06-29

Step-2 draft generation derived from the core set. Each `no_draft` seed (and each
`with_draft` seed, for an alternative draft) can get an **off-voice draft** from
any configured model folder below. All folders share identical inputs and
`instruction.md`; the folder name signals which model or runner config runs there.

```
glm-4.7-mlx/
```

## Run a model manually

Open one folder and run that model's agent. Fan out **one sub-agent per chunk**
(`inputs/000.input.jsonl` -> `outputs/000.output.jsonl`); never let two sub-agents
write the same output file. Output rows are `{"id": "...", "draft": "..."}` only.

## Run a configured local model

For configured local providers (for example LM Studio, Ollama, or MLX), add a
matching entry in `data_prep/draft_models.json`. From the repo root, list
available aliases with:

```bash
make draft-models
```

Then run this model with the Makefile helper:

```bash
make draft-generation \
  MODEL=<folder-name> \
  GENERATION_DATE=2026-06-29 \
  START=0 \
  END=10
```

`GENERATION_DATE` defaults to today when omitted. The helper validates `MODEL`,
scaffolds this generation folder with `build_generation.py --date <date>
--models <model>`, then runs:

```bash
.venv/bin/python data_prep/run_draft_generation.py \
  --model <folder-name> \
  --generation-date 2026-06-29 \
  --start 0 \
  --end 10
```

The runner validates that every output row has exactly `id` and `draft`, preserves
input ids/order, and rejects empty drafts or drafts that equal the final text.

Input rows (25906 total, 2591 chunks of <= 10):

```json
{"id": "...", "context": "...", "final": "..."}
```

## After generation

```bash
python3 data_prep/build_triplets.py        # step 3: merge -> landing_zone/triplets.jsonl
```

`build_triplets.py` auto-discovers any `<model>/outputs/` here, so you can run a
subset of the four folders and still build — only the models you ran contribute.
