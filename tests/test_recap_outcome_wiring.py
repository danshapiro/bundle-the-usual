"""Static contract tests for the recap outcome block wiring (v3.10.0).

Ports skill-the-usual 08fa196: the recap must end with exactly one
"## Outcome Block" heading and a machine-readable json object, the recap step
must write recap.md and self-validate, and a terminal hard-gate bash step
re-runs the deterministic validator (scripts/validate-recap-outcome.py).
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPE = (ROOT / "recipes" / "the-usual.yaml").read_text(encoding="utf-8")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class TestRecapOutcomeBlockContract(unittest.TestCase):
    def test_recap_step_requires_exactly_one_outcome_block(self):
        recap = RECIPE[RECIPE.index('  - id: "recap"') :]
        self.assertIn('exactly one "## Outcome Block" heading', norm(recap))

    def test_recap_writes_recap_file(self):
        recap = RECIPE[RECIPE.index('  - id: "recap"') :]
        self.assertIn("{{workspace.logs_dir}}/recap.md", recap)

    def test_recap_step_self_validates(self):
        recap = RECIPE[RECIPE.index('  - id: "recap"') :]
        self.assertIn("scripts/validate-recap-outcome.py", recap)
        self.assertIn("fix + rerun until", norm(recap))

    def test_validator_script_is_in_repository(self):
        self.assertTrue((ROOT / "scripts" / "validate-recap-outcome.py").is_file())

    def test_schema_fields_documented(self):
        for field in (
            "schema_version",
            "non-convergence",
            "head_commit_sha",
            "NO_MARKER",
            "NOT_RUN",
        ):
            self.assertIn(field, RECIPE)


class TestHardGateStep(unittest.TestCase):
    def _gate(self) -> str:
        start = RECIPE.index('  - id: "recap-outcome-validate"')
        return RECIPE[start:]

    def test_gate_step_exists_and_is_bash(self):
        gate = self._gate()
        self.assertIn('type: "bash"', gate)

    def test_gate_runs_validator_on_recap_file(self):
        gate = self._gate()
        self.assertIn("{{workspace.logs_dir}}/recap.md", gate)
        self.assertIn('python3 "$VALIDATOR" "$RECAP"', gate)

    def test_gate_fails_loudly(self):
        gate = norm(self._gate())
        self.assertEqual(gate.count("FATAL:"), 3)
        self.assertIn('on_error: "fail"', gate)

    def test_gate_resolves_bundle_dir(self):
        gate = self._gate()
        self.assertIn("THE_USUAL_BUNDLE_DIR", gate)
        self.assertIn("registry.json", gate)

    def test_gate_is_terminal_step(self):
        self.assertLess(RECIPE.index('  - id: "recap"'), RECIPE.index('  - id: "recap-outcome-validate"'))
        self.assertNotIn("\n  - id:", RECIPE[RECIPE.index('  - id: "recap-outcome-validate"') + 1 :].rstrip("\n") + "\n")


if __name__ == "__main__":
    unittest.main()
