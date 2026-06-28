"""Shared prompt format + jsonl helpers used by build/infer/eval.

The editor's task framing lives here so training and serving stay identical.
"""
import json
import hashlib
from pathlib import Path

from writer_model.prompts import EDITOR_SYSTEM, build_user_prompt


def bucket(rec_id: str) -> int:
    """Deterministic 0-9 bucket for stable train/valid/test splits (0=test, 1=valid, else train)."""
    return int(hashlib.md5(rec_id.encode()).hexdigest()[:8], 16) % 10

def chat_record(context: str, draft: str, final: str) -> dict:
    """MLX chat format for mlx_lm.lora."""
    return {"messages": [
        {"role": "system", "content": EDITOR_SYSTEM},
        {"role": "user", "content": build_user_prompt(context, draft)},
        {"role": "assistant", "content": final.strip()},
    ]}


def read_jsonl(path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def write_jsonl(path, rows) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def active_landing_triplets(C) -> list:
    """Load the unified landing-zone triplets file.

    Falls back to the legacy manifest/shard path, then to legacy data/synth triples,
    so older data still trains if the unified file hasn't been built yet.
    """
    rows = read_jsonl(C.LANDING_FILE)
    if rows:
        return rows

    manifest = read_json(C.LANDING_MANIFEST, default=None)
    if manifest:
        entries = manifest.get("batches", manifest if isinstance(manifest, list) else [])
        legacy = []
        for entry in entries:
            if not entry.get("active", True):
                continue
            shard_path = Path(entry["path"])
            if not shard_path.is_absolute():
                shard_path = C.ROOT / shard_path
            legacy.extend(read_jsonl(shard_path))
        if legacy:
            return legacy

    return read_jsonl(C.TRIPLES)


def validate_triplets(rows) -> list[str]:
    errors = []
    seen = set()
    required = ("id", "context", "draft", "final")
    for i, row in enumerate(rows, start=1):
        missing = [key for key in required if not str(row.get(key, "")).strip()]
        if missing:
            errors.append(f"row {i}: missing {', '.join(missing)}")
        rec_id = row.get("id")
        if rec_id in seen:
            errors.append(f"row {i}: duplicate id {rec_id}")
        seen.add(rec_id)
    return errors
