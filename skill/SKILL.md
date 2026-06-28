---
name: writer-model-edit
description: Use this skill when the user wants to edit/rewrite a draft into Virang's voice with the local fine-tuned writer model — "run the writer model", "edit this tweet/reply", "turn this draft into the final", "writer-model-edit". Turns {context, draft} into a final piece.
metadata:
  author: nimrobo-ai
  version: "1.0"
compatibility: Requires the writer-model repo's .venv with `writer-model-edit` on PATH and a promoted adapter at out/editor-latest (run `make promote` once).
allowed-tools: Read, Write, Bash(writer-model-edit:*)
---

# writer-model-edit

A local fine-tuned editor model that turns `{context, draft}` into Virang's final
piece (tweet, reply, email, …). **You (the planner) own the substance and angle;
the model owns the edit — voice, structure, final wording.**

## When to use

The user has a rough/off-voice draft and wants it rewritten into their voice, or
asks to run the writer model on something.

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

Useful flags: `-n N` (generate N candidates), `--temp 0.7`, `--max-tokens 160`,
`--json` (print the full result instead of just the final text).

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

## Output & logging

- Default prints just the final text; `--json` prints the full `EditResult`
  (all candidates, chosen output, adapter, metadata).
- Every call appends to `data/usage/usage.jsonl`; feedback appends to
  `data/feedback/feedback.jsonl`. These feed the Data Prep → retrain loop.
