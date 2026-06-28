# Use

The stable runtime package is `writer_model`.

Primary CLI:

```bash
writer-model-edit --context-file context.md --draft-file draft.md --json
```

Raw model calls append to `data/usage/usage.jsonl`.

When a generation is reviewed during use, record feedback directly:

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

Feedback appends to `data/feedback/feedback.jsonl` and can be turned into new
landing-zone shards by the Data Prep agent.
