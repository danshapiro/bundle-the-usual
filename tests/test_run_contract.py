"""Tripwire tests for the run contract (v3.11.0).

Ports skill-the-usual 86377ed (Seam 1), adapted: the author-facing contract
lives in recipe comments, the baseline ledger schema in the workspace-setup
prompt, the blocker-resolution rule in the execute-plan prompt, and the
touchpoint inventory in tests/fixtures/touchpoints.json — asserted verbatim
against the recipe so refactors cannot silently drop stops or prohibitions.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPE = (ROOT / "recipes" / "the-usual.yaml").read_text(encoding="utf-8")
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "touchpoints.json").read_text(encoding="utf-8")
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


NORMED_RECIPE = norm(RECIPE)


def step_section(step_id: str) -> str:
    start = RECIPE.index(f'  - id: "{step_id}"')
    nxt = RECIPE.find("\n  - id: ", start + 1)
    return RECIPE[start:] if nxt == -1 else RECIPE[start:nxt]


class TestBaselineLedger(unittest.TestCase):
    def setUp(self):
        self.setup = step_section("workspace-setup")

    def test_baseline_block_exists_in_workspace_setup(self):
        self.assertIn("## Baseline (recorded at workspace setup)", self.setup)

    def test_baseline_field_schema(self):
        for field in (
            "- time:",
            "- base commit:",
            "- command:",
            "- exit status:",
            "- result:",
            "- pre-existing failures:",
            "- evidence:",
        ):
            self.assertIn(field, self.setup, f"missing baseline field {field}")

    def test_baseline_runs_full_suite_once(self):
        self.assertIn("Establish the baseline (required before this step may complete)", norm(self.setup))

    def test_no_backfilling(self):
        self.assertIn("backfilling the list after the fact is not allowed", norm(self.setup))

    def test_execute_plan_expects_existing_ledger(self):
        execute = step_section("execute-plan")
        self.assertIn("recreate it if recovery removed it", norm(execute))


class TestBlockerResolutionRule(unittest.TestCase):
    def test_rule_section_in_execute_plan(self):
        execute = step_section("execute-plan")
        self.assertIn("## Blocker resolution rule", execute)

    def test_rule_substance(self):
        execute = norm(step_section("execute-plan"))
        self.assertIn("binding until cleared by evidence or re-review", execute)
        self.assertIn("KISS, YAGNI", execute)
        self.assertIn("never clear a blocker by editing or downgrading the finding", execute)


class TestAuthorContractComment(unittest.TestCase):
    def test_author_section_present(self):
        self.assertIn("# RUN CONTRACT (author-facing", RECIPE)

    def test_base_ref_invariance_documented(self):
        self.assertIn("base_ref...HEAD", RECIPE)


class TestTouchpointInventory(unittest.TestCase):
    def test_inventory_is_not_empty(self):
        self.assertGreaterEqual(len(FIXTURE["entries"]), 10)

    def test_kinds_are_known(self):
        for entry in FIXTURE["entries"]:
            self.assertIn(entry["kind"], {"HARD STOP", "PROHIBITION", "QUESTION"})

    def test_cited_steps_exist(self):
        for entry in FIXTURE["entries"]:
            self.assertIn(f'  - id: "{entry["step"]}"', RECIPE, entry["step"])

    def test_quotes_are_verbatim_in_recipe(self):
        for entry in FIXTURE["entries"]:
            self.assertIn(
                norm(entry["quote"]),
                NORMED_RECIPE,
                f"lost or reworded touchpoint ({entry['kind']}, {entry['step']}): {entry['quote']}",
            )

    def test_quotes_are_unique(self):
        quotes = [norm(e["quote"]) for e in FIXTURE["entries"]]
        self.assertEqual(len(quotes), len(set(quotes)), "duplicate quotes in inventory")


if __name__ == "__main__":
    unittest.main()
