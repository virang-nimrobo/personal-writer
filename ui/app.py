#!/usr/bin/env python3
"""Pairwise A/B + inline-edit labeling UI (Phase 3).

For each {context, draft} the editor generates two candidates. You pick the better one (or edit the
winner inline), producing a clean {chosen, rejected} pair for DPO. Writes data/prefs/prefs.jsonl.

Queue source: data/synth/triples.jsonl by default (any {context, draft} works). Already-labeled
items are skipped. Run: `make ui` (needs gradio: `make install`).
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import C          # noqa: E402
from _common import read_jsonl  # noqa: E402
from editor import load_editor, generate_final  # noqa: E402

PREFS_FILE = C.PREFS / "prefs.jsonl"
ADAPTER = "out/editor-latest" if Path("out/editor-latest").exists() else "out/smoke"


def item_key(ctx, draft):
    return hashlib.md5((ctx + "||" + draft).encode()).hexdigest()


def load_queue():
    labeled = {item_key(p["context"], p["draft"]) for p in read_jsonl(PREFS_FILE)}
    return [t for t in read_jsonl(C.TRIPLES) if item_key(t["context"], t["draft"]) not in labeled]


def main():
    import gradio as gr
    print(f"loading editor adapter {ADAPTER} ...")
    model, tok = load_editor(adapter_path=ADAPTER)
    state = {"queue": load_queue(), "i": 0, "cands": ["", ""], "cur": None}

    def gen():
        q = state["queue"]
        if state["i"] >= len(q):
            return "All done 🎉", "", "", "", "", gr.update(visible=False)
        it = q[state["i"]]
        state["cur"] = it
        cands = generate_final(model, tok, it["context"], it["draft"], n=2, temp=0.9)
        state["cands"] = cands
        head = f"Item {state['i']+1}/{len(q)}"
        return head, it["context"], it["draft"], cands[0], cands[1], gr.update(visible=True)

    def save(winner, edited):
        it = state["cur"]
        if not it:
            return "nothing to save"
        a, b = state["cands"]
        chosen = (edited.strip() or (a if winner == "A" else b))
        rejected = b if winner == "A" else a
        rec = {"context": it["context"], "draft": it["draft"],
               "chosen": chosen, "rejected": rejected, "winner": winner}
        with open(PREFS_FILE, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        state["i"] += 1
        return f"saved ({sum(1 for _ in open(PREFS_FILE))} total)"

    with gr.Blocks(title="writer-model labeling") as app:
        gr.Markdown("# Editor preference labeling — pick the better tweet (or edit the winner)")
        head = gr.Markdown()
        ctx = gr.Textbox(label="Context", lines=3, interactive=False)
        draft = gr.Textbox(label="Draft (planner)", lines=2, interactive=False)
        with gr.Row():
            ca = gr.Textbox(label="A", lines=4, interactive=False)
            cb = gr.Textbox(label="B", lines=4, interactive=False)
        winner = gr.Radio(["A", "B"], label="Better", value="A")
        edited = gr.Textbox(label="Optional: edit the winner into the ideal tweet", lines=4)
        with gr.Row(visible=False) as actions:
            save_btn = gr.Button("Save + Next", variant="primary")
        status = gr.Markdown()

        app.load(gen, outputs=[head, ctx, draft, ca, cb, actions])
        save_btn.click(save, [winner, edited], status).then(
            gen, outputs=[head, ctx, draft, ca, cb, actions]).then(
            lambda: "", outputs=edited)

    app.launch()


if __name__ == "__main__":
    main()
