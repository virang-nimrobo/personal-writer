# Use

The stable runtime package is `writer_model`. It can be used from the CLI, the
browser studio, or Python.

## Setup

From the repository root:

```bash
make install
.venv/bin/python -m pip install -e .
```

The editable install exposes:

```text
writer-model-edit
writer-model-studio
```

Without the editable install, use:

```bash
.venv/bin/python -m writer_model.cli --help
.venv/bin/python -m writer_model.studio --help
```

## CLI Examples

Inline context and draft:

```bash
writer-model-edit \
  --context "Write an original tweet. Topic: taste is mostly repeated exposure to better examples." \
  --draft "Taste gets better when you look at better work over and over, not just by thinking." \
  --json
```

File-based workflow:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --json
```

JSON stdin:

```bash
printf '%s\n' '{"context":"Write a reply. Parent from @maya: small models are not worth the trouble.","draft":"They are worth it when the job is narrow, repeatable, and taste-heavy."}' \
  | writer-model-edit --stdin --json
```

Multiple candidates:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  -n 3 \
  --temp 0.9 \
  --max-tokens 220 \
  --json
```

Specific adapter:

```bash
writer-model-edit \
  --adapter out/editor-latest \
  --context-file context.md \
  --draft-file draft.md
```

Suppress usage logging:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --no-log
```

Raw model calls append to `data/usage/usage.jsonl` by default.

## Feedback Capture

Accepted output:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --feedback accepted
```

Edited output:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --feedback edited \
  --final-used-file final.md
```

Rejected output:

```bash
writer-model-edit \
  --context-file context.md \
  --draft-file draft.md \
  --feedback rejected
```

Feedback appends to `data/feedback/feedback.jsonl` and can be turned into new
core seeds in the next data-prep pass.

## WebUI Examples

Launch the browser studio:

```bash
writer-model-studio --adapter out/editor-latest --port 7860
```

Or run it without editable install:

```bash
.venv/bin/python -m writer_model.studio --adapter out/editor-latest --port 7860
```

Then open:

```text
http://localhost:7860
```

The studio has two inputs:

- `Context`: the directive and any source material.
- `Draft`: the rough text to rewrite.

Set `n` for the number of candidates and `temp` for sampling. The first
candidate is deterministic when only one output is requested; additional
candidates explore more.

Run without opening a browser automatically:

```bash
writer-model-studio --adapter out/editor-latest --port 7860 --no-open
```

## Python API

One-shot:

```python
from writer_model.api import edit

result = edit(
    context="Write an original tweet. Topic: local models as personal editors.",
    draft="Local models are useful because they can learn a person's writing style.",
    adapter_path="out/editor-latest",
)

print(result.chosen_output)
```

Repeated calls:

```python
from writer_model.api import WriterEditor

editor = WriterEditor(adapter_path="out/editor-latest")
editor.load()

result = editor.edit(
    "Write a reply. Parent: small models are too limited.",
    "They are limited, but that is fine for narrow editing jobs.",
    n=2,
    temp=0.8,
    source="local-script",
)

print(result.outputs)
```

## Logs

Default paths:

```text
data/usage/usage.jsonl
data/feedback/feedback.jsonl
```

Override them from the CLI:

```bash
writer-model-edit \
  --usage-path /tmp/writer-usage.jsonl \
  --feedback-path /tmp/writer-feedback.jsonl \
  --context-file context.md \
  --draft-file draft.md \
  --feedback accepted
```
