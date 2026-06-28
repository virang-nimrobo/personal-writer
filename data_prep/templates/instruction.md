# Draft Generation Worker Instructions

You are generating **training data** for the writer-model, a small **personal writer** that takes
`{context, draft}` and returns a polished `final` in the user's voice (email, articles, tweets, etc.).

The `final` is already written — it is the real, gold piece in the user's voice. Your job is to produce
the **rough, off-voice DRAFT** that the writer would have turned into that final. You are working
backwards from the answer.

This folder is one of four (`codex/`, `gemini/`, `sonnet/`, `opus/`). The instructions are identical;
the folder name tells you which model should run here. Run **one sub-agent per input chunk** so the
four models each produce their own diverse drafts.

## What you produce

For each input row you write exactly one off-voice draft. The draft must:

- carry the **same substance, facts, and numbers** as the `final` — invent nothing not present in it,
- be clearly **off-voice**: not yet in the user's voice. Pick a realistic failure mode and commit to it
  — generic / too long / too formal / too hype / wrong angle / buried point / marketing filler.
- read like a plausible rough first attempt that a person or a large model would actually write before
  editing.

Keep direction light. Do not converge on one template — your job is to add variety, so the writer
sees many shapes of bad input mapping to the same good final. The `final` itself is the voice to
deviate *from*.

Do **not** rewrite the final, polish it, or copy it. If your draft already reads like the final, it is
wrong — make it rougher.

## Input

`inputs/*.input.jsonl` — one JSON object per line. `context` is already resolved: it always leads
with a terse directive (`Write an original tweet.` / `Write a reply.` / `Write an email.` /
`Write a paragraph.` …), with any real source material appended after it. Treat it as given. `final`
is the gold target.

```json
{"id": "...", "context": "...", "final": "..."}
```

## Output

Write to `outputs/<chunk-name>.output.jsonl` — one row per input row, same order.

```json
{"id": "...", "draft": "..."}
```

Rules:

- Preserve `id` exactly.
- Output **only** `id` and `draft`. Do not include `context`, `final`, or any other field.
- One JSON object per line. No markdown, no commentary, no code fences.
- Every `draft` must be a non-empty string and must differ from the `final`.

## Sub-agent use

Run parallel sub-agents **by chunk, not by row**. Each sub-agent owns exactly one input chunk and
writes exactly one output file. Never let two sub-agents write to the same file. If the agent system
has a concurrency limit, run them in waves.

```text
Input:  inputs/000.input.jsonl   ->  Output: outputs/000.output.jsonl
Input:  inputs/001.input.jsonl   ->  Output: outputs/001.output.jsonl
...one sub-agent per chunk...
```

## Validation checklist

After all sub-agents finish, confirm:

- every input `id` appears exactly once in the outputs, with no unexpected ids,
- output schema is exactly `id` + `draft`,
- every `draft` is non-empty and differs from its `final`.
