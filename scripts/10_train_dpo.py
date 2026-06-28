#!/usr/bin/env python3
"""Preference stage (DPO). mlx_lm has no DPO trainer, so per the plan this is the HF+PEFT fallback.

Always builds the DPO dataset (certain, valuable). Trains only with --train AND the optional deps
present (torch, transformers, trl, peft -> requirements-dpo.txt), since that stack is heavy on Mac.

DPO record per pair: prompt = editor input {context, draft=rejected}, chosen = preferred final,
rejected = dispreferred text. UI pairs share one {context, draft}; harvested edit-pairs frame the
rejected version as the draft the editor should transform away from.

Build: data/synth/dpo.jsonl     Train: out/editor-dpo (LoRA on top of the SFT adapter)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C          # noqa: E402
from _common import read_jsonl, write_jsonl, EDITOR_SYSTEM, build_user_prompt  # noqa: E402

DPO_FILE = C.SYNTH / "dpo.jsonl"
FEEDBACK_FILE = C.FEEDBACK / "feedback.jsonl"


def build_dataset():
    rows = []
    # harvested edit-pairs: prompt is the rejected version as the draft to improve on
    for p in read_jsonl(FEEDBACK_FILE):
        if p.get("chosen") and p.get("rejected"):
            draft = p.get("draft") or p["rejected"]
            rows.append({
                "prompt": build_user_prompt(p["context"], draft),
                "chosen": p["chosen"], "rejected": p["rejected"], "system": EDITOR_SYSTEM,
            })
            continue

        # CLI feedback rows are broader reviewed-outcome records. Only edited
        # outputs form a clean preference pair for DPO; accepted-only rows are
        # better handled by Data Prep as future SFT triplets.
        final_used = p.get("final_used_output")
        chosen_output = p.get("chosen_output")
        if p.get("feedback") == "edited" and final_used and chosen_output and final_used != chosen_output:
            rows.append({
                "prompt": build_user_prompt(p["context"], p["draft"]),
                "chosen": final_used, "rejected": chosen_output, "system": EDITOR_SYSTEM,
            })
    # UI prefs: same {context, draft}, picked vs not-picked
    for p in read_jsonl(C.PREFS / "prefs.jsonl"):
        rows.append({
            "prompt": build_user_prompt(p["context"], p["draft"]),
            "chosen": p["chosen"], "rejected": p["rejected"], "system": EDITOR_SYSTEM,
        })
    write_jsonl(DPO_FILE, rows)
    print(f"built {len(rows)} DPO pairs -> {DPO_FILE}")
    return rows


def train(rows, sft_adapter, out_dir):
    try:
        import torch  # noqa: F401
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import LoraConfig
        from trl import DPOTrainer, DPOConfig
    except ImportError as e:
        print(f"\n[skip training] missing DPO deps ({e}).")
        print("install: .venv/bin/python -m pip install -r requirements-dpo.txt")
        print(f"dataset is ready at {DPO_FILE} for a HF+PEFT DPO run.")
        return

    base = C.BASE_MODEL.replace("-4bit", "")  # full-precision base for HF training
    tok = AutoTokenizer.from_pretrained(base)
    ds = Dataset.from_list([{
        "prompt": tok.apply_chat_template(
            [{"role": "system", "content": r["system"]},
             {"role": "user", "content": r["prompt"]}],
            tokenize=False, add_generation_prompt=True),
        "chosen": r["chosen"], "rejected": r["rejected"],
    } for r in rows])
    model = AutoModelForCausalLM.from_pretrained(base)
    peft_cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM")
    cfg = DPOConfig(output_dir=out_dir, per_device_train_batch_size=1,
                    num_train_epochs=1, learning_rate=5e-6, beta=0.1, logging_steps=5)
    trainer = DPOTrainer(model=model, args=cfg, train_dataset=ds,
                         processing_class=tok, peft_config=peft_cfg)
    trainer.train()
    trainer.save_model(out_dir)
    print(f"DPO adapter saved -> {out_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--sft-adapter", default="out/editor-latest")
    ap.add_argument("--out", default="out/editor-dpo")
    args = ap.parse_args()
    rows = build_dataset()
    if args.train:
        if not rows:
            sys.exit("no DPO pairs - harvest/label first")
        train(rows, args.sft_adapter, args.out)


if __name__ == "__main__":
    main()
