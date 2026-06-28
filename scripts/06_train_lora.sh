#!/usr/bin/env bash
# LoRA SFT of the editor via mlx_lm. `--smoke` = tiny run to validate the chain.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)}"
MODEL="${MODEL:-mlx-community/Qwen3.5-2B-MLX-4bit}"
DATA="data/synth"

if [[ "${1:-}" == "--smoke" ]]; then
  ITERS="${ITERS:-40}"; BATCH=1; LAYERS=4; ADAPTER="out/smoke"
else
  ITERS="${ITERS:-300}"; BATCH="${BATCH:-2}"; LAYERS="${LAYERS:-8}"; ADAPTER="${ADAPTER:-out/editor-latest}"
fi
# Data maxes at ~424 tokens; cap well below mlx_lm's 2048 default to fit a 16GB GPU.
# This cap is the main memory saver; grad checkpointing is off for speed but can be
# re-enabled (GRAD_CKPT=1) if memory gets tight.
MAXSEQ="${MAXSEQ:-512}"
LR="${LR:-1e-4}"
CKPT="${GRAD_CKPT:+--grad-checkpoint}"
mkdir -p "$ADAPTER"

echo "training: model=$MODEL iters=$ITERS batch=$BATCH layers=$LAYERS lr=$LR maxseq=$MAXSEQ mask_prompt=on ckpt=${GRAD_CKPT:-0} -> $ADAPTER"
$PY -m mlx_lm lora \
  --model "$MODEL" \
  --train \
  --data "$DATA" \
  --iters "$ITERS" \
  --batch-size "$BATCH" \
  --num-layers "$LAYERS" \
  --learning-rate "$LR" \
  --max-seq-length "$MAXSEQ" \
  --mask-prompt \
  $CKPT \
  --adapter-path "$ADAPTER"
echo "adapter written to $ADAPTER"
