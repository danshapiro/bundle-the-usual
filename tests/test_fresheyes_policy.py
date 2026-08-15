"""Static contract tests for Fresh Eyes review policy (v3.12.0).

Policy-only port of skill-the-usual 53b8f04 (Seam 2): same-family reviewer
selections are rejected as NO_MARKER, conflicting verdict markers are not
passed, and every round's log entry records the reviewer identity label.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPE = (ROOT / "recipes" / "the-usual.yaml").read_text(encoding="utf-8")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def step_section(step_id: str) -> str:
    start = RECIPE.index(f'  - id: "{step_id}"')
    nxt = RECIPE.find("\n  - id: ", start + 1)
    return RECIPE[start:] if nxt == -1 else RECIPE[start:nxt]


class TestSameFamilyRejection(unittest.TestCase):
    def check_step(self, step_id: str):
        step = norm(step_section(step_id))
        self.assertIn("a same-family selection is rejected, not run", step)
        self.assertIn("treat it as NO_MARKER", step)

    def test_fresheyes_plan_rejects_same_family(self):
        self.check_step("fresheyes-plan")

    def test_fresheyes_delta_rejects_same_family(self):
        self.check_step("fresheyes-delta")


class TestConflictingMarkersNotPassed(unittest.TestCase):
    def check_step(self, step_id: str):
        self.assertIn("CONFLICTING markers in one report", norm(step_section(step_id)))

    def test_fresheyes_plan(self):
        self.check_step("fresheyes-plan")

    def test_fresheyes_delta(self):
        self.check_step("fresheyes-delta")


class TestReviewerIdentityLabel(unittest.TestCase):
    def check_step(self, step_id: str, log_name: str):
        step = norm(step_section(step_id))
        self.assertIn(log_name, step)
        self.assertIn("reviewer identity label", step)
        self.assertIn("{{reviewer_provider}}/{{reviewer_model}}", step)

    def test_fresheyes_plan_logs_label(self):
        self.check_step("fresheyes-plan", "fresheyes-plan.md")

    def test_fresheyes_delta_logs_label(self):
        self.check_step("fresheyes-delta", "fresheyes-delta.md")


if __name__ == "__main__":
    unittest.main()
