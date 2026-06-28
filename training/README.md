# Training

Training is deterministic and Make-driven. It consumes active triplet shards from
`landing_zone/manifest.json`.

Commands:

```bash
make train
make eval
make promote
```

`make train` rebuilds MLX chat data from active landing-zone shards before
running LoRA training.

`make eval` scores an adapter against the held-out bucket from the same active
triplets.

`make promote` compares `out/editor-candidate/scorecard.json` with
`out/editor-latest/scorecard.json` and promotes the candidate only when it does
not regress gate pass rate.
