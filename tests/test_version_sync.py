"""Release-ledger test: version fields stay in sync across the bundle.

The recipe's version field and changelog are the release ledger; bundle.md and
behaviors/the-usual.yaml must match (see v3.7.0 changelog entry).
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def version_of(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    # Accept both `version: "3.9.0"` (recipe) and `version: 3.9.0`.
    match = re.search(r'^\s*version:\s*"?(\d+\.\d+\.\d+)"?\s*$', text, re.MULTILINE)
    assert match is not None, f"no version field found in {path.name}"
    return match.group(1)


class TestVersionSync(unittest.TestCase):
    def test_versions_match(self):
        recipe = version_of(ROOT / "recipes" / "the-usual.yaml")
        bundle = version_of(ROOT / "bundle.md")
        behavior = version_of(ROOT / "behaviors" / "the-usual.yaml")
        self.assertEqual(recipe, bundle, "bundle.md version out of sync")
        self.assertEqual(recipe, behavior, "behaviors/the-usual.yaml version out of sync")

    def test_changelog_head_matches_recipe_version(self):
        recipe_text = (ROOT / "recipes" / "the-usual.yaml").read_text(encoding="utf-8")
        recipe = version_of(ROOT / "recipes" / "the-usual.yaml")
        changelog = re.search(r"# v(\d+\.\d+\.\d+) \(", recipe_text)
        assert changelog is not None, "no changelog entry found"
        self.assertEqual(
            recipe,
            changelog.group(1),
            "newest changelog entry does not match recipe version",
        )


if __name__ == "__main__":
    unittest.main()
