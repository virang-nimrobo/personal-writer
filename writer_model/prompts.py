"""Shared editor prompt format used for training and serving."""

EDITOR_SYSTEM = (
    "You are a writing editor. You receive a CONTEXT (the situation and material) and a DRAFT "
    "(a rough, off-voice attempt). Rewrite it into the final piece. You may freely restructure "
    "and choose the angle, but never invent facts, numbers, or claims that are not supported by "
    "the context or draft. Output only the final text, nothing else."
)


def build_user_prompt(context: str, draft: str) -> str:
    return (
        f"<context>\n{context.strip()}\n</context>\n\n"
        f"<draft>\n{draft.strip()}\n</draft>\n\n"
        "FINAL:"
    )
