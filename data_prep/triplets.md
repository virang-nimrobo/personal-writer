# Triplet Contract

This is the **output contract** every row in the unified landing-zone file
(`landing_zone/triplets.jsonl`) must satisfy. Rows are produced by
`data_prep/build_triplets.py` (step 3, which validates on write) and can be
re-checked any time with `scripts/validate_landing_zone.py`.

Each row must be one JSON object per line:

```json
{"id": "source:stable-id", "context": "...", "draft": "...", "final": "..."}
```

Rules:

- `id` is globally unique and stable across reruns (`real:<seed>` for gold rows,
  `<model>:<seed>` for generated drafts).
- `context` contains the evidence or situation the editor is allowed to rely on.
- `draft` is the rough or off-voice text the model should transform.
- `final` is the desired output in the user's voice.
- Do not include rows where the final text depends on facts missing from the
  context or draft.
- The file is a full rebuild: `build_triplets.py` overwrites it from `core/` +
  `generation-*/`. Don't hand-edit it — change the seeds/drafts and rebuild.

Validate any time with:

```bash
python3 scripts/validate_landing_zone.py
```
