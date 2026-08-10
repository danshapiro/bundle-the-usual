from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "recipes" / "the-usual.yaml"
BEGIN_MARKER = "# --- BEGIN embedded validate-recap-outcome.py"
END_MARKER = "# --- END embedded validate-recap-outcome.py"

VALID_PAYLOAD = {
    "schema_version": 1,
    "status": "success",
    "reason": None,
    "execution_tasks": {"completed": 2, "total": 2},
    "full_suite_gate": {"result": "passed"},
    "review_loops": {
        "plan": {"rounds": 1, "final_verdict": "PASSED"},
        "delta": {"rounds": 1, "final_verdict": "PASSED"},
    },
    "head_commit_sha": "0123456789abcdef0123456789abcdef01234567",
}


def recap_document(payload: object) -> str:
    return (
        "# Recap\n\nHuman-facing content.\n\n"
        "## Outcome Block\n\n```json\n"
        + json.dumps(payload, indent=2)
        + "\n```\n"
    )


class RecipeRecapBlockTest(unittest.TestCase):
    prompt: str

    @classmethod
    def setUpClass(cls) -> None:
        recipe = yaml.safe_load(RECIPE.read_text(encoding="utf-8"))
        steps = {step.get("id"): step for step in recipe["steps"]}
        cls.prompt = steps["recap"]["prompt"]

    def test_recap_prompt_declares_outcome_block(self) -> None:
        self.assertIn("## Outcome Block", self.prompt)
        self.assertIn('"schema_version": 1', self.prompt)
        self.assertIn(BEGIN_MARKER, self.prompt)
        self.assertIn(END_MARKER, self.prompt)

    def test_embedded_validator_validates_fixtures(self) -> None:
        start = self.prompt.index(BEGIN_MARKER)
        start = self.prompt.index("\n", start) + 1
        end = self.prompt.index(END_MARKER)
        source = self.prompt[start:end]
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "validate-recap-outcome.py"
            script.write_text(source, encoding="utf-8")
            good = Path(directory) / "good.md"
            good.write_text(recap_document(VALID_PAYLOAD), encoding="utf-8")
            bad = Path(directory) / "bad.md"
            bad.write_text("# Recap\n\nNo block here.\n", encoding="utf-8")

            ok = subprocess.run(
                [sys.executable, str(script), str(good)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(ok.stdout, "")

            fail = subprocess.run(
                [sys.executable, str(script), str(bad)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(fail.returncode, 1)
            self.assertIn("missing terminal Outcome Block", fail.stderr)


if __name__ == "__main__":
    unittest.main()
