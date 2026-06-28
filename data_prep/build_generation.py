#!/usr/bin/env python3
"""Step 2 of data prep: scaffold a dated generation-{date}/ from the core set.

Reads the whole core set, emits generation inputs {id, context, final} straight
from the core rows, chunks them, and writes the SAME chunks into one folder per
model (codex/ gemini/ sonnet/ opus/), each with an identical instruction.md and
an empty outputs/. A human then opens a model folder and runs that model's agent
(one sub-agent per inputs/*.input.jsonl chunk) to fill outputs/*.output.jsonl.

This only scaffolds — it does not call any model. After the four models have
written their outputs, run `python3 data_prep/build_triplets.py` (step 3).

Usage:
  python3 data_prep/build_generation.py                 # date = today, chunk 10
  python3 data_prep/build_generation.py --date 2026-06-28 --chunk-size 10
  python3 data_prep/build_generation.py --models codex sonnet opus
"""
import argparse
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent          # data_prep/
sys.path.insert(0, str(HERE.parent))            # repo root
from scripts._common import read_jsonl, write_jsonl  # noqa: E402

CORE = HERE / "core"
TEMPLATE = HERE / "templates" / "instruction.md"
DEFAULT_MODELS = ["codex", "gemini", "sonnet", "opus"]

GEN_README = """# Generation {date}

Step-2 draft generation derived from the core set. Each `no_draft` seed (and each
`with_draft` seed, for an alternative draft) gets an **off-voice draft** from every
model folder below. The four folders share identical inputs and `instruction.md`;
the folder name signals which model runs there.

```
{model_list}
```

## Run a model

Open one folder and run that model's agent. Fan out **one sub-agent per chunk**
(`inputs/000.input.jsonl` -> `outputs/000.output.jsonl`); never let two sub-agents
write the same output file. Output rows are `{{"id": "...", "draft": "..."}}` only.

Input rows ({n_inputs} total, {n_chunks} chunks of <= {chunk_size}):

```json
{{"id": "...", "context": "...", "final": "..."}}
```

## After generation

```bash
python3 data_prep/build_triplets.py        # step 3: merge -> landing_zone/triplets.jsonl
```

`build_triplets.py` auto-discovers any `<model>/outputs/` here, so you can run a
subset of the four folders and still build — only the models you ran contribute.
"""


def load_inputs():
    """Generation inputs {id, context, final} from both core files (all seeds get a draft)."""
    inputs, seen = [], set()
    for name in ("no_draft.jsonl", "with_draft.jsonl"):
        for n, row in enumerate(read_jsonl(CORE / name), 1):
            rid = str(row.get("id", "")).strip()
            context = str(row.get("context", "")).strip()
            final = str(row.get("final", "")).strip()
            if not (rid and context and final):
                sys.exit(f"core/{name}:{n}: every seed needs id, context, final")
            if rid in seen:
                sys.exit(f"core/{name}:{n}: duplicate core id {rid}")
            seen.add(rid)
            inputs.append({"id": rid, "context": context, "final": final})
    return inputs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=date.today().isoformat(), help="generation date (default today)")
    ap.add_argument("--chunk-size", type=int, default=10)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    args = ap.parse_args()

    if not TEMPLATE.exists():
        sys.exit(f"missing instruction template: {TEMPLATE}")
    instruction = TEMPLATE.read_text()

    inputs = load_inputs()
    if not inputs:
        sys.exit("no core seeds found in data_prep/core/{no_draft,with_draft}.jsonl")

    chunks = [inputs[i:i + args.chunk_size] for i in range(0, len(inputs), args.chunk_size)]

    gen_dir = HERE / f"generation-{args.date}"
    if gen_dir.exists():
        sys.exit(f"{gen_dir} already exists -- remove it or pick another --date")

    for model in args.models:
        mdir = gen_dir / model
        (mdir / "outputs").mkdir(parents=True, exist_ok=True)
        (mdir / "instruction.md").write_text(instruction)
        (mdir / "outputs" / ".gitkeep").write_text("")
        for idx, chunk in enumerate(chunks):
            write_jsonl(mdir / "inputs" / f"{idx:03d}.input.jsonl", chunk)

    (gen_dir / "README.md").write_text(GEN_README.format(
        date=args.date,
        model_list="\n".join(f"{m}/" for m in args.models),
        n_inputs=len(inputs), n_chunks=len(chunks), chunk_size=args.chunk_size,
    ))

    print(f"scaffolded {gen_dir}")
    print(f"  models: {', '.join(args.models)}")
    print(f"  inputs: {len(inputs)} seeds -> {len(chunks)} chunks of <= {args.chunk_size}")
    print(f"  per model: instruction.md + inputs/000..{len(chunks)-1:03d}.input.jsonl + outputs/")
    print("next: run each model folder's agent, then python3 data_prep/build_triplets.py")


if __name__ == "__main__":
    main()
