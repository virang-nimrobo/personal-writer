"""Append-only structured usage logs for future training data."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from writer_model import settings


SCHEMA_VERSION = 1


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def default_usage_path():
    return settings.DEFAULT_USAGE_PATH


class UsageLogger:
    """JSONL logger for model calls.

    The raw usage log is intentionally broader than training feedback. Later
    harvesters can convert accepted/edited records into SFT or preference data.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path else default_usage_path()

    def append(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = dict(record)
        if not row.get("schema_version"):
            row["schema_version"] = SCHEMA_VERSION
        if not row.get("id"):
            row["id"] = str(uuid4())
        if not row.get("created_at"):
            row["created_at"] = utc_now_iso()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row
