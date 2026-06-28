#!/usr/bin/env python3
"""Validate the unified landing-zone triplets file."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C  # noqa: E402
from _common import active_landing_triplets, validate_triplets  # noqa: E402


def main():
    rows = active_landing_triplets(C)
    if not rows:
        sys.exit(f"no landing-zone triplets - run data_prep/build_triplets.py first ({C.LANDING_FILE})")

    errors = validate_triplets(rows)
    if errors:
        sys.exit("invalid landing-zone triplets:\n" + "\n".join(errors[:50]))

    print(json.dumps({
        "triplets": len(rows),
        "landing_file": str(C.LANDING_FILE),
    }, indent=2))


if __name__ == "__main__":
    main()
