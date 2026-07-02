# Core Set

The core set is the **durable seed bank** for training the writer-model. It grows over time as new
material lands. Everything downstream (the dated `generation-{date}/` folders, then the landing-zone
triplets) is derived from here.

This is **step 1** of the 3-step data-prep flow:

1. **Build the core set** — curate seeds into the two files below.
2. **Build the generation folder** — derive `data_prep/generation-{date}/` from the core set, where
   configured models generate off-voice drafts. (See `../README.md`.)
3. **Build triplets** — merge core seeds and generated drafts into
   `landing_zone/triplets.jsonl`.

## The two files

Seeds are split by the one distinction that matters downstream — **does a real draft already exist?**
The core set itself is model-agnostic; model-specific variation is introduced only
in the generation folders.

| File | Holds | Row schema |
| --- | --- | --- |
| `no_draft.jsonl`   | seeds with no draft (a final, maybe real context) | `{id, kind, context, final}` |
| `with_draft.jsonl` | seeds that already have a real draft | `{id, kind, context, draft, final}` |

- `no_draft.jsonl` rows get a draft **generated** in step 2.
- `with_draft.jsonl` rows keep their real draft as gold **and** get alternative drafts in step 2.

## Fields

- **id** — stable unique id, e.g. `tweet:<id>`, `email:<slug>`, `raw:<n>`.
- **kind** — the medium/format. Drives the terse directive. One of:
  `tweet`, `reply`, `thread`, `email`, `article`, `para`.
- **context** — **compulsory and non-empty on every row.** It **always leads with a terse directive**
  that names the task, so the model knows *what is being written* at both training and inference time.
  When real source material exists (e.g. the parent of a reply), **append it after** the directive.
  The agent fills this in.
- **draft** (`with_draft.jsonl` only) — the real, rough draft.
- **final** — the real, gold piece in the user's voice. Always present.

### Terse directive by `kind`

| kind | directive |
| --- | --- |
| `tweet`   | `Write an original tweet.` |
| `reply`   | `Write a reply.` |
| `thread`  | `Write a thread.` |
| `email`   | `Write an email.` |
| `article` | `Write an article.` |
| `para`    | `Write a paragraph.` |

The directive is **always present**, even when real context exists — so the row is never just the raw
parent text. Real material is appended after it.

## Examples

`no_draft.jsonl` — an original tweet, no real context (directive only):

```json
{"id": "tweet:0001", "kind": "tweet", "context": "Write an original tweet.", "final": "<the real tweet, in the user's voice>"}
```

`no_draft.jsonl` — a reply, with real context appended after the directive:

```json
{"id": "tweet:0002", "kind": "reply", "context": "Write a reply. Parent from @someone: <the parent post text>", "final": "<the real reply, in the user's voice>"}
```

`with_draft.jsonl` — an email, with real context and a real rough draft:

```json
{"id": "email:0003", "kind": "email", "context": "Write an email. To <recipient> about <topic>.", "draft": "<the rough, off-voice draft that was actually written first>", "final": "<the real sent email, in the user's voice>"}
```

## Notes

- Keep one JSON object per line. No trailing commas, no comments.
- `final` is gold — never edit it to fit the schema.
- The core set is cumulative: append new seeds, don't rewrite existing ones.
