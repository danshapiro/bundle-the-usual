"""Execute the port's brief and review-package interfaces; no agent simulation."""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

import test_user_request_contract as contract


class V7PortFixtures(unittest.TestCase):
    def test_planner_header_round_trips_the_request_without_its_h1(self):
        section = contract.step_section("write-plan")
        start = section.index("      ```markdown\n", section.index("## Plan Document Header"))
        start += len("      ```markdown\n")
        end = section.index("\n      ```", start)
        header = textwrap.dedent(section[start:end])
        request = (
            "## User Request\n\n### Requested result\nExact request.\n\n"
            "### Explicit constraints\n- Keep all of this.\n\n"
            "### Accepted tradeoffs and residuals\n- None stated."
        )
        header = header.replace(
            "[Insert the complete current `## User Request` block unchanged exactly once.]",
            request,
        )
        result, brief = contract.TestExecutableRecipeRegressions.run_task_brief(
            header + "\n### Task 1: Feature\nImplement it.\n", 1
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(brief[:brief.index(b"## Global Constraints")],
                         request.encode() + b"\n\n")

    def test_review_focus_is_not_a_global_constraint(self):
        request = (
            "## User Request\n\n### Requested result\nShip the feature.\n\n"
            "### Explicit constraints\n- Preserve bytes.\n\n"
            "### Accepted tradeoffs and residuals\n- None stated.\n\n"
        )
        plan = (
            "# Feature Implementation Plan\n\nSteps use checkboxes.\n\n"
            + request
            + "**Goal:** Ship it.\n\n## Global Constraints\nGLOBAL_VALUE\n\n"
            "## Review Focus\nFOCUS_IS_NOT_A_GLOBAL_REQUIREMENT\n\n---\n"
            "### Task 1: Feature\nTest the behavior.\n"
        )
        result, brief = contract.TestExecutableRecipeRegressions.run_task_brief(plan, 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            brief,
            (request + "## Global Constraints\nGLOBAL_VALUE\n\n"
             "### Task 1: Feature\nTest the behavior.\n").encode(),
        )

    def test_review_packages_cover_full_range_and_keep_distinct_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.git(repo, "init", "-q")
            base = self.commit(repo, "base", "base\n")
            first = self.commit(repo, "first", "first\n")
            head = self.commit(repo, "second", "second\n")
            result = self.package(repo, base, head)
            self.assertEqual(result.returncode, 0, result.stderr)
            artifacts = list(repo.rglob("*.diff"))
            self.assertEqual(len(artifacts), 1)
            original = artifacts[0].read_bytes()
            self.assertIn(b"first", original)
            self.assertIn(b"second", original)
            self.assertIn(b"+first", original)
            self.assertIn(b"+second", original)
            self.assertEqual(self.package(repo, base, head).returncode, 0)
            self.assertEqual(len(list(repo.rglob("*.diff"))), 2)
            self.assertEqual(artifacts[0].read_bytes(), original)
            self.assertEqual(self.package(repo, first, head).returncode, 0)
            self.assertEqual(len(list(repo.rglob("*.diff"))), 3)

    def test_invalid_review_ranges_fail_without_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.git(repo, "init", "-q")
            base = self.commit(repo, "base", "base\n")
            head = self.commit(repo, "head", "head\n")
            self.git(repo, "checkout", "--orphan", "unrelated")
            other = self.commit(repo, "other", "other\n")
            for left, right in ((head, head), (head, base), (base, other), ("missing", head)):
                with self.subTest(base=left, head=right):
                    result = self.package(repo, left, right)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(list(repo.rglob("*.diff")), [])

    def test_whole_branch_package_uses_explicit_worktree_and_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            repo = outside / "worktree with spaces"
            repo.mkdir()
            self.git(repo, "init", "-q")
            base = self.commit(repo, "base", "base\n")
            head = self.commit(repo, "feature", "feature\n")
            logs = outside / "logs with spaces"
            result = subprocess.run(
                ["bash", "-c", contract.embedded_bash_after("REVIEW PACKAGE — commit list")],
                cwd=outside,
                env={**os.environ, "BASE": base, "HEAD_REF": head,
                     "WORKTREE_PATH": str(repo), "LOGS_DIR": str(logs),
                     "REVIEW_SCOPE": "whole-branch"},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            artifacts = list((logs / "reports").glob("*.diff"))
            self.assertEqual(len(artifacts), 1)
            self.assertIn(b"+feature", artifacts[0].read_bytes())
            self.assertEqual(list(repo.rglob("*.diff")), [])

    @staticmethod
    def git(repo, *args):
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=Fixture",
             "-c", "user.email=fixture@example.invalid", *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def commit(self, repo, name, content):
        (repo / name).write_text(content)
        self.git(repo, "add", name)
        self.git(repo, "commit", "-qm", name)
        return self.git(repo, "rev-parse", "HEAD")

    @staticmethod
    def package(repo, base, head):
        return subprocess.run(
            ["bash", "-c", contract.embedded_bash_after("REVIEW PACKAGE — commit list")],
            cwd=repo, env={**os.environ, "BASE": base, "HEAD_REF": head,
                          "WORKTREE_PATH": str(repo)},
            capture_output=True, text=True,
        )


if __name__ == "__main__":
    unittest.main()
