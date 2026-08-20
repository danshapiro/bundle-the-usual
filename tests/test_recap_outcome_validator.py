from __future__ import annotations

from copy import deepcopy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-recap-outcome.py"
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


def recap(payload: object) -> str:
    return (
        "## Outcome Block\n\n```json\n"
        + json.dumps(payload, indent=2)
        + "\n```\n\n# Recap\n\nHuman-facing content.\n"
    )


class RecapOutcomeValidatorTest(unittest.TestCase):
    def run_path(self, path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(path), *extra],
            check=False,
            capture_output=True,
            text=True,
        )

    def run_document(self, document: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recap.md"
            path.write_text(document, encoding="utf-8")
            return self.run_path(path)

    def assert_invalid(self, document: str, message: str) -> None:
        result = self.run_document(document)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"invalid outcome block: {message}", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_accepts_well_formed_outcome_block(self) -> None:
        result = self.run_document(recap(VALID_PAYLOAD))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "")

    def test_rejects_missing_outcome_block(self) -> None:
        self.assert_invalid("# Recap\n\nHuman-facing content.\n", "missing leading Outcome Block")

    def test_rejects_missing_required_field(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        del payload["head_commit_sha"]
        self.assert_invalid(recap(payload), "missing required field: head_commit_sha")

    def test_rejects_malformed_structure(self) -> None:
        document = "## Outcome Block\n\n```yaml\n{broken\n```\n"
        self.assert_invalid(document, "expected one leading json fence")

    def test_rejects_unknown_status(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        payload["status"] = "stalled"
        self.assert_invalid(recap(payload), "status must be one of: success, non-convergence")

    def test_rejects_invalid_json(self) -> None:
        document = "## Outcome Block\n\n```json\n{broken\n```\n"
        self.assert_invalid(document, "invalid JSON")

    def test_rejects_leading_content(self) -> None:
        self.assert_invalid(
            "# Recap\n\nHuman-facing content.\n\n" + recap(VALID_PAYLOAD),
            "outcome block must come first",
        )

    def test_rejects_unknown_key_and_bad_types(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        payload["extra"] = True
        self.assert_invalid(recap(payload), "unknown field: extra")

        payload = deepcopy(VALID_PAYLOAD)
        payload["execution_tasks"]["completed"] = True
        self.assert_invalid(recap(payload), "execution_tasks.completed must be an integer")

        payload = deepcopy(VALID_PAYLOAD)
        payload["status"] = ["success"]
        self.assert_invalid(
            recap(payload), "status must be one of: success, non-convergence"
        )

    def test_rejects_nested_key_changes(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        del payload["review_loops"]["plan"]["rounds"]
        self.assert_invalid(
            recap(payload), "missing required field: review_loops.plan.rounds"
        )

        payload = deepcopy(VALID_PAYLOAD)
        payload["full_suite_gate"]["detail"] = "ok"
        self.assert_invalid(recap(payload), "unknown field: full_suite_gate.detail")

    def test_accepts_non_convergence_outcome(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        payload.update(status="non-convergence", reason="Work remains.")
        payload["execution_tasks"] = {"completed": 1, "total": 2}
        payload["full_suite_gate"]["result"] = "not-run"
        payload["review_loops"] = {
            "plan": {"rounds": 0, "final_verdict": "NOT_RUN"},
            "delta": {"rounds": 0, "final_verdict": "NOT_RUN"},
        }
        result = self.run_document(recap(payload))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "")

    def test_rejects_semantically_inconsistent_payloads(self) -> None:
        cases = [
            (("schema_version",), 2, "schema_version must equal 1"),
            (("execution_tasks", "completed"), 3, "completed must be <= total"),
            (("execution_tasks", "completed"), 1, "success requires complete tasks"),
            (("status",), "non-convergence", "non-convergence requires a non-empty reason"),
            (("review_loops", "plan", "rounds"), 4, "plan review rounds must be between 0 and 3"),
            (("review_loops", "plan", "final_verdict"), "NOT_RUN", "NOT_RUN requires zero rounds"),
            (("review_loops", "delta", "rounds"), 6, "delta review rounds must be between 0 and 5"),
            (("reason",), "unneeded", "success reason must be null"),
            (("full_suite_gate", "result"), "unknown", "full_suite_gate.result must be one of the allowed values"),
            (("review_loops", "plan", "final_verdict"), "UNKNOWN", "final_verdict must be one of the allowed values"),
            (("head_commit_sha",), "not-a-sha", "head_commit_sha must be 40 lowercase hex characters"),
        ]
        for keys, value, message in cases:
            with self.subTest(keys=keys, value=value):
                payload = deepcopy(VALID_PAYLOAD)
                target = payload
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                self.assert_invalid(recap(payload), message)

        payload = deepcopy(VALID_PAYLOAD)
        payload.update(status="non-convergence", reason="No unsuccessful fact.")
        self.assert_invalid(
            recap(payload), "non-convergence requires an unsuccessful run fact"
        )

    def test_rejects_duplicate_outcome_headings(self) -> None:
        document = recap(VALID_PAYLOAD).replace(
            "## Outcome Block", "## Outcome Block\n\n## Outcome Block", 1
        )
        self.assert_invalid(document, "exactly one Outcome Block")

    def test_rejects_unreadable_recap_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_path(Path(directory) / "missing.md")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unable to read recap:", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_rejects_wrong_argument_count(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr.lower())

        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "first.md", "second.md"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
