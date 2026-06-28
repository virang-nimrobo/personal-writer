#!/usr/bin/env python3
"""Score an editor adapter on the held-out test split -> scorecard.json.

Metrics:
  - gate_pass_rate     deterministic DRAFT-GATE checks (always on)
  - similarity         embedding cosine to the real tweet (if sentence-transformers present)
  - voice_winrate      LLM-judge: editor output more in-voice than the draft? (--judge)
  - hallucination_rate LLM-judge: adds a claim not in context/draft? (--judge)  <- free-restructure gate

The hallucination_rate is the signal for the free-vs-bounded decision in the plan.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C          # noqa: E402
from _common import active_landing_triplets, bucket, validate_triplets  # noqa: E402
from editor import load_editor, generate_final  # noqa: E402
from gates import check_gates  # noqa: E402


def embed_sim(pairs):
    try:
        from sentence_transformers import SentenceTransformer, util
    except ImportError:
        return None
    m = SentenceTransformer("all-MiniLM-L6-v2")
    sims = []
    for out, gold in pairs:
        e = m.encode([out, gold], convert_to_tensor=True, normalize_embeddings=True)
        sims.append(float(util.cos_sim(e[0], e[1])))
    return sum(sims) / len(sims) if sims else None


def judge(items):
    """LLM-judge voice win-rate vs draft + hallucination rate."""
    import os
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    wins, halluc = 0, 0
    for it in items:
        prompt = (
            "You judge edited writing. Given a CONTEXT and a rough DRAFT, decide whether the "
            "EDITOR's version is more in the writer's voice than the draft, and whether it adds "
            "any claim not supported by the context or draft.\n\n"
            f"CONTEXT:\n{it['context']}\n\nDRAFT:\n{it['draft']}\n\nEDITOR:\n{it['out']}\n\n"
            "Answer JSON only: {\"editor_more_in_voice\": true|false, "
            "\"editor_adds_unsupported_claim\": true|false}"
        )
        msg = client.messages.create(model=C.JUDGE_MODEL, max_tokens=120,
                                     messages=[{"role": "user", "content": prompt}])
        import re
        m = re.search(r"\{.*\}", msg.content[0].text, re.DOTALL)
        d = json.loads(m.group(0)) if m else {}
        wins += bool(d.get("editor_more_in_voice"))
        halluc += bool(d.get("editor_adds_unsupported_claim"))
    n = len(items) or 1
    return wins / n, halluc / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="out/editor-latest")
    ap.add_argument("--judge", action="store_true", help="run the LLM voice/hallucination judge")
    args = ap.parse_args()

    triples = active_landing_triplets(C)
    errors = validate_triplets(triples)
    if errors:
        sys.exit("invalid triplets:\n" + "\n".join(errors[:50]))

    test = [t for t in triples if bucket(t["id"]) == 0]
    if not test:
        sys.exit("no test triples - build the dataset first")

    print(f"loading adapter {args.adapter} ...", file=sys.stderr)
    model, tok = load_editor(adapter_path=args.adapter)

    items, gates = [], []
    for t in test:
        out = generate_final(model, tok, t["context"], t["draft"], n=1)[0]
        items.append({"context": t["context"], "draft": t["draft"], "out": out, "gold": t["final"]})
        gates.append(check_gates(out))

    scorecard = {
        "adapter": args.adapter,
        "n_test": len(test),
        "gate_pass_rate": sum(g["all_pass"] for g in gates) / len(gates),
        "gate_breakdown": {k: sum(g[k] for g in gates) / len(gates)
                           for k in gates[0] if k != "all_pass"},
        "similarity": embed_sim([(it["out"], it["gold"]) for it in items]),
    }
    if args.judge:
        vw, hr = judge(items)
        scorecard["voice_winrate_vs_draft"] = vw
        scorecard["hallucination_rate"] = hr

    out_path = Path(args.adapter) / "scorecard.json"
    out_path.write_text(json.dumps(scorecard, indent=2))
    print(json.dumps(scorecard, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
