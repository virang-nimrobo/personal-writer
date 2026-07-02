import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "data_prep" / "run_draft_generation.py"
spec = importlib.util.spec_from_file_location("run_draft_generation", MODULE_PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunDraftGenerationTests(unittest.TestCase):
    def test_load_config_and_resolve_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft_models.json"
            path.write_text(json.dumps({
                "models": {
                    "gemma-test": {
                        "base_url": "http://localhost:11434/v1",
                        "model": "gemma3:27b",
                    }
                }
            }))

            config = runner.load_config(path)
            self.assertEqual(
                runner.resolve_model(config, "gemma-test")["model"],
                "gemma3:27b",
            )

    def test_load_config_allows_mlx_without_base_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft_models.json"
            path.write_text(json.dumps({
                "models": {
                    "mlx-test": {
                        "backend": "mlx",
                        "model": "mlx-community/Qwen3-8B-4bit",
                    }
                }
            }))

            config = runner.load_config(path)

            self.assertEqual(config["models"]["mlx-test"]["backend"], "mlx")

    def test_resolve_model_supports_ad_hoc_lmstudio_default(self):
        config = {"models": {}}
        spec = runner.resolve_model(config, "gemma-custom", provider="lmstudio")
        self.assertEqual(spec["backend"], "openai-compatible")
        self.assertEqual(spec["base_url"], "http://localhost:1234/v1")
        self.assertEqual(spec["model"], "gemma-custom")

    def test_resolve_model_supports_ad_hoc_ollama_default(self):
        config = {"models": {}}
        spec = runner.resolve_model(config, "gemma3:27b", provider="ollama")
        self.assertEqual(spec["base_url"], "http://localhost:11434/v1")

    def test_resolve_model_supports_mlx_override(self):
        config = {"models": {}}
        spec = runner.resolve_model(
            config,
            "qwen-local",
            mlx_model="mlx-community/Qwen2.5-3B-Instruct-4bit",
        )
        self.assertEqual(spec["backend"], "mlx")
        self.assertEqual(spec["model"], "mlx-community/Qwen2.5-3B-Instruct-4bit")

    def test_build_user_prompt_preserves_rows(self):
        rows = [{"id": "tweet:1", "context": "Write an original tweet.", "final": "hello"}]
        prompt = runner.build_user_prompt(rows)
        self.assertIn('"id": "tweet:1"', prompt)
        self.assertIn("Return JSONL only", prompt)
        self.assertIn("Preserve ids and row order exactly", prompt)

    def test_validate_output_accepts_matching_rows_and_strips_draft(self):
        input_rows = [{"id": "tweet:1", "final": "final text"}]
        output_rows = [{"id": "tweet:1", "draft": " rough draft "}]

        runner.validate_output(input_rows, output_rows, "chunk")

        self.assertEqual(output_rows[0]["draft"], "rough draft")

    def test_validate_output_canonicalizes_token_artifact_id_prefix(self):
        input_rows = [{"id": "tweet:1", "final": "final text"}]
        output_rows = [{"id": "<0xA0>tweet:1", "draft": "rough draft"}]

        runner.validate_output(input_rows, output_rows, "chunk")

        self.assertEqual(output_rows[0]["id"], "tweet:1")

    def test_validate_output_canonicalizes_truncated_tweet_prefix(self):
        input_rows = [{"id": "tweet:2032923446280372465", "final": "final text"}]
        output_rows = [{"id": "t:2032923446280372465", "draft": "rough draft"}]

        runner.validate_output(input_rows, output_rows, "chunk")

        self.assertEqual(output_rows[0]["id"], "tweet:2032923446280372465")

    def test_validate_output_rejects_different_tweet_number(self):
        input_rows = [{"id": "tweet:2032923446280372465", "final": "final text"}]
        output_rows = [{"id": "t:2032923446280372466", "draft": "rough draft"}]

        with self.assertRaises(SystemExit):
            runner.validate_output(input_rows, output_rows, "chunk")

    def test_validate_output_can_quarantine_bad_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid_path = Path(tmp) / "invalid.jsonl"
            retry_path = Path(tmp) / "retry.jsonl"
            input_rows = [
                {"id": "tweet:1", "final": "final one"},
                {"id": "tweet:2", "final": "final two"},
            ]
            output_rows = [
                {"id": "tweet:1", "draft": "rough one"},
                {"id": "tweet:999", "draft": "rough two"},
            ]

            invalid = runner.validate_output(input_rows, output_rows, "chunk", invalid_path, retry_path)

            self.assertEqual(output_rows, [{"id": "tweet:1", "draft": "rough one"}])
            self.assertEqual(len(invalid), 1)
            saved = json.loads(invalid_path.read_text().strip())
            self.assertIn("id mismatch", saved["reason"])
            self.assertEqual(saved["input"]["id"], "tweet:2")
            self.assertEqual(
                [json.loads(line) for line in retry_path.read_text().splitlines()],
                [{"id": "tweet:2", "final": "final two"}],
            )

    def test_validate_output_can_quarantine_extra_output_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid_path = Path(tmp) / "invalid.jsonl"
            retry_path = Path(tmp) / "retry.jsonl"
            input_rows = [
                {"id": "tweet:1", "final": "final one"},
                {"id": "tweet:2", "final": "final two"},
            ]
            output_rows = [
                {"id": "tweet:1", "draft": "rough one"},
                {"id": "control_id_placeholder", "draft": "error"},
                {"id": "tweet:2", "draft": "rough two"},
            ]

            invalid = runner.validate_output(input_rows, output_rows, "chunk", invalid_path, retry_path)

            self.assertEqual(output_rows, [
                {"id": "tweet:1", "draft": "rough one"},
                {"id": "tweet:2", "draft": "rough two"},
            ])
            self.assertEqual(len(invalid), 1)
            saved = json.loads(invalid_path.read_text().strip())
            self.assertEqual(saved["reason"], "unexpected extra output row")
            self.assertEqual(saved["output"]["id"], "control_id_placeholder")
            self.assertFalse(retry_path.exists())

    def test_validate_output_can_quarantine_duplicate_expected_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid_path = Path(tmp) / "invalid.jsonl"
            retry_path = Path(tmp) / "retry.jsonl"
            input_rows = [
                {"id": "tweet:1", "final": "final one"},
                {"id": "tweet:2", "final": "final two"},
            ]
            output_rows = [
                {"id": "tweet:1", "draft": "rough one"},
                {"id": "tweet:1", "draft": "duplicate rough one"},
                {"id": "tweet:2", "draft": "rough two"},
            ]

            invalid = runner.validate_output(input_rows, output_rows, "chunk", invalid_path, retry_path)

            self.assertEqual(output_rows, [
                {"id": "tweet:1", "draft": "rough one"},
                {"id": "tweet:2", "draft": "rough two"},
            ])
            self.assertEqual(len(invalid), 1)
            saved = json.loads(invalid_path.read_text().strip())
            self.assertEqual(saved["reason"], "duplicate output row for expected id")
            self.assertFalse(retry_path.exists())

    def test_validate_output_can_quarantine_missing_expected_id_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid_path = Path(tmp) / "invalid.jsonl"
            retry_path = Path(tmp) / "retry.jsonl"
            input_rows = [
                {"id": "tweet:1", "final": "final one"},
                {"id": "tweet:2", "final": "final two"},
            ]
            output_rows = [{"id": "tweet:1", "draft": "rough one"}]

            invalid = runner.validate_output(input_rows, output_rows, "chunk", invalid_path, retry_path)

            self.assertEqual(output_rows, [{"id": "tweet:1", "draft": "rough one"}])
            self.assertEqual(len(invalid), 1)
            saved = json.loads(invalid_path.read_text().strip())
            self.assertEqual(saved["reason"], "missing output row for expected id")
            self.assertEqual(
                [json.loads(line) for line in retry_path.read_text().splitlines()],
                [{"id": "tweet:2", "final": "final two"}],
            )

    def test_validate_output_canonicalizes_long_tweet_suffix(self):
        input_rows = [{"id": "tweet:95045771069636610", "final": "final text"}]
        output_rows = [{"id": "s5045771069636610", "draft": "rough draft"}]

        runner.validate_output(input_rows, output_rows, "chunk")

        self.assertEqual(output_rows[0]["id"], "tweet:95045771069636610")

    def test_validate_output_rejects_short_tweet_suffix(self):
        input_rows = [{"id": "tweet:95045771069636610", "final": "final text"}]
        output_rows = [{"id": "x636610", "draft": "rough draft"}]

        with self.assertRaises(SystemExit):
            runner.validate_output(input_rows, output_rows, "chunk")

    def test_validate_output_rejects_bad_rows(self):
        input_rows = [{"id": "tweet:1", "final": "final text"}]
        cases = [
            [{"id": "tweet:1", "draft": "rough", "extra": "nope"}],
            [{"id": "tweet:2", "draft": "rough"}],
            [{"id": "tweet:1", "draft": ""}],
            [{"id": "tweet:1", "draft": "final text"}],
            [],
        ]

        for output_rows in cases:
            with self.subTest(output_rows=output_rows):
                with self.assertRaises(SystemExit):
                    runner.validate_output(input_rows, output_rows, "chunk")

    def test_parse_output_accepts_jsonl_code_fence(self):
        text = '```jsonl\n{"id":"tweet:1","draft":"rough"}\n```'
        self.assertEqual(
            runner.parse_output(text, "chunk"),
            [{"id": "tweet:1", "draft": "rough"}],
        )

    def test_parse_output_ignores_thinking_preamble(self):
        text = 'Thinking out loud...</think>{"id":"tweet:1","draft":"rough"}'
        self.assertEqual(
            runner.parse_output(text, "chunk"),
            [{"id": "tweet:1", "draft": "rough"}],
        )

    def test_parse_output_ignores_plain_text_preamble(self):
        text = 'I will output JSONL now.\n{"id":"tweet:1","draft":"rough"}'
        self.assertEqual(
            runner.parse_output(text, "chunk"),
            [{"id": "tweet:1", "draft": "rough"}],
        )

    def test_parse_output_repairs_missing_terminal_brace(self):
        text = '{"id":"tweet:1","draft":"rough"'
        self.assertEqual(
            runner.parse_output(text, "chunk"),
            [{"id": "tweet:1", "draft": "rough"}],
        )

    def test_parse_output_repairs_polluted_input_fields(self):
        text = (
            '{"id": "context": "Write an original tweet.", '
            '"final": "Want a 90% drop?", '
            '"id": "tweet:83781838862159872", '
            '"draft": "Are you worried about the impact?"}'
        )

        self.assertEqual(
            runner.parse_output(text, "chunk"),
            [{"id": "tweet:83781838862159872", "draft": "Are you worried about the impact?"}],
        )

    def test_parse_output_repairs_annotated_id_placeholder(self):
        text = (
            '{"id": "annotated_id_placeholder": "tweet:79865642248974336", '
            '"draft": "Did you know the U.S. government is targeting Bitcoin?"}'
        )

        self.assertEqual(
            runner.parse_output(text, "chunk"),
            [{
                "id": "tweet:79865642248974336",
                "draft": "Did you know the U.S. government is targeting Bitcoin?",
            }],
        )

    def test_parse_output_accepts_labeled_backtick_rows(self):
        text = (
            'Analysis first.\n'
            'Row 1: `{"id": "tweet:1", "draft": "rough one"}`\n'
            'Row 2: `{"id": "tweet:2", "draft": "rough two"}`\n'
            'More commentary after.'
        )

        self.assertEqual(
            runner.parse_output(text, "chunk"),
            [
                {"id": "tweet:1", "draft": "rough one"},
                {"id": "tweet:2", "draft": "rough two"},
            ],
        )

    def test_parse_output_allow_partial_skips_malformed_jsonl_lines(self):
        text = (
            '{"id": "tweet:1", "draft": "rough one"}\n'
            '{"id": "tweet:2\t\tbad runaway'
        )

        self.assertEqual(
            runner.parse_output(text, "chunk", allow_partial=True),
            [{"id": "tweet:1", "draft": "rough one"}],
        )

    def test_parse_output_allow_partial_skips_invalid_escape_repair_failure(self):
        text = (
            '{"id": "tweet:1", "draft": "rough one"}\n'
            '{"id": "tweet:2", "draft": "bad \\q escape"}'
        )

        self.assertEqual(
            runner.parse_output(text, "chunk", allow_partial=True),
            [{"id": "tweet:1", "draft": "rough one"}],
        )
        with self.assertRaises(SystemExit):
            runner.parse_output(text, "chunk")

    def test_parse_output_allow_partial_skips_extra_data_repair_failure(self):
        text = (
            '{"id": "tweet:1", "draft": "rough one"}\n'
            '{"id": "tweet:2", "draft": "bad" trailing"}'
        )

        self.assertEqual(
            runner.parse_output(text, "chunk", allow_partial=True),
            [{"id": "tweet:1", "draft": "rough one"}],
        )
        with self.assertRaises(SystemExit):
            runner.parse_output(text, "chunk")

    def test_parse_output_accepts_json_array_and_wrapped_rows(self):
        rows = [{"id": "tweet:1", "draft": "rough"}]
        self.assertEqual(runner.parse_output(json.dumps(rows), "chunk"), rows)
        self.assertEqual(runner.parse_output(json.dumps({"rows": rows}), "chunk"), rows)

    def test_extract_message_content_supports_alternate_shapes(self):
        self.assertEqual(
            runner.extract_message_content({
                "choices": [{"message": {"content": [{"type": "text", "text": "ok"}]}}],
            }),
            "ok",
        )
        self.assertEqual(
            runner.extract_message_content({
                "choices": [{"message": {"content": None}, "text": "fallback"}],
            }),
            "fallback",
        )

    def test_reasoning_details_detects_thinking_only_response(self):
        chars, finish_reason = runner.reasoning_details({
            "choices": [{
                "message": {"content": "", "reasoning": "thinking..."},
                "finish_reason": "length",
            }],
        })

        self.assertEqual(chars, len("thinking..."))
        self.assertEqual(finish_reason, "length")

    def test_parse_think_converts_cli_values(self):
        self.assertIsNone(runner.parse_think(None))
        self.assertIsNone(runner.parse_think("auto"))
        self.assertTrue(runner.parse_think("on"))
        self.assertFalse(runner.parse_think("off"))

    def test_ollama_endpoint_strips_openai_v1_suffix(self):
        self.assertEqual(
            runner.ollama_endpoint("http://localhost:11434/v1"),
            "http://localhost:11434/api/chat",
        )
        self.assertEqual(
            runner.ollama_endpoint("http://localhost:11434"),
            "http://localhost:11434/api/chat",
        )

    def test_call_chat_completion_routes_explicit_think_to_native_ollama(self):
        spec = {
            "provider": "Ollama (local)",
            "base_url": "http://localhost:11434/v1",
            "model": "gemma4:26b",
        }

        with patch.object(runner, "call_ollama_chat", return_value=("{}", {"choices": []})) as native:
            runner.call_chat_completion(
                spec,
                [{"id": "tweet:1", "context": "Write.", "final": "final"}],
                "instruction",
                think="off",
            )

        self.assertFalse(native.call_args.kwargs["think"])

    def test_empty_content_saves_raw_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = runner.raw_response_path(None, Path(tmp), Path(tmp) / "000.output.jsonl")
            runner.save_raw_response(
                path,
                request_model="gemma",
                output_path=Path(tmp) / "000.output.jsonl",
                extracted_content="",
                raw_response={"choices": [{"message": {"content": ""}}]},
            )
            saved = json.loads(path.read_text())

            self.assertEqual(saved["model"], "gemma")
            self.assertEqual(saved["extracted_content"], "")
            self.assertIn("raw_response", saved)

    def test_dry_run_resolves_chunks_without_writing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "draft_models.json"
            config_path.write_text(json.dumps({
                "models": {
                    "gemma-test": {
                        "base_url": "http://localhost:11434/v1",
                        "model": "gemma3:27b",
                    }
                }
            }))
            model_dir = root / "generation-2026-06-29" / "gemma-test"
            inputs = model_dir / "inputs"
            inputs.mkdir(parents=True)
            (inputs / "000.input.jsonl").write_text(
                json.dumps({
                    "id": "tweet:1",
                    "context": "Write an original tweet.",
                    "final": "final text",
                }) + "\n"
            )

            args = Namespace(
                config=config_path,
                model="gemma-test",
                generation_date="2026-06-29",
                generation_dir=root / "generation-2026-06-29",
                start=0,
                end=0,
                dry_run=True,
                temperature=None,
                max_tokens=None,
                timeout=120,
                overwrite=False,
                provider=None,
                base_url=None,
                mlx_model=None,
                raw_response_dir=None,
                debug_response=False,
                think=None,
                invalid_row_action="fail",
                invalid_row_dir=None,
                retry_input_dir=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                runner.run(args)

            self.assertIn("dry run: would generate 1 drafts", output.getvalue())
            self.assertFalse((model_dir / "outputs").exists())

    def test_skip_mode_quarantines_unparseable_chunk_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "draft_models.json"
            config_path.write_text(json.dumps({
                "models": {
                    "mlx-test": {
                        "backend": "mlx",
                        "model": "mlx-community/test",
                    }
                }
            }))
            model_dir = root / "generation-2026-06-29" / "mlx-test"
            inputs = model_dir / "inputs"
            inputs.mkdir(parents=True)
            input_row = {
                "id": "tweet:1",
                "context": "Write an original tweet.",
                "final": "final text",
            }
            (inputs / "000.input.jsonl").write_text(json.dumps(input_row) + "\n")
            args = Namespace(
                config=config_path,
                model="mlx-test",
                generation_date="2026-06-29",
                generation_dir=root / "generation-2026-06-29",
                start=0,
                end=0,
                dry_run=False,
                temperature=None,
                max_tokens=None,
                timeout=120,
                overwrite=True,
                provider=None,
                base_url=None,
                mlx_model=None,
                raw_response_dir=None,
                debug_response=False,
                think=None,
                invalid_row_action="skip",
                invalid_row_dir=None,
                retry_input_dir=None,
            )

            with patch.object(runner, "call_model", return_value=("thinking forever with no json", {"backend": "mlx"})):
                output = StringIO()
                with redirect_stdout(output):
                    runner.run(args)

            outputs = model_dir / "outputs"
            self.assertEqual((outputs / "000.output.jsonl").read_text(), "")
            retry_rows = [
                json.loads(line)
                for line in (outputs / "_retry_inputs" / "000.input.retry.jsonl").read_text().splitlines()
            ]
            self.assertEqual(retry_rows, [input_row])
            self.assertIn("1 invalid rows quarantined", output.getvalue())


if __name__ == "__main__":
    unittest.main()
