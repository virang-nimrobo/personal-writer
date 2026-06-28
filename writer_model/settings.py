"""Package-local paths and model defaults for editable local installs.

Model/adapter defaults are derived from the root ``config.py`` so the inference
path and the data/training pipeline can't drift apart.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from config import C  # noqa: E402  (path set up above)

DATA = ROOT / "data"
OUT = ROOT / "out"
USAGE = DATA / "usage"
FEEDBACK = DATA / "feedback"

BASE_MODEL = C.BASE_MODEL
DEFAULT_ADAPTER = C.DEFAULT_ADAPTER
DEFAULT_USAGE_PATH = USAGE / "usage.jsonl"
DEFAULT_FEEDBACK_PATH = FEEDBACK / "feedback.jsonl"

USAGE.mkdir(parents=True, exist_ok=True)
FEEDBACK.mkdir(parents=True, exist_ok=True)
