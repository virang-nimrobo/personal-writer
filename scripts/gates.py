"""Deterministic DRAFT-GATE checks, mirrored from Xgrowth run.md.

These are the rule-checkable parts of taste: they serve as an eval metric here and can later be a
hard repair/reject step in the inference pipeline (Phase 2).
"""
import re

from config import C

VALIDATION_OPENERS = [
    "this is huge", "love this", "so true", "honestly", "hot take",
    "great point", "absolutely", "100%", "this.", "wow",
]


def check_gates(text: str) -> dict:
    t = text.strip()
    low = t.lower()
    lines = [ln for ln in t.splitlines() if ln.strip()]
    has_link = bool(re.search(r"(https?://|github\.com|x\.com)", low))

    checks = {
        "no_em_dash": "—" not in t and " - " not in t,
        "no_validation_opener": not any(low.startswith(o) for o in VALIDATION_OPENERS),
        "within_length": len(t) <= C.MAX_TWEET_CHARS,
        "link_on_last_line": (not has_link) or bool(
            re.search(r"(https?://|github\.com)", lines[-1].lower())),
        "no_cta_spam": not re.search(r"(check it out|don'?t miss|sign up now|click)", low),
    }
    checks["all_pass"] = all(checks.values())
    return checks
