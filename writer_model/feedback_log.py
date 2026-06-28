"""Append-only reviewed feedback logs for future data prep."""

import json
from pathlib import Path
from uuid import uuid4

from writer_model import settings
from writer_model.usage_log import utc_now_iso


SCHEMA_VERSION = 1


def default_feedback_path():
    return settings.DEFAULT_FEEDBACK_PATH


class FeedbackLogger:
    """JSONL logger for reviewed model outputs.

    These rows are not training data by themselves. Data Prep converts accepted
    or edited generations into future landing-zone triplet shards.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path else default_feedback_path()

    def append(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = dict(record)
        row.setdefault("schema_version", SCHEMA_VERSION)
        row.setdefault("id", str(uuid4()))
        row.setdefault("created_at", utc_now_iso())
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row
