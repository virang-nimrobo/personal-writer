"""CLI wrapper for markdown-driven workflows such as Xgrowth."""

import argparse
import json
import sys
from pathlib import Path

from writer_model.api import WriterEditor
from writer_model.feedback_log import FeedbackLogger


def _read_text(value, file_path):
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    return value


def _payload_from_args(args):
    if args.stdin:
        payload = json.loads(sys.stdin.read())
        context = payload["context"]
        draft = payload["draft"]
        metadata = payload.get("metadata") or {}
        return context, draft, metadata

    context = _read_text(args.context, args.context_file)
    draft = _read_text(args.draft, args.draft_file)
    if not context or not draft:
        raise SystemExit(
            "provide --context/--draft, --context-file/--draft-file, or --stdin"
        )

    metadata = {}
    if args.metadata_json:
        metadata = json.loads(args.metadata_json)
    return context, draft, metadata


def build_parser():
    ap = argparse.ArgumentParser(description="Edit an Xgrowth draft with writer-model.")
    ap.add_argument("--context")
    ap.add_argument("--draft")
    ap.add_argument("--context-file")
    ap.add_argument("--draft-file")
    ap.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--base-model", default=None)
    ap.add_argument("--usage-path", default=None)
    ap.add_argument("--source", default="xgrowth")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--artifact-type", default=None)
    ap.add_argument("--metadata-json", default=None)
    ap.add_argument("--feedback", choices=["accepted", "edited", "rejected"], default=None)
    ap.add_argument("--feedback-path", default=None)
    ap.add_argument("--final-used")
    ap.add_argument("--final-used-file")
    ap.add_argument("-n", type=int, default=1)
    ap.add_argument("--temp", type=float, default=0.7)
    ap.add_argument("--max-tokens", type=int, default=160)
    ap.add_argument("--no-log", action="store_true")
    ap.add_argument("--json", action="store_true", help="print full result JSON")
    return ap


def _write_feedback(args, result):
    if not args.feedback:
        return None

    final_used = _read_text(args.final_used, args.final_used_file)
    if args.feedback == "accepted" and not final_used:
        final_used = result.chosen_output
    if args.feedback == "edited" and not final_used:
        raise SystemExit("--feedback edited requires --final-used or --final-used-file")

    row = {
        "usage_id": result.id,
        "feedback": args.feedback,
        "accepted": args.feedback in {"accepted", "edited"},
        "source": result.source,
        "run_id": result.run_id,
        "artifact_type": result.artifact_type,
        "model_base": result.model_base,
        "adapter": result.adapter,
        "context": result.context,
        "draft": result.draft,
        "outputs": result.outputs,
        "chosen_output": result.chosen_output,
        "final_used_output": final_used,
        "metadata": result.metadata,
    }
    return FeedbackLogger(args.feedback_path).append(row)


def main(argv=None):
    args = build_parser().parse_args(argv)
    context, draft, metadata = _payload_from_args(args)

    editor = WriterEditor(
        adapter_path=args.adapter,
        base_model=args.base_model,
        usage_path=args.usage_path,
        log_usage=not args.no_log,
    )
    result = editor.edit(
        context,
        draft,
        n=args.n,
        temp=args.temp,
        max_tokens=args.max_tokens,
        source=args.source,
        run_id=args.run_id,
        artifact_type=args.artifact_type,
        metadata=metadata,
    )
    feedback_row = _write_feedback(args, result)

    if args.json:
        payload = result.to_dict()
        if feedback_row:
            payload["feedback_id"] = feedback_row["id"]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(result.chosen_output or "")


if __name__ == "__main__":
    main()
