import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "training" / "promote.py"
spec = importlib.util.spec_from_file_location("promote", MODULE_PATH)
promote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promote)


def write_scorecard(adapter, scorecard):
    adapter.mkdir(parents=True)
    (adapter / "scorecard.json").write_text(json.dumps(scorecard))
    (adapter / "adapter_config.json").write_text("{}")


class PromoteTests(unittest.TestCase):
    def test_kept_champion_is_successful_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            champion = root / "champion"
            write_scorecard(candidate, {
                "gate_pass_rate": 0.94,
                "similarity": 0.77,
            })
            write_scorecard(champion, {
                "gate_pass_rate": 0.93,
                "similarity": 0.90,
            })

            stdout = StringIO()
            with patch("sys.argv", [
                "promote.py",
                "--candidate", str(candidate),
                "--champion", str(champion),
            ]), redirect_stdout(stdout):
                code = promote.main()

            self.assertEqual(code, 0)
            self.assertIn("kept champion", stdout.getvalue())
            self.assertIn("similarity regressed", stdout.getvalue())

    def test_promotion_copies_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            champion = root / "champion"
            write_scorecard(candidate, {
                "gate_pass_rate": 0.94,
                "similarity": 0.90,
            })
            write_scorecard(champion, {
                "gate_pass_rate": 0.93,
                "similarity": 0.80,
            })

            stdout = StringIO()
            with patch("sys.argv", [
                "promote.py",
                "--candidate", str(candidate),
                "--champion", str(champion),
            ]), redirect_stdout(stdout):
                code = promote.main()

            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads((champion / "scorecard.json").read_text())["similarity"],
                0.90,
            )


if __name__ == "__main__":
    unittest.main()
