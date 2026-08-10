# Upstream Port and Pin Implementation Plan

> **For agentic workers:** This plan is executed task-by-task by the
> workflow's execute stage: a fresh implementer per task, with a spec +
> quality review after each task. Steps use checkbox (`- [ ]`) syntax
> for tracking.

**Goal:** Port the best improvements from upstream `skill-the-usual`
(range `d447273..a100fac`) into this bundle's canonical recipe
`recipes/the-usual.yaml`, then formally pin the upstream version in the
recipe header.

**Architecture:** Four independent, sequential changes to a single-repo
bundle: (1) a byte-faithful port of upstream's standalone recap-outcome
validator plus its test suite; (2) a machine-readable Outcome Block added
to the recipe's recap step — spliced in programmatically so the validator
source is embedded byte-perfectly into the recipe prompt; (3) the
full-suite gate hardening semantics rewritten as prose in the recipe's
execute-plan step, translated to this bundle's mechanisms; (4) a formal
upstream pin line, changelog entry, and version bump. All recipe edits
are additive prose/comment changes — no step structure, output contract,
guard, anchor, or skill-whitelist changes.

**Tech Stack:** YAML (pyyaml 6.0.1 available as `python3 -c "import
yaml"`), Python 3 stdlib only (`json`, `pathlib`, `re`, `sys`,
`subprocess`, `unittest`, `tempfile`), git.

## Global Constraints

- Worktree root (all work happens here): `/home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin`, branch `speed-v3.8.0-draft`, base HEAD `e44ee2d`. Every command below runs from this root (`cd` there first) unless it says otherwise.
- `/home/dan/code/skill-the-usual` is **read-only reference material**. Never write to it, commit to it, or change its checkout in any way. Only `git -C /home/dan/code/skill-the-usual show/diff/log/rev-parse ...` reads are allowed.
- Upstream pin SHA (the commit actually reviewed for this port): `a100facc784e93ef9fd8c6ef66658a95c1cdaeca` (= `origin/main` of skill-the-usual; short `a100fac`). Reviewed range: `d447273..a100fac`.
- EXPLICITLY OUT OF SCOPE (do not do, in any task): adopting `run-state.md` or baseline-ledger machinery; changing Fresh Eyes transport (the bundle deliberately uses `delegate()` — do not import harness requirements or `reviewer-prompt.md`); CI drift tripwires; vendoring/sync scripts or byte-equality-with-upstream tests; upstreaming anything to skill-the-usual.
- Keep ALL existing recipe safeguards intact: 12 steps, every existing output contract, the collect steps (`write-plan-collect`, `load-bearing-collect`, `execute-collect`), both halt guards, the `/tmp/the-usual-pending-output.{{session.id}}.json` anchor, the skill-load whitelist (stock `using-git-worktrees` and `requesting-code-review` only), progress banners, DELEGATION MANDATE / TURN ECONOMY / EXPLORATION REUSE blocks.
- `recipes/the-usual.yaml` must parse cleanly after EVERY modification: `python3 -c "import yaml; d=yaml.safe_load(open('recipes/the-usual.yaml', encoding='utf-8')); print(d['version'], len(d['steps']))"` must print the expected version and `12`.
- Versioning conventions (per v3.5.0/v3.6.0/v3.8.0-draft precedent): new changelog entry at the TOP of the changelog (directly under the CHANGELOG banner), heading format `# vX.Y.Z (YYYY-MM-DD):`; version bump in the recipe's `version:` field only (currently `"3.8.0"` at ~line 314). `bundle.md` and `behaviors/the-usual.yaml` deliberately stay at 3.7.0 — they are synced in dedicated hygiene commits at release time (v3.7.0 precedent), and the draft precedent (v3.8.0-draft) did not touch them. Do NOT edit them.
- The recipe engine rejects pre-release version tags, so the YAML `version:` field carries `"3.9.0"` while the changelog heading carries `v3.9.0-draft` — exactly mirroring the existing v3.8.0-draft entry.
- README.md is not modified (strict scope: port + pin, nothing else). Do not create any markdown docs other than this plan.
- The recipe file mixes `--` and `—` dash characters. All NEW text in this plan uses ASCII `--` only. When an edit anchor ("old string") fails to match, read the actual lines from the file and match the file's characters exactly — the file is truth; do not retype new content, only fix the anchor.
- Commits stay focused and atomic: one commit per task, exactly the files named in the task.
- Full test command (used from Task 1 on): `python3 -m unittest discover -s tests -v`. It must pass at the end of every task after Task 1.

## Upstream facts (for implementers with zero context)

- Upstream repo: `/home/dan/code/skill-the-usual` (a Claude-Code "skill" repo; this bundle is a sibling dialect of it as a single self-contained Amplifier recipe).
- Upstream PR #5 (commit `08fa196`) added: `subskills/usual-recap.md` "Outcome Block" section (every recap ends with exactly one `## Outcome Block` heading + one terminal ```` ```json ```` fence), `scripts/validate-recap-outcome.py` (stdlib-only validator, exit 0 = valid / 1 = invalid block / 2 = unreadable path or wrong argv), and `tests/test_recap_outcome_validator.py` (unittest suite driving the real CLI via subprocess).
- Upstream gate hardening (5 commits `43c7033`, `13e7b66`, `860a6e6`, `e61a979`, `9f04cd7`, all touching only `subskills/usual-executing-plans.md`): the full-suite gate now identifies the exact command, adopts/awaits/resumes a matching prior invocation at the same committed HEAD before launching, records launches beforehand, inventories unreached scopes, returns services/queues to reusable state, and loops fail-closed.
- This bundle has NO `run-state.md`, NO baseline ledger, NO `usual-sdd/` dir. Its equivalents: the progress ledger at `$(git rev-parse --git-path sdd)/progress.md` inside the target worktree, JSON output contracts + per-session `/tmp` anchor files, and `{{workspace.base_ref}}` as the original fork commit.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `scripts/validate-recap-outcome.py` | Create (Task 1) | Byte-faithful port of upstream's standalone recap Outcome Block validator. First executable in this repo. |
| `tests/test_recap_outcome_validator.py` | Create (Task 1) | Byte-faithful port of upstream's validator test suite (14 tests, subprocess-driven CLI contract). |
| `tests/test_recipe_recap_block.py` | Create (Task 2) | Bundle-specific: asserts the recipe's recap prompt declares the Outcome Block, and extracts the validator embedded in the recipe YAML and runs it against known-good/known-bad fixtures. |
| `recipes/the-usual.yaml` | Modify (Tasks 2, 3, 4) | Task 2: Outcome Block section + embedded validator in the recap step (~line 2910-3004 region). Task 3: full-suite gate steps 1-4 rewrite (~line 2549-2587 region, shifted ~+330 lines after Task 2). Task 4: header pin line, changelog entry, `version:` bump. |

No other files change. The one-shot splice script in Task 2 lives at
`/tmp/splice-outcome-block.py` and is never committed.

---

### Task 1: Port the recap-outcome validator and its test suite

**Files:**
- Create: `scripts/validate-recap-outcome.py`
- Create: `tests/test_recap_outcome_validator.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `scripts/validate-recap-outcome.py` — CLI contract `python3 scripts/validate-recap-outcome.py RECAP_PATH`; exit `0` = valid; exit `1` = invalid outcome block (stderr message prefixed `invalid outcome block: `); exit `2` = unreadable path or wrong argument count; never writes stdout. Task 2's splice script reads this file's bytes and embeds them into the recipe.

- [ ] **Step 1: Write the failing test file**

Create `tests/test_recap_outcome_validator.py` with exactly this content
(byte-faithful port of upstream `tests/test_recap_outcome_validator.py`
at `a100fac` — do not reformat, do not add a provenance header):

````python
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
        "# Recap\n\nHuman-facing content.\n\n"
        "## Outcome Block\n\n```json\n"
        + json.dumps(payload, indent=2)
        + "\n```\n"
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
        self.assert_invalid("# Recap\n\nHuman-facing content.\n", "missing terminal Outcome Block")

    def test_rejects_missing_required_field(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        del payload["head_commit_sha"]
        self.assert_invalid(recap(payload), "missing required field: head_commit_sha")

    def test_rejects_malformed_structure(self) -> None:
        document = "# Recap\n\n## Outcome Block\n\n```yaml\n{broken\n```\n"
        self.assert_invalid(document, "expected one terminal json fence")

    def test_rejects_unknown_status(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        payload["status"] = "stalled"
        self.assert_invalid(recap(payload), "status must be one of: success, non-convergence")

    def test_rejects_invalid_json(self) -> None:
        document = "# Recap\n\n## Outcome Block\n\n```json\n{broken\n```\n"
        self.assert_invalid(document, "invalid JSON")

    def test_rejects_trailing_content(self) -> None:
        self.assert_invalid(recap(VALID_PAYLOAD) + "More prose.\n", "outcome block must be terminal")

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
````

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
python3 -m unittest discover -s tests -v
```
Expected: FAIL — all 14 tests fail/error because
`scripts/validate-recap-outcome.py` does not exist (the subprocess is
`python3 <missing path> ...`, which exits 2 with "can't open file"; tests
expecting exit 0 or 1 therefore fail).

- [ ] **Step 3: Write the validator**

Create `scripts/validate-recap-outcome.py` with exactly this content
(byte-faithful port of upstream `scripts/validate-recap-outcome.py` at
`a100fac` — do not reformat, do not add a provenance header):

````python
#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


class ValidationError(ValueError):
    pass


class InputError(ValueError):
    pass


TOP_LEVEL_KEYS = {
    "schema_version",
    "status",
    "reason",
    "execution_tasks",
    "full_suite_gate",
    "review_loops",
    "head_commit_sha",
}
GATE_RESULTS = {"passed", "failed", "not-run", "blocked"}
REVIEW_VERDICTS = {"PASSED", "FAILED", "NO_MARKER", "NOT_RUN"}


def read_document(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise InputError(str(error)) from error


def extract_payload(document: str) -> object:
    headings = list(re.finditer(r"^## Outcome Block[ \t]*$", document, re.MULTILINE))
    if not headings:
        raise ValidationError("missing terminal Outcome Block")
    if len(headings) != 1:
        raise ValidationError("exactly one Outcome Block is required")

    suffix = document[headings[0].end():]
    opener = "\n\n```json\n"
    if not suffix.startswith(opener):
        raise ValidationError("expected one terminal json fence")

    terminal = re.fullmatch(
        r"\n\n```json\n(?P<body>.*?)\n```[ \t\r\n]*", suffix, re.DOTALL
    )
    if terminal is None:
        closing = re.search(r"\n```(?P<trailing>[\s\S]*)", suffix[len(opener):])
        if closing is not None and closing.group("trailing").strip():
            raise ValidationError("outcome block must be terminal")
        raise ValidationError("expected one terminal json fence")

    try:
        return json.loads(terminal.group("body"))
    except json.JSONDecodeError as error:
        raise ValidationError(f"invalid JSON in Outcome Block: {error.msg}") from error


def expect_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def expect_exact_keys(
    mapping: dict[str, object], expected: set[str], label: str = ""
) -> None:
    missing = sorted(expected - mapping.keys())
    unknown = sorted(mapping.keys() - expected)
    prefix = f"{label}." if label else ""
    if missing:
        raise ValidationError(f"missing required field: {prefix}{missing[0]}")
    if unknown:
        raise ValidationError(f"unknown field: {prefix}{unknown[0]}")


def expect_non_negative_integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise ValidationError(f"{label} must be an integer")
    if value < 0:
        raise ValidationError(f"{label} must be non-negative")
    return value


def expect_enum(value: object, allowed: set[str], message: str) -> str:
    if type(value) is not str or value not in allowed:
        raise ValidationError(message)
    return value


def validate_review(value: object, name: str, maximum: int) -> str:
    review = expect_mapping(value, f"review_loops.{name}")
    expect_exact_keys(review, {"rounds", "final_verdict"}, f"review_loops.{name}")
    rounds = expect_non_negative_integer(review["rounds"], f"{name} review rounds")
    if rounds > maximum:
        raise ValidationError(
            f"{name} review rounds must be between 0 and {maximum}"
        )
    verdict = expect_enum(
        review["final_verdict"],
        REVIEW_VERDICTS,
        "final_verdict must be one of the allowed values",
    )
    if verdict == "NOT_RUN" and rounds != 0:
        raise ValidationError("NOT_RUN requires zero rounds")
    if verdict != "NOT_RUN" and rounds == 0:
        raise ValidationError("a completed review verdict requires at least one round")
    return verdict


def validate_payload(payload: object) -> None:
    root = expect_mapping(payload, "outcome block")
    expect_exact_keys(root, TOP_LEVEL_KEYS)

    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise ValidationError("schema_version must equal 1")

    status = expect_enum(
        root["status"],
        {"success", "non-convergence"},
        "status must be one of: success, non-convergence",
    )
    reason = root["reason"]
    if status == "success" and reason is not None:
        raise ValidationError("success reason must be null")
    if status == "non-convergence" and (
        type(reason) is not str or not reason.strip()
    ):
        raise ValidationError("non-convergence requires a non-empty reason")

    tasks = expect_mapping(root["execution_tasks"], "execution_tasks")
    expect_exact_keys(tasks, {"completed", "total"}, "execution_tasks")
    completed = expect_non_negative_integer(
        tasks["completed"], "execution_tasks.completed"
    )
    total = expect_non_negative_integer(tasks["total"], "execution_tasks.total")
    if completed > total:
        raise ValidationError("completed must be <= total")

    gate = expect_mapping(root["full_suite_gate"], "full_suite_gate")
    expect_exact_keys(gate, {"result"}, "full_suite_gate")
    gate_result = expect_enum(
        gate["result"],
        GATE_RESULTS,
        "full_suite_gate.result must be one of the allowed values",
    )

    reviews = expect_mapping(root["review_loops"], "review_loops")
    expect_exact_keys(reviews, {"plan", "delta"}, "review_loops")
    plan_verdict = validate_review(reviews["plan"], "plan", 3)
    delta_verdict = validate_review(reviews["delta"], "delta", 5)

    sha = root["head_commit_sha"]
    if type(sha) is not str or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise ValidationError(
            "head_commit_sha must be 40 lowercase hex characters"
        )

    success_facts = (
        completed == total
        and gate_result == "passed"
        and plan_verdict == "PASSED"
        and delta_verdict == "PASSED"
    )
    if status == "success" and completed != total:
        raise ValidationError("success requires complete tasks")
    if status == "success" and gate_result != "passed":
        raise ValidationError("success requires a passed full-suite gate")
    if status == "success" and (
        plan_verdict != "PASSED" or delta_verdict != "PASSED"
    ):
        raise ValidationError("success requires passed reviews")
    if status == "non-convergence" and success_facts:
        raise ValidationError("non-convergence requires an unsuccessful run fact")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: validate-recap-outcome.py RECAP_PATH", file=sys.stderr)
        return 2
    try:
        document = read_document(Path(argv[0]))
        validate_payload(extract_payload(document))
    except InputError as error:
        print(f"unable to read recap: {error}", file=sys.stderr)
        return 2
    except ValidationError as error:
        print(f"invalid outcome block: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
````

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
python3 -m unittest discover -s tests -v
```
Expected: PASS — `Ran 14 tests`, `OK`.

- [ ] **Step 5: Verify the port is byte-faithful to upstream (read-only check)**

Run:
```bash
git -C /home/dan/code/skill-the-usual show a100facc784e93ef9fd8c6ef66658a95c1cdaeca:scripts/validate-recap-outcome.py | diff - scripts/validate-recap-outcome.py && echo VALIDATOR-IDENTICAL
git -C /home/dan/code/skill-the-usual show a100facc784e93ef9fd8c6ef66658a95c1cdaeca:tests/test_recap_outcome_validator.py | diff - tests/test_recap_outcome_validator.py && echo TESTS-IDENTICAL
```
Expected: no diff output; `VALIDATOR-IDENTICAL` and `TESTS-IDENTICAL`
each printed. If a diff appears, fix the local file to match upstream
exactly (upstream is authoritative for these two files) and re-run
Step 4.

- [ ] **Step 6: Commit**

```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
git add scripts/validate-recap-outcome.py tests/test_recap_outcome_validator.py
git commit -m "feat: port upstream recap-outcome validator + test suite (skill-the-usual PR #5, @ a100fac)"
```

---

### Task 2: Add the machine-readable Outcome Block to the recipe's recap step

**Files:**
- Create: `tests/test_recipe_recap_block.py`
- Modify: `recipes/the-usual.yaml` (recap step, currently ~lines 2910-3004 — locate by anchors, not line numbers)

**Interfaces:**
- Consumes: `scripts/validate-recap-outcome.py` from Task 1 (its bytes are embedded into the recipe prompt by the splice script; its CLI contract — one recap-path arg, exit 0/1/2 — is what the recap step's instructions describe).
- Produces: marker lines inside the recap step's prompt — `# --- BEGIN embedded validate-recap-outcome.py (twin: scripts/validate-recap-outcome.py in the bundle repo) ---` and `# --- END embedded validate-recap-outcome.py ---` — which `tests/test_recipe_recap_block.py` uses to extract the embedded source. Also the runtime convention that the recap is written to `{{workspace.logs_dir}}/recap.md` and validated before handoff.

Why a splice script instead of hand-editing: the 200-line validator must
land inside the recipe prompt byte-identically to `scripts/
validate-recap-outcome.py` (each non-empty line prefixed with the
prompt's 6-space YAML indent). Hand-copying 200 lines invites
transcription errors; the script embeds it mechanically and fails loudly
if any anchor is missing.

- [ ] **Step 1: Write the failing test file**

Create `tests/test_recipe_recap_block.py` with exactly this content:

````python
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
````

- [ ] **Step 2: Run the new tests to verify they fail**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
python3 -m unittest tests.test_recipe_recap_block -v
```
Expected: FAIL — `test_recap_prompt_declares_outcome_block` fails
(`'## Outcome Block' not found`) and
`test_embedded_validator_validates_fixtures` errors
(`ValueError: substring not found` from `.index`). 2 tests, 0 passing.

- [ ] **Step 3: Verify the splice anchors exist in the recipe**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
grep -c "Return the recap as your message text (plain prose, no JSON)." recipes/the-usual.yaml
grep -c "must be the recap prose" recipes/the-usual.yaml
```
Expected: `1` and `1`. If either prints `0`, read the recap step (the
final ~100 lines of the file) and adjust the corresponding anchor
constant in Step 4's script to the file's actual text (change ONLY the
OLD_* anchors, never the inserted content).

- [ ] **Step 4: Write the one-shot splice script**

Create `/tmp/splice-outcome-block.py` (NOT in the repo; never committed)
with exactly this content:

`````python
#!/usr/bin/env python3
"""One-shot splice: add the Outcome Block section to the recap step of
recipes/the-usual.yaml. Run from the worktree root. Refuses to run twice.
Exits non-zero with a message on any anchor mismatch."""
from __future__ import annotations

import sys
from pathlib import Path

RECIPE = Path("recipes/the-usual.yaml")
VALIDATOR = Path("scripts/validate-recap-outcome.py")

OLD_REMINDER = (
    "your FINAL message must be the recap prose\n"
    "      itself; end with it"
)
NEW_REMINDER = (
    "your FINAL message must be the validated recap\n"
    "      itself (prose plus its terminal Outcome Block); end with it"
)
OLD_CLOSING = (
    "      Return the recap as your message text (plain prose, no JSON).\n"
)

NEW_SECTION = '''\
      Outcome Block (mandatory, terminal; ported from upstream
      skill-the-usual PR #5, adapted to this recipe's mechanisms):

      After ALL content above -- including the warning block when one is
      required -- the recap MUST end with exactly one heading line reading
      `## Outcome Block`, then one blank line, then a single fenced json
      object, with nothing after the closing fence. This is the sole
      machine-readable exception to the rule that nothing may follow the
      failure warning. Keep the human-facing account, warning behavior,
      and next-step choices unchanged.

      Copy every value from the recorded run facts; never invent values:
      - execution_tasks: completed = {{execute_result.tasks_completed}},
        total = {{execute_result.total_tasks}}. If either template value
        is not a plain integer, take the counts from the progress ledger
        read above instead.
      - full_suite_gate.result: from the progress ledger's gate entries
        read above -- "passed" if the final gate entry PASSED at the
        final HEAD; "failed" if the last recorded gate result was a
        failure; "not-run" if no gate entry exists; "blocked" if
        execution recorded that the gate could not run.
      - review_loops.plan: rounds = the number of iteration entries in
        {{workspace.logs_dir}}/fresheyes-plan.md (0-3). final_verdict =
        "PASSED" if plan_passed is 'true'; else "FAILED" if the final
        iteration recorded a failing verdict; else "NO_MARKER" if the
        final iteration recorded no verdict at all; "NOT_RUN" (with
        rounds 0) only if the log is missing or has no iteration
        entries.
      - review_loops.delta: same mapping, from
        {{workspace.logs_dir}}/fresheyes-delta.md and delta_passed
        (rounds 0-5).
      - head_commit_sha: the full 40-character lowercase SHA from
        `git -C {{workspace.worktree_path}} rev-parse HEAD`.
      - status and reason are DERIVED, not chosen: status is "success"
        only when completed equals total AND the gate result is "passed"
        AND both final verdicts are "PASSED"; then reason is null.
        Otherwise status is "non-convergence" and reason is one
        non-empty sentence naming the unsuccessful fact(s): partial
        tasks, a failed/not-run/blocked gate, a failed review, or a
        blocked run.

      Use this exact schema, changing only its values:

      ```json
      {
        "schema_version": 1,
        "status": "success",
        "reason": null,
        "execution_tasks": {
          "completed": 2,
          "total": 2
        },
        "full_suite_gate": {
          "result": "passed"
        },
        "review_loops": {
          "plan": {
            "rounds": 1,
            "final_verdict": "PASSED"
          },
          "delta": {
            "rounds": 1,
            "final_verdict": "PASSED"
          }
        },
        "head_commit_sha": "0123456789abcdef0123456789abcdef01234567"
      }
      ```

      Validation (required before handoff):
      1. Write the COMPLETE recap -- prose, any warning block, and the
         terminal Outcome Block -- to {{workspace.logs_dir}}/recap.md.
      2. Write the embedded validator to
         {{workspace.logs_dir}}/validate-recap-outcome.py: every line
         between the BEGIN and END marker lines below, exactly as given,
         nothing else. Confirm the copy compiles:
         `python3 -m py_compile {{workspace.logs_dir}}/validate-recap-outcome.py`
      3. Run:
         `python3 {{workspace.logs_dir}}/validate-recap-outcome.py {{workspace.logs_dir}}/recap.md`
         Exit 0 means valid. Treat any non-zero exit as a failed recap
         step: correct the block from the recorded facts (never bend the
         facts to silence the validator), rewrite recap.md, and rerun
         until it exits 0. If python3 itself is unavailable in this
         environment, skip validation and say so in one line placed
         BEFORE the Outcome Block heading (never after the fence).

      ```python
      # --- BEGIN embedded validate-recap-outcome.py (twin: scripts/validate-recap-outcome.py in the bundle repo) ---
@VALIDATOR@
      # --- END embedded validate-recap-outcome.py ---
      ```

      Return the recap as your message text: the exact validated content
      of recap.md -- prose first, the warning block when required, and
      the single terminal Outcome Block json fence as the final content.
'''


def main() -> int:
    text = RECIPE.read_text(encoding="utf-8")
    if "BEGIN embedded validate-recap-outcome.py" in text:
        print("already spliced; nothing to do", file=sys.stderr)
        return 1
    for name, needle in (("reminder", OLD_REMINDER), ("closing", OLD_CLOSING)):
        count = text.count(needle)
        if count != 1:
            print(
                f"anchor {name!r} found {count} times, expected 1",
                file=sys.stderr,
            )
            return 3
    validator_lines = VALIDATOR.read_text(encoding="utf-8").split("\n")
    if validator_lines and validator_lines[-1] == "":
        validator_lines.pop()
    indented = "\n".join(
        ("      " + line) if line.strip() else "" for line in validator_lines
    )
    section = NEW_SECTION.replace("@VALIDATOR@", indented, 1)
    new_text = text.replace(OLD_REMINDER, NEW_REMINDER, 1)
    new_text = new_text.replace(OLD_CLOSING, section, 1)
    RECIPE.write_text(new_text, encoding="utf-8")
    added = len(section.split("\n")) - 1
    print(f"spliced Outcome Block section into {RECIPE} (+{added} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
`````

- [ ] **Step 5: Run the splice**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
python3 /tmp/splice-outcome-block.py
```
Expected: `spliced Outcome Block section into recipes/the-usual.yaml
(+3xx lines)` and exit 0. On exit 3, go back to Step 3's anchor
adjustment. Running it a second time must print `already spliced;
nothing to do` and exit 1 (do not run it twice for real).

- [ ] **Step 6: Verify — YAML parses, all tests pass**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
python3 -c "import yaml; d=yaml.safe_load(open('recipes/the-usual.yaml', encoding='utf-8')); print(d['version'], len(d['steps']))"
python3 -m unittest discover -s tests -v
```
Expected: `3.8.0 12`, then `Ran 16 tests`, `OK`.

- [ ] **Step 7: Sanity-inspect the spliced region and clean up**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
git diff --stat
grep -n "BEGIN embedded validate-recap-outcome" recipes/the-usual.yaml
grep -n "Return the recap as your message text" recipes/the-usual.yaml
rm /tmp/splice-outcome-block.py
```
Expected: diff stat shows ONLY `recipes/the-usual.yaml` modified (plus
the untracked new test file); one BEGIN match near the end of the file;
exactly one "Return the recap as your message text" match (the new
closing line). Read ~40 lines around the BEGIN match and confirm the
section sits between the review-failure warning instructions and the
closing "Return the recap" line, all indented 6 spaces.

- [ ] **Step 8: Commit**

```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
git add recipes/the-usual.yaml tests/test_recipe_recap_block.py
git commit -m "feat: recap Outcome Block -- machine-readable terminal JSON, validated before handoff"
```

---

### Task 3: Port the full-suite gate hardening semantics into the execute-plan step

**Files:**
- Modify: `recipes/the-usual.yaml` (the `## Full-suite gate` section inside the execute-plan step's prompt; before Task 2 it sat at lines 2549-2587 — after Task 2 it will have shifted; locate by anchor, not line number)

**Interfaces:**
- Consumes: nothing from Tasks 1-2 (independent prose edit in a different region of the same file).
- Produces: the hardened gate procedure text (steps 1-5) that Task 4's changelog entry describes. The phrases `current logical invocation` (on a single line in steps 2 and 4; the step-1 occurrence wraps across lines), `scope the runner did not reach`, and `documented reusable state` must appear exactly as written below (Task 3 Step 3 greps for them).

Translation rules applied (from the task spec): the bundle's progress
ledger lives at `$(git rev-parse --git-path sdd)/progress.md` inside the
target worktree (NOT `usual-sdd/`); the pre-existing-failure definition
keeps the bundle's existing `{{workspace.base_ref}}` reproduction receipt
and OMITS upstream's baseline-ledger reference clause (no baseline ledger
exists in a bundle run); `run-state.md` is not referenced anywhere.

- [ ] **Step 1: Locate and confirm the current gate procedure text**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
grep -n "1. Run the repository's full test suite." recipes/the-usual.yaml
```
Expected: exactly one match (around line 2553 + Task 2's shift). Read
the ~45 lines starting there and confirm they match the OLD text below
(modulo `--` vs `—` dash characters — if the file differs only in dashes
or similar punctuation, use the file's exact characters in the
old-string of Step 2's edit; the file is truth).

- [ ] **Step 2: Replace gate procedure steps 1-4**

In `recipes/the-usual.yaml`, replace this exact text (steps 1-4 of "The
gate procedure (run inside the worktree):" — step 5 "Record the gate
entry..." stays untouched):

OLD (to be replaced):

```
      1. Run the repository's full test suite.
      2. Record every failure in the progress ledger as a bug: the failing
         test, the command, and the observed output. A failure counts as a
         LEDGER-RECORDED PRE-EXISTING FAILURE only if it also reproduces at
         the original fork commit {{workspace.base_ref}} -- the code this
         branch started from, without this branch's changes -- with that
         reproduction receipt recorded in the ledger.
      3. If there are failures that are not ledger-recorded pre-existing
         failures, dispatch ONE fix subagent with the complete failure list
         (same batching rule as final-review fixes; the fixer verifies each
         fix with its covering tests and commits). Do not fix ledger-recorded
         pre-existing failures unless they block the feature's verification;
         leave them recorded for the recap instead.
      4. Rerun the full suite. Repeat record-fix-rerun until the suite is
         green excluding ledger-recorded pre-existing failures. The gate
         passes at that point, and only at that point.
```

NEW (replacement):

```
      1. Identify the repository's exact full-suite command. Before
         launching it, inspect the progress ledger and this run's recorded
         artifacts for an invocation on the same committed HEAD with that
         exact command. Adopt a valid passing result as the current logical
         invocation. Treat a matching stopped invocation with valid output
         likewise, whether the process completed normally or was
         interrupted by infrastructure; await or resume a matching running
         invocation. Clean up an unusable prior invocation through the
         repository's documented path before replacing it. When no usable
         matching invocation exists, record the committed HEAD, the exact
         command, and the log or session location in the progress ledger,
         then launch the suite inside the worktree.
      2. If the current logical invocation is active, let it terminate
         before repairing assertion failures; the runner's native
         continuation counts as part of the same invocation when later
         results remain trustworthy. Process its output. Record every
         failure in the progress ledger as a bug: the failing test, the
         command, and the observed output. Also record every configured
         scope the runner did not reach. A failure counts as a
         LEDGER-RECORDED PRE-EXISTING FAILURE only if it also reproduces at
         the original fork commit {{workspace.base_ref}} -- the code this
         branch started from, without this branch's changes -- with that
         reproduction receipt recorded in the ledger. Return services,
         queues, and other resources started by the repository to the
         repository's documented reusable state before another interacting
         run.
      3. If there are failures that are not ledger-recorded pre-existing
         failures, dispatch ONE fix subagent with the complete failure
         list, addressing shared causes first (same batching rule as
         final-review fixes; the fixer verifies each fix with its covering
         tests and commits). That focused verification and those commits
         complete before another full-suite invocation. Do not fix
         ledger-recorded pre-existing failures unless they block the
         feature's verification; leave them recorded for the recap instead.
      4. If the current logical invocation is green excluding
         ledger-recorded pre-existing failures, proceed directly to step 5.
         Otherwise, only after the complete remediation pass or a concrete
         infrastructure recovery, return to step 1 with the resulting
         committed HEAD before launching another full invocation. Repeat
         the inventory-remediation-rerun cycle until the suite is green
         excluding ledger-recorded pre-existing failures. The gate passes
         at that point, and only at that point.
```

Apply with a single `edit_file` (old_string = the OLD block exactly as it
appears in the file, new_string = the NEW block above verbatim). Both
blocks keep the recipe prompt's 6-space base indent with 9-space
continuation lines, as shown.

- [ ] **Step 3: Verify — YAML parses, hardened phrases present, tests still pass**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
python3 -c "import yaml; d=yaml.safe_load(open('recipes/the-usual.yaml', encoding='utf-8')); print(d['version'], len(d['steps']))"
grep -c "current logical invocation" recipes/the-usual.yaml
grep -c "scope the runner did not reach" recipes/the-usual.yaml
grep -c "documented reusable state" recipes/the-usual.yaml
grep -c "Run the repository's full test suite." recipes/the-usual.yaml
python3 -m unittest discover -s tests -v
```
Expected: `3.8.0 12`; then `2`, `1`, `1`, `0`; then `Ran 16 tests`, `OK`.
(`current logical invocation` counts 2 because grep counts lines: the
step-1 occurrence wraps across a line break; steps 2 and 4 each match.)

- [ ] **Step 4: Confirm surrounding gate machinery is untouched**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
grep -c "5. Record the gate entry in the progress ledger" recipes/the-usual.yaml
grep -c "PERIODICALLY, on long runs" recipes/the-usual.yaml
grep -c "AT THE END OF EXECUTION" recipes/the-usual.yaml
git diff --stat
```
Expected: `1`, `1`, `1`; diff stat shows only `recipes/the-usual.yaml`.
(The "When the gate runs" triggers and step 5 recording are deliberately
unchanged — upstream did not change the periodic trigger in this range.)

- [ ] **Step 5: Commit**

```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
git add recipes/the-usual.yaml
git commit -m "feat: harden full-suite gate with invocation adoption/resume/cleanup semantics (upstream 43c7033..9f04cd7)"
```

---

### Task 4: Formal upstream pin, changelog entry, version bump

**Files:**
- Modify: `recipes/the-usual.yaml` (header comment block ~lines 1-36; changelog top ~line 37; `version:` field ~line 314 + shifts from Tasks 2-3)

**Interfaces:**
- Consumes: the landed Tasks 1-3 (the changelog entry below describes them; do not write this entry unless Tasks 1-3 are committed).
- Produces: the formal pin line `# upstream: skill-the-usual @ a100facc784e93ef9fd8c6ef66658a95c1cdaeca`, the `v3.9.0-draft` changelog entry, and `version: "3.9.0"`.

- [ ] **Step 1: Insert the pin block in the header**

In `recipes/the-usual.yaml`, replace this exact text (the end of the
"canonical home" paragraph near the top of the file, ~line 13):

OLD:
```
# files -> inline bash). EDITS TO THE WORKFLOW SHOULD BE MADE HERE.
#
# Two skills are still loaded by name at runtime because the author's copies
```

NEW:
```
# files -> inline bash). EDITS TO THE WORKFLOW SHOULD BE MADE HERE.
#
# upstream: skill-the-usual @ a100facc784e93ef9fd8c6ef66658a95c1cdaeca
#   (formal pin of the sibling skill repo this recipe was ported from;
#   range d447273..a100fac reviewed and selectively adopted 2026-08-10 --
#   see changelog v3.9.0-draft. Ports are deliberate translations to this
#   recipe's mechanisms, never byte-syncs.)
#
# Two skills are still loaded by name at runtime because the author's copies
```

If the OLD anchor does not match exactly (dash characters), read lines
1-20 of the file and match its characters; insert the same NEW pin lines.

- [ ] **Step 2: Insert the changelog entry at the top of the changelog**

In `recipes/the-usual.yaml`, replace this exact text (the first line of
the first existing changelog entry heading, ~line 37 — it is unique in
the file; verify first with
`grep -c "v3.8.0-draft (2026-08-09)" recipes/the-usual.yaml` → `1`):

OLD:
```
# v3.8.0-draft (2026-08-09) [DRAFT
```

NEW:
```
# v3.9.0-draft (2026-08-10) [DRAFT -- version field reads 3.9.0 because the
#   recipe engine rejects pre-release tags; treat as draft until merged]:
#   - UPSTREAM PORT (deliberate-port pattern per v3.5.0/v3.6.0; the full
#     upstream range d447273..a100fac of skill-the-usual was reviewed on
#     2026-08-10 and the portable improvements adopted):
#     * NEW (upstream PR #5): machine-readable Outcome Block in the recap
#       step. Every recap now ends with exactly one `## Outcome Block`
#       heading plus one terminal json fence (schema_version 1: status,
#       reason, execution_tasks, full_suite_gate, review_loops,
#       head_commit_sha; success requires complete tasks + passed gate +
#       both reviews PASSED). The recap is written to logs_dir/recap.md
#       and validated before handoff by an embedded copy of upstream's
#       stdlib-only validate-recap-outcome.py (non-zero exit = failed
#       recap; sole exception to "nothing follows the warning block").
#       Field sources are this recipe's own mechanisms -- execute_result
#       counts, fresheyes logs, progress-ledger gate entries -- NOT
#       upstream's run-state.md, which is not adopted.
#     * NEW: scripts/validate-recap-outcome.py and tests/ -- byte-faithful
#       port of the upstream validator and its unittest suite (the repo's
#       first executable + tests), plus tests/test_recipe_recap_block.py,
#       which extracts the embedded twin from this YAML and runs it
#       against known-good/known-bad fixtures.
#     * CHANGED (gate hardening; upstream commits 43c7033..9f04cd7 as
#       prose): full-suite gate steps 1-4 rewritten around a "current
#       logical invocation": identify the exact command, then
#       adopt/await/resume a matching prior invocation at the same
#       committed HEAD before launching (stopped invocations with valid
#       output count; unusable prior invocations are cleaned up first;
#       every launch is recorded in the ledger beforehand); let active
#       invocations terminate before repairing; also record configured
#       scopes the runner did not reach; return services/queues to their
#       documented reusable state; fail-closed loop back through step 1
#       at the new committed HEAD. Translated to this recipe's mechanisms
#       (progress ledger in `git rev-parse --git-path sdd`, base_ref
#       reproduction receipts); upstream's baseline-ledger reference
#       clause is omitted -- no baseline ledger exists in a bundle run.
#     * NOT DONE (deliberate, out of scope): run-state.md and
#       baseline-ledger machinery; Fresh Eyes harness/transport split and
#       the rewritten reviewer-prompt.md (this recipe deliberately
#       reviews via delegate()); CI drift tripwires; vendoring or
#       byte-equality sync; touchpoint fixtures; review-endpoints
#       rewording (this recipe's dispatch templates already state exact
#       endpoints).
#   - NEW: formal upstream pin in the header block above (`upstream:
#     skill-the-usual @ a100fac...`), replacing informal changelog-only
#     provenance.
#
# v3.8.0-draft (2026-08-09) [DRAFT
```

(The `[DRAFT` truncation in the anchor is deliberate — the v3.8.0-draft
heading wraps across two lines; anchoring on its first line is enough
and avoids dash-character ambiguity in the continuation line. Verify
first: `grep -n "v3.8.0-draft (2026-08-09)" recipes/the-usual.yaml`
must print exactly one match before the edit, on the line directly
after the `#` spacer under the CHANGELOG banner.)

- [ ] **Step 3: Bump the version field**

In `recipes/the-usual.yaml`, replace:

OLD:
```
version: "3.8.0"
```

NEW:
```
version: "3.9.0"
```

(`grep -c 'version: "3.8.0"' recipes/the-usual.yaml` must print `1`
before the edit — the string appears only in the metadata block.)

- [ ] **Step 4: Verify — YAML parses at 3.9.0, pin present, tests pass**

Run:
```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
python3 -c "import yaml; d=yaml.safe_load(open('recipes/the-usual.yaml', encoding='utf-8')); print(d['version'], len(d['steps']))"
grep -n "upstream: skill-the-usual @ a100facc784e93ef9fd8c6ef66658a95c1cdaeca" recipes/the-usual.yaml
grep -n "v3.9.0-draft (2026-08-10)" recipes/the-usual.yaml
python3 -m unittest discover -s tests -v
```
Expected: `3.9.0 12`; the pin grep matches once in the header (line
< 25); the changelog grep matches once (~line 37-40); `Ran 16 tests`,
`OK`.

- [ ] **Step 5: Commit**

```bash
cd /home/dan/code/bundle-the-usual/.worktrees/upstream-port-and-pin
git add recipes/the-usual.yaml
git commit -m "feat: pin upstream skill-the-usual @ a100fac; changelog + version bump (v3.9.0-draft)"
```

---

## Verification notes for reviewers

- The strongest available static claims are: the YAML parses (12 steps,
  correct version), the 16 tests pass, and the two ported files are
  byte-identical to upstream `a100fac` (Task 1 Step 5). The recap step's
  runtime behavior is exercised by `tests/test_recipe_recap_block.py`,
  which runs the ACTUAL validator source embedded in the recipe prompt
  against known-good and known-bad recap fixtures — no mocks or stubs
  stand in for the production path. A full end-to-end recipe run is
  hours-long and outside this plan's tasks; the embedded-twin test is
  the production-fidelity evidence for the splice.
- Deliberate scope decisions (not gaps): upstream's review-endpoints
  rewording (PR-range candidate) was evaluated and dropped — this
  recipe's reviewer dispatch templates already state exact endpoints
  (`BASE = the commit recorded before the implementer was dispatched`,
  final review over the branch delta), so the wording adds nothing; the
  two separable gate one-liners (unreached scopes, resource hygiene) ARE
  included, inside Task 3's step 2 text. `bundle.md` and
  `behaviors/the-usual.yaml` version fields stay at 3.7.0 per the
  repo's own draft-release precedent. README.md is untouched (strict
  "port + pin, nothing else" scope).
