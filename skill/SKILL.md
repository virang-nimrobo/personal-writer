---
name: writer-model-edit
description: Use this skill when the user wants to edit/rewrite a draft into Virang's voice with the local fine-tuned writer model — "run the writer model", "edit this tweet/reply", "turn this draft into the final", "writer-model-edit". Turns {context, draft} into a final piece.
metadata:
  author: nimrobo-ai
  version: "1.1"
compatibility: Requires the writer-model repo's .venv and a local adapter. Editable install exposes `writer-model-edit` and `writer-model-studio`; otherwise use `.venv/bin/python -m writer_model.cli` / `.venv/bin/python -m writer_model.studio`. Pass `--adapter out/editor-latest` for the promoted champion.
allowed-tools: Read, Write, Bash(writer-model-edit:*), Bash(writer-model-studio:*), Bash(.venv/bin/python -m writer_model.cli:*), Bash(.venv/bin/python -m writer_model.studio:*)
---

# writer-model-edit

A local fine-tuned editor model that turns `{context, draft}` into Virang's final
piece (tweet, reply, email, …). **You (the planner) own the substance and angle;
the model owns the edit — voice, structure, final wording.**

## When to use

The user has a rough/off-voice draft and wants it rewritten into their voice, or
asks to run the writer model on something.

Choose the path by job shape:

- **One-off edit** — run `writer-model-edit` or `.venv/bin/python -m writer_model.cli`.
- **Repeated/batch edits** — use the Python API and keep one `WriterEditor`
  loaded.
- **Interactive comparison** — launch `writer-model-studio`.
- **New training data / retrain loop** — use the Data Prep workflow, then train,
  evaluate, and promote.

## The input contract (get this right)

The model was trained on `{context, draft} → final` triples, so it only behaves
well when `context` and `draft` are shaped the way the training data is:

- **`context`** — non-empty, and **always leads with a terse directive naming the
  medium**, then the real source material. The directive is what tells the model
  *what is being written*. Examples:
  - `Write an original tweet. Topic: why we deleted the retrain folder`
  - `Write a reply. Parent from @alice: <full parent tweet text>`
  - `Write an email. To a candidate, scheduling a screening call.`
- **`draft`** — a rough first attempt carrying the same substance, facts, and
  numbers as the desired final. It can be generic, too long, too formal, or the
  wrong angle — that's fine, that's the model's job to fix.
- **Never invent facts, links, or numbers** that aren't in the context or draft.
  Output is **only the final text**.

## Run it

Run from the `writer-model` repo. Three input modes:

```bash
# files (best for multi-line content)
writer-model-edit --context-file context.md --draft-file draft.md

# inline
writer-model-edit --context "Write an original tweet. Topic: shipping fast" \
                  --draft "we should ship faster honestly it matters a lot"

# stdin JSON
echo '{"context":"…","draft":"…"}' | writer-model-edit --stdin --json
```

Without editable install:

```bash
.venv/bin/python -m writer_model.cli --context-file context.md --draft-file draft.md
```

Useful generation flags:

- `-n N` — generate N candidates. Candidate 1 is the stable/default choice.
- `--temp 0.7` — sampling temperature for exploratory candidates.
- `--max-tokens 160` — output budget.
- `--json` — print the full `EditResult` instead of just the final text.
- `--adapter out/editor-latest` — use the promoted champion adapter.
- `--base-model ...` — override the configured base model.
- `--no-log` — suppress usage logging for throwaway calls.

Useful provenance/logging flags:

- `--source`, `--run-id`, `--artifact-type` — tag where the call came from.
- `--metadata-json '{"key":"value"}'` — attach structured metadata.
- `--usage-path /tmp/usage.jsonl` — override the usage log path.
- `--feedback-path /tmp/feedback.jsonl` — override the feedback log path.

## Efficient repeated calls

For batch or tool integration work, do not start the CLI for every item. Load the
model once:

```python
from writer_model.api import WriterEditor

editor = WriterEditor(adapter_path="out/editor-latest")
editor.load()

result = editor.edit(
    context="Write a reply. Parent: small models are too limited.",
    draft="They are limited, but useful for narrow editing jobs.",
    n=2,
    temp=0.8,
    source="local-script",
    metadata={"thread": "demo"},
)

print(result.chosen_output)
```

For a single in-process call, `from writer_model.api import edit` is fine. For
many calls, `WriterEditor` is faster because it keeps the model and tokenizer
loaded.

## Browser studio

For interactive drafting, launch the studio:

```bash
writer-model-studio --adapter out/editor-latest --port 7860 --no-open
```

Without editable install:

```bash
.venv/bin/python -m writer_model.studio --adapter out/editor-latest --port 7860 --no-open
```

Open `http://localhost:7860`, paste `context` and `draft`, choose `n` and
`temp`, then copy the best candidate. Studio calls log usage with
`source="studio"`.

## Record feedback (feeds the next training pass)

When the user reviews an output, capture it so it can become new training data:

```bash
# kept as-is
writer-model-edit --context-file context.md --draft-file draft.md --feedback accepted

# user tweaked it — supply what they actually used
writer-model-edit --context-file context.md --draft-file draft.md \
  --feedback edited --final-used-file final.md

# rejected
writer-model-edit --context-file context.md --draft-file draft.md --feedback rejected
```

Notes:

- `--feedback accepted` uses the chosen output when no `--final-used` value is
  provided.
- `--feedback edited` requires `--final-used` or `--final-used-file`.
- Feedback rows include provenance fields, metadata, all outputs, the chosen
  output, and the final text the user actually used.

## Data Prep and retraining

When usage/feedback or new examples should improve the model, keep the skill's
job as orchestration and use the repo docs for details:

```bash
make draft-models

make draft-generation \
  MODEL=gemma-4-12b-coder-fable5-composer2.5-v1 \
  GENERATION_DATE=2026-06-29 \
  START=0 \
  END=10

.venv/bin/python data_prep/build_triplets.py
make train
make eval
make promote
```

Operational pointers:

- Core seed data lives under `data_prep/core/`.
- Generated draft rounds live under `data_prep/generation-YYYY-MM-DD/`.
- `data_prep/build_triplets.py` rebuilds `landing_zone/triplets.jsonl`.
- `make promote` updates `out/editor-latest` only after the candidate passes the
  promotion gate.

For long local draft-generation runs:

- Use `--invalid-row-action skip` to quarantine bad rows instead of stopping the
  whole run.
- Use `--raw-response-dir ...` when debugging provider responses.
- Use `--think off` for thinking models that return empty content because all
  budget went to reasoning.

## Output & logging

- Default prints just the final text; `--json` prints the full `EditResult`
  (all candidates, chosen output, adapter, metadata).
- Every call appends to `data/usage/usage.jsonl`; feedback appends to
  `data/feedback/feedback.jsonl`. These feed the Data Prep → retrain loop.

## Troubleshooting

- `writer-model-edit: command not found` — run `.venv/bin/python -m writer_model.cli`
  or install the repo editable with `.venv/bin/python -m pip install -e .`.
- `adapter not found` — pass `--adapter out/editor-latest`, train/promote a
  candidate, or use the configured candidate adapter if that is what you intend.
- Repeated calls are slow — switch from the CLI to `WriterEditor`.
- Output invents facts — fix the `context` and `draft`; the model may only use
  facts, numbers, and links present there.
- Draft generation writes bad local-model rows — rerun with
  `--invalid-row-action skip`, inspect `_invalid_rows/` and `_retry_inputs/`,
  and use `--raw-response-dir` for provider debugging.
