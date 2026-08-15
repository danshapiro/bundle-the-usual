"""Static contract tests for the execute-plan full-suite gate (v3.9.0).

Ports skill-the-usual 43c7033, 13e7b66, 860a6e6, e61a979, 9f04cd7: the gate
adopts or reuses an existing invocation at the same committed HEAD instead of
blindly launching, gates reruns on complete remediation, records unreached
scopes, and requires returning repo-started resources to a reusable state.
"""

import re
import unittest
from pathlib import Path

RECIPE_PATH = Path(__file__).resolve().parent.parent / "recipes" / "the-usual.yaml"
RECIPE = RECIPE_PATH.read_text(encoding="utf-8")


def gate_section() -> str:
    """The Full-suite gate procedure inside the execute-plan step."""
    start = RECIPE.index("      ## Full-suite gate")
    end = RECIPE.index("      ## Final whole-branch review")
    return RECIPE[start:end]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


GATE = norm(gate_section())


class TestInvocationAdoption(unittest.TestCase):
    def test_lookup_before_launch(self):
        self.assertIn(
            "inspect the current run's progress ledger and artifacts for an "
            "invocation on the same committed HEAD with that exact command",
            GATE,
        )

    def test_adopts_valid_passing_result(self):
        self.assertIn(
            "Adopt a valid passing result as the current logical invocation", GATE
        )

    def test_reuses_interrupted_invocation_with_valid_output(self):
        self.assertIn(
            "whether the process completed normally or was interrupted by "
            "infrastructure",
            GATE,
        )

    def test_awaits_or_resumes_running_invocation(self):
        self.assertIn("await or resume a matching running invocation", GATE)

    def test_no_blind_launch_wording_remains(self):
        self.assertNotIn("1. Run the repository's full test suite.", GATE)


class TestRemediationDiscipline(unittest.TestCase):
    def test_records_unreached_scopes(self):
        self.assertIn(
            "Also record every configured scope the runner did not reach", GATE
        )

    def test_remediation_completes_before_rerun(self):
        self.assertIn(
            "Complete that focused verification and those commits before "
            "another full-suite invocation",
            GATE,
        )

    def test_shared_causes_first(self):
        self.assertIn("addressing shared causes first", GATE)

    def test_rerun_fail_closed(self):
        self.assertIn(
            "only after the complete remediation pass or a concrete "
            "infrastructure recovery",
            GATE,
        )

    def test_pass_criterion_unchanged(self):
        self.assertIn("The gate passes at that point, and only at that point.", GATE)


class TestLedgerAndResources(unittest.TestCase):
    def test_preexisting_receipt_cross_referenced_from_baseline(self):
        self.assertIn(
            "cross-referenced from the ledger's first (baseline) entry", GATE
        )

    def test_resources_returned_to_reusable_state(self):
        self.assertIn(
            "documented reusable state before another interacting run", GATE
        )


if __name__ == "__main__":
    unittest.main()
