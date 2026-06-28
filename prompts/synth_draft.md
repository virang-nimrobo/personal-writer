You are generating TRAINING DATA for a tweet-editor model. Given a FINAL tweet that
@VirangJhaveri actually wrote (in his voice), reverse-engineer the inputs that should
produce it: a realistic CONTEXT brief and a rough, OFF-VOICE DRAFT.

The DRAFT must:
- carry the SAME substance, facts, and numbers as the final (invent nothing new),
- but read like a generic LLM/marketing draft that violates Virang's voice: hype words,
  a validation opener, em-dashes, a salesy CTA, vague generalities instead of specifics.
The CONTEXT must describe the situation/material a planner would hand the editor (topic,
source, any real numbers), WITHOUT already being in Virang's voice.

Kind: {kind}
Existing context (may be "none"): {context}
FINAL tweet:
{final}

Return ONLY a JSON object:
{{"context": "<planner brief>", "draft": "<rough off-voice draft>"}}
