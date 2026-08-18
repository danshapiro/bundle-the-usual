"""Behavior tests for the recap outcome hard-gate step.

Ports skill-the-usual 08fa196: a terminal hard-gate bash step re-runs the
deterministic validator (scripts/validate-recap-outcome.py) against the
committed recap, resolving the validator path via the bundle registry or an
explicit override and failing closed when it can't be found.
"""

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPE = (ROOT / "recipes" / "the-usual.yaml").read_text(encoding="utf-8")


def gate_command() -> str:
    section = RECIPE[RECIPE.index('  - id: "recap-outcome-validate"') :]
    marker = "    command: |\n"
    start = section.index(marker) + len(marker)
    lines = []
    for line in section[start:].splitlines():
        if line.startswith("      "):
            lines.append(line[6:])
        elif not line:
            lines.append("")
        else:
            break
    return "\n".join(lines) + "\n"


def write_fake_bundle(bundle_dir: Path) -> Path:
    (bundle_dir / "scripts").mkdir(parents=True)
    (bundle_dir / "bundle.md").write_text("bundle: {}\n", encoding="utf-8")
    validator = bundle_dir / "scripts" / "validate-recap-outcome.py"
    validator.write_text(
        textwrap.dedent(
            """\
            import sys
            from pathlib import Path

            recap = Path(sys.argv[1])
            recap.with_suffix(".validator").write_text(
                str(Path(__file__).resolve()),
                encoding="utf-8",
            )
            """
        ),
        encoding="utf-8",
    )
    return validator


def run_gate(
    home: Path,
    logs_dir: Path,
    registry_local_path: Path,
    *,
    bundle_override: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    registry = home / ".amplifier" / "registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "bundles": {
                    "the-usual": {
                        "local_path": str(registry_local_path),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    logs_dir.mkdir()
    (logs_dir / "recap.md").write_text("# Recap\n", encoding="utf-8")

    environment = {
        **os.environ,
        "HOME": str(home),
        "LOGS_DIR": str(logs_dir),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    environment.pop("THE_USUAL_BUNDLE_DIR", None)
    if bundle_override is not None:
        environment["THE_USUAL_BUNDLE_DIR"] = str(bundle_override)

    return subprocess.run(
        ["bash", "-c", gate_command()],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=10,
    )


class TestHardGateStep(unittest.TestCase):
    def test_validator_script_is_in_repository(self):
        self.assertTrue((ROOT / "scripts" / "validate-recap-outcome.py").is_file())

    def test_registry_fallback_accepts_bundle_directory_or_manifest_path(self):
        for local_path_form in ("directory", "manifest"):
            with (
                self.subTest(local_path_form=local_path_form),
                tempfile.TemporaryDirectory() as temporary,
            ):
                sandbox = Path(temporary)
                bundle_dir = sandbox / "bundle with spaces"
                validator = write_fake_bundle(bundle_dir)
                local_path = (
                    bundle_dir
                    if local_path_form == "directory"
                    else bundle_dir / "bundle.md"
                )

                result = run_gate(
                    sandbox / "home",
                    sandbox / "logs",
                    local_path,
                )

                self.assertEqual(0, result.returncode, result.stderr)
                invoked = (sandbox / "logs" / "recap.validator").read_text(
                    encoding="utf-8"
                )
                self.assertEqual(str(validator.resolve()), invoked)

    def test_explicit_bundle_dir_takes_precedence_over_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            registered_bundle = sandbox / "registered"
            registered_bundle.mkdir()
            (registered_bundle / "bundle.md").write_text("", encoding="utf-8")
            override_bundle = sandbox / "override"
            validator = write_fake_bundle(override_bundle)

            result = run_gate(
                sandbox / "home",
                sandbox / "logs",
                registered_bundle / "bundle.md",
                bundle_override=override_bundle,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            invoked = (sandbox / "logs" / "recap.validator").read_text(encoding="utf-8")
            self.assertEqual(str(validator.resolve()), invoked)

    def test_gate_fails_closed_with_resolved_missing_validator_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            bundle_dir = sandbox / "bundle"
            bundle_dir.mkdir()
            manifest = bundle_dir / "bundle.md"
            manifest.write_text("", encoding="utf-8")

            result = run_gate(
                sandbox / "home",
                sandbox / "logs",
                manifest,
            )

            expected = bundle_dir / "scripts" / "validate-recap-outcome.py"
            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                f"FATAL: recap validator is unavailable at {expected}",
                result.stderr,
            )

    def test_gate_is_terminal_step(self):
        self.assertLess(
            RECIPE.index('  - id: "recap"'),
            RECIPE.index('  - id: "recap-outcome-validate"'),
        )
        self.assertNotIn(
            "\n  - id:",
            RECIPE[RECIPE.index('  - id: "recap-outcome-validate"') + 1 :].rstrip("\n")
            + "\n",
        )


if __name__ == "__main__":
    unittest.main()
