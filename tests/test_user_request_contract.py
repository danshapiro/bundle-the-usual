"""Contract tests for the revision-free User Request flow (v3.13.1)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = ROOT / "recipes" / "the-usual.yaml"
INSTRUCTIONS_PATH = ROOT / "context" / "the-usual-instructions.md"
README_PATH = ROOT / "README.md"
BUNDLE_PATH = ROOT / "bundle.md"
BEHAVIOR_PATH = ROOT / "behaviors" / "the-usual.yaml"
STEP_RUNNER_PATH = ROOT / "agents" / "step-runner.md"
VALIDATOR_PATH = ROOT / "scripts" / "validate-recap-outcome.py"

RECIPE = RECIPE_PATH.read_text(encoding="utf-8")
INSTRUCTIONS = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
README = README_PATH.read_text(encoding="utf-8")
BUNDLE = BUNDLE_PATH.read_text(encoding="utf-8")
BEHAVIOR = BEHAVIOR_PATH.read_text(encoding="utf-8")

USER_REQUEST_HEADINGS = (
    "## User Request",
    "### Requested result",
    "### Explicit constraints",
    "### Accepted tradeoffs and residuals",
)

APPROVED_SCOPE = (
    "Use the current User Request as the definition of need. Choose the simplest "
    "complete plan or remedy that delivers its requested result and explicit "
    "constraints. Every substantiated finding about the chosen solution must be "
    "cleared, but it may be cleared by fixing, replacing, simplifying, or removing "
    "work introduced or materially expanded by the current plan. When that new "
    "machinery is not necessary to satisfy the User Request, omit or simplify it "
    "rather than expanding or hardening it. Preserve pre-existing code and behavior "
    "unless changing them is necessary to satisfy the User Request or clear a "
    "substantiated blocker to it."
)


def norm(text: str) -> str:
    """Collapse formatting differences while retaining contract wording."""
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).strip()


def step_section(step_id: str) -> str:
    """Return one top-level recipe step."""
    start = RECIPE.index(f'  - id: "{step_id}"')
    nxt = RECIPE.find("\n  - id: ", start + 1)
    return RECIPE[start:] if nxt == -1 else RECIPE[start:nxt]


def version_of(text: str) -> str:
    match = re.search(
        r'^\s*version:\s*"?(\d+\.\d+\.\d+)"?\s*$',
        text,
        re.MULTILINE,
    )
    assert match is not None
    return match.group(1)


def embedded_bash_after(marker: str) -> str:
    """Extract the actual fenced bash program embedded after a recipe marker."""
    marker_start = RECIPE.index(marker)
    opener = "      ```bash\n"
    script_start = RECIPE.index(opener, marker_start) + len(opener)
    script_end = RECIPE.index("\n      ```", script_start)
    return textwrap.dedent(RECIPE[script_start:script_end]) + "\n"


def top_level_steps() -> list[tuple[str, str]]:
    matches = list(re.finditer(r'(?m)^  - id: "([^"]+)"', RECIPE))
    return [
        (
            match.group(1),
            RECIPE[
                match.start() : matches[index + 1].start()
                if index + 1 < len(matches)
                else len(RECIPE)
            ],
        )
        for index, match in enumerate(matches)
    ]


def step_field(section: str, name: str) -> str | None:
    match = re.search(
        rf'(?m)^    {re.escape(name)}:\s*(?:"([^"]*)"|([^#\n]+))',
        section,
    )
    if match is None:
        return None
    return (match.group(1) if match.group(1) is not None else match.group(2)).strip()


def step_command(section: str) -> str:
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


def step_env_bindings(section: str) -> dict[str, str]:
    """Return pure template-to-environment bindings from one bash step."""
    marker = re.search(r"(?m)^    env:\s*$", section)
    if marker is None:
        return {}
    bindings = {}
    for line in section[marker.end() :].splitlines():
        if not line:
            continue
        match = re.fullmatch(
            r'\s{6}([A-Za-z_][A-Za-z0-9_]*):\s*["\']?\{\{([^}]+)\}\}["\']?\s*',
            line,
        )
        if match is None:
            if line.startswith("      "):
                continue
            break
        bindings[match.group(1)] = match.group(2)
    return bindings


def render_bash_step(
    section: str, values: dict[str, str]
) -> tuple[str, dict[str, str]]:
    """Model recipe interpolation for command text and supported env mappings."""
    command = step_command(section)
    environment = os.environ.copy()
    for binding in set(re.findall(r"\{\{([^}]+)\}\}", command)):
        command = command.replace(f"{{{{{binding}}}}}", values[binding])
    for variable, binding in step_env_bindings(section).items():
        environment[variable] = values[binding]
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return command, environment


def condition_allows(section: str, values: dict[str, object]) -> bool:
    condition = step_field(section, "condition")
    if condition is None:
        return True
    match = re.fullmatch(r"\{\{([^}]+)\}\}\s*(==|!=)\s*'([^']*)'", condition)
    if match is None:
        raise ValueError(f"unsupported recipe condition: {condition}")
    value: object = values
    for part in match.group(1).split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(match.group(1))
        value = value[part]
    actual = str(value).lower() if isinstance(value, bool) else str(value)
    return (actual == match.group(3)) == (match.group(2) == "==")


TASK_BRIEF_SCRIPT = embedded_bash_after(
    "TASK BRIEF — extract the complete current User Request"
)


class TestParentDispatcherContract(unittest.TestCase):
    """The interactive parent owns extraction, sanitization, and later judgment."""

    def test_exact_revision_free_block(self):
        positions = [INSTRUCTIONS.index(heading) for heading in USER_REQUEST_HEADINGS]
        self.assertEqual(positions, sorted(positions))
        for heading in USER_REQUEST_HEADINGS:
            self.assertEqual(INSTRUCTIONS.count(heading), 1, heading)
        for forbidden_heading in (
            "### Revision",
            "### Timestamp",
            "### History",
            "### Amendment",
        ):
            self.assertNotIn(forbidden_heading, INSTRUCTIONS)

    def test_parent_extracts_current_request_from_full_conversation(self):
        text = norm(INSTRUCTIONS).lower()
        for required in (
            "full conversation",
            "bare workflow activation",
            "later explicit direction",
            "supersedes",
            "adds",
            "withdraws",
            "active obligations",
            "accepted tradeoffs",
        ):
            self.assertIn(required, text)

    def test_parent_sanitizes_values_but_keeps_safe_behavior(self):
        text = norm(INSTRUCTIONS).lower()
        for secret_kind in (
            "literal credentials",
            "private keys",
            "authorization headers",
            "token values",
            "secret values",
            "sensitive payloads",
        ):
            self.assertIn(secret_kind, text)
        self.assertIn("safe behavior", text)
        self.assertIn("references", text)
        self.assertIn("never log", text)

    def test_invocation_separates_provenance_current_request_and_repo(self):
        self.assertRegex(INSTRUCTIONS, r'"task":\s*"<[^"]+>"')
        self.assertRegex(INSTRUCTIONS, r'"user_request":\s*"<[^"]+>"')
        self.assertRegex(INSTRUCTIONS, r'"repo_path":\s*"<[^"]+>"')
        self.assertIn("task never overrides", norm(INSTRUCTIONS).lower())

    def test_parent_handles_later_direction_by_judgment(self):
        text = norm(INSTRUCTIONS).lower()
        for required in (
            "update the current user request block",
            "relevant plan",
            "assess practical impact",
            "notify",
            "redirect",
            "cancel",
            "replace",
            "restart",
            "reuse",
            "disregard stale results",
            "leave agents or work alone",
            "affected work",
            "preserve unaffected valid work",
        ):
            self.assertIn(required, text)

    def test_blocking_and_resume_limits_are_explicit(self):
        combined = norm(f"{INSTRUCTIONS}\n{README}").lower()
        self.assertIn(
            "after the blocking recipe call returns or is interrupted", combined
        )
        self.assertIn("unchanged interruption", combined)
        self.assertIn('operation="resume"', combined)
        self.assertIn("rather than an automatic changed-intent continuation", combined)


class TestPublicDirectInvocationContract(unittest.TestCase):
    """README documents direct callers without pretending they have conversation context."""

    def test_optional_user_request_and_conservative_fallback(self):
        text = norm(README).lower()
        for required in (
            "optional",
            "user_request",
            "self-contained",
            "sanitized task",
            "specification",
            "fails honestly",
            "referential",
        ):
            self.assertIn(required, text)

    def test_direct_caller_owns_pre_invocation_sanitization(self):
        text = norm(README).lower()
        self.assertIn("direct caller", text)
        self.assertIn("before invocation", text)
        self.assertIn("sanit", text)

    def test_public_docs_explain_revision_free_current_snapshot(self):
        text = norm(README).lower()
        self.assertIn("current snapshot", text)
        self.assertIn("no revision", text)
        self.assertIn("git history", text)
        self.assertIn("changed direction", text)
        self.assertIn("parent", text)


class TestRecipeInputAndPlanContract(unittest.TestCase):
    """The recipe accepts the current snapshot and makes the plan its carrier."""

    def test_recipe_declares_optional_user_request(self):
        self.assertRegex(RECIPE, r'(?m)^\s{2}user_request:\s*""')
        context = RECIPE[RECIPE.index("context:") : RECIPE.index("steps:")]
        self.assertIn("optional", context.lower())

    def test_recipe_fallback_is_conservative_and_honest(self):
        text = norm(RECIPE).lower()
        for required in (
            "self-contained sanitized task",
            "specification fallback",
            "referential",
            "fails honestly",
            "direct caller",
            "pre-invocation sanitization",
        ):
            self.assertIn(required, text)

    def test_task_is_provenance_and_never_overrides_current_request(self):
        text = norm(RECIPE).lower()
        self.assertIn("sanitized task provenance", text)
        self.assertIn("task never overrides", text)

    def test_plan_inserts_block_unchanged_once_before_goal(self):
        plan = norm(step_section("write-plan"))
        self.assertIn(
            "insert the supplied user request block unchanged exactly once",
            plan.lower(),
        )
        self.assertIn("immediately before the planner-owned ## Goal", plan)

    def test_plan_has_no_request_revision_metadata(self):
        lowered = RECIPE.lower()
        for forbidden in (
            "user_request_revision",
            "request_revision",
            "request_timestamp",
            "amendment_log",
            "amendment history",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_plan_is_the_sole_durable_carrier(self):
        self.assertIn("plan is the sole durable carrier", norm(RECIPE).lower())
        artifact_names = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            relative = path.relative_to(ROOT)
            if relative == Path("tests/test_user_request_contract.py"):
                continue
            lowered = relative.as_posix().lower()
            if "user-request" in lowered or "user_request" in lowered:
                artifact_names.append(lowered)
        self.assertEqual([], artifact_names, "new User Request artifact found")


class TestCompleteDelegateContext(unittest.TestCase):
    """Every semantic delegate receives the complete current plan block verbatim."""

    def test_planning_and_load_bearing_delegates(self):
        write_plan = norm(step_section("write-plan")).lower()
        self.assertIn(
            "planning explorers receive the complete current user request block verbatim",
            write_plan,
        )

        load_bearing = norm(step_section("load-bearing")).lower()
        for role in ("finder", "strategist", "validators"):
            self.assertIn(
                f"{role} receive the complete current user request block verbatim",
                load_bearing,
            )

    def test_plan_review_and_remediation_delegates(self):
        section = norm(step_section("fresheyes-plan")).lower()
        for role in ("reviewer", "remediation"):
            self.assertIn(
                f"{role} receives the complete current user request block verbatim",
                section,
            )

    def test_execution_delegates(self):
        section = norm(step_section("execute-plan")).lower()
        for role in (
            "execution preflight",
            "task briefs",
            "implementers",
            "fixers",
            "task reviewers",
            "full-suite fixer",
            "whole-branch reviewer",
            "whole-branch fixer",
        ):
            self.assertIn(
                f"{role} receive the complete current user request block verbatim",
                section,
            )

    def test_delta_review_and_recap_receive_complete_block(self):
        delta = norm(step_section("fresheyes-delta")).lower()
        for role in ("reviewer", "remediation"):
            self.assertIn(
                f"{role} receives the complete current user request block verbatim",
                delta,
            )
        self.assertIn(
            "recap receives the complete current user request block verbatim",
            norm(step_section("recap")).lower(),
        )

    def test_task_brief_order(self):
        section = norm(step_section("execute-plan"))
        markers = (
            "Task brief order: ## User Request",
            "then ## Global Constraints",
            "then the selected ## Task",
        )
        for marker in markers:
            self.assertIn(marker, section)
        user_request = section.index(markers[0])
        constraints = section.index(markers[1], user_request)
        task = section.index(markers[2], constraints)
        self.assertLess(user_request, constraints)
        self.assertLess(constraints, task)


class TestScopeAndFindingAuthority(unittest.TestCase):
    """Scope remains user-defined while every substantiated finding remains binding."""

    def test_exact_scope_paragraph_at_authority_seams(self):
        approved = norm(APPROVED_SCOPE)
        for step_id in (
            "write-plan",
            "load-bearing",
            "fresheyes-plan",
            "execute-plan",
            "fresheyes-delta",
        ):
            self.assertIn(approved, norm(step_section(step_id)), step_id)

    def test_kiss_and_yagni_authority_sentences(self):
        text = norm(RECIPE)
        self.assertIn("KISS governs how", text)
        self.assertIn("YAGNI limits new work", text)

    def test_findings_bind_and_remedies_only_advise(self):
        text = norm(RECIPE).lower()
        for required in (
            "findings bind",
            "reviewer remedies advise",
            "every severity",
            "durably recorded",
            "assessed",
            "carried until explicit clearance",
            "passed cannot erase prior unresolved findings",
            "minor",
            "nit",
            "may clear locally",
            "caps remain bounded",
        ):
            self.assertIn(required, text)

    def test_unresolved_findings_prevent_success(self):
        text = norm(RECIPE).lower()
        for required in (
            "unresolved",
            "failed",
            "non-converged",
            "no success",
            "no merge",
        ):
            self.assertIn(required, text)


class TestRejectedMechanismsStayAbsent(unittest.TestCase):
    """The port stays judgment-based rather than growing continuation machinery."""

    def test_rejected_runtime_contracts_are_absent(self):
        runtime = f"{RECIPE}\n{INSTRUCTIONS}\n{README}\n{BUNDLE}\n{BEHAVIOR}".lower()
        for forbidden in (
            "continuation_manifest",
            "continuation manifest",
            "request_hash",
            "request hash",
            "request ownership",
            "continuation ownership",
            "request ancestry",
            "transaction journal",
            "amendment journal",
            "changed-intent resume protocol",
            "earliest affected task",
            "fixed restart algorithm",
            "fixed invalidation algorithm",
        ):
            self.assertNotIn(forbidden, runtime)

    def test_no_standalone_source_runtime_reference(self):
        runtime = f"{RECIPE}\n{INSTRUCTIONS}\n{README}\n{BUNDLE}\n{BEHAVIOR}".lower()
        self.assertNotRegex(runtime, r"(?:^|[/\\])skill-the-usual\b")
        self.assertNotIn("standalone canonical prompt", runtime)

    def test_step_runner_matches_current_head(self):
        expected = subprocess.run(
            ["git", "-C", str(ROOT), "show", "HEAD:agents/step-runner.md"],
            check=True,
            capture_output=True,
        ).stdout
        actual = STEP_RUNNER_PATH.read_bytes()
        self.assertEqual(
            hashlib.sha256(expected).digest(), hashlib.sha256(actual).digest()
        )


class TestExecutableRecipeRegressions(unittest.TestCase):
    """Execute embedded shell paths whose behavior cannot be protected by prose."""

    @staticmethod
    def run_task_brief(
        plan_text: str, task_number: int
    ) -> tuple[subprocess.CompletedProcess[str], bytes | None]:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            plan_path = repo / "plan.md"
            plan_path.write_bytes(plan_text.encode())
            subprocess.run(
                ["git", "add", "plan.md"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Contract Test",
                    "-c",
                    "user.email=contract@example.invalid",
                    "commit",
                    "-qm",
                    "add realistic plan",
                ],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            environment = os.environ.copy()
            environment.update(
                PLAN=str(plan_path),
                N=str(task_number),
                PYTHONDONTWRITEBYTECODE="1",
            )
            result = subprocess.run(
                ["bash", "-c", TASK_BRIEF_SCRIPT],
                cwd=repo,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            brief_path = repo / ".git" / "sdd" / f"task-{task_number}-brief.md"
            brief = brief_path.read_bytes() if brief_path.is_file() else None
            return result, brief

    @staticmethod
    def run_validator(payload: object) -> subprocess.CompletedProcess[str]:
        document = (
            "# Recap\n\nPlan review did not converge. No success or merge "
            "recommendation.\n\n## Outcome Block\n\n```json\n"
            f"{json.dumps(payload, indent=2)}\n```\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            recap_path = Path(directory) / "recap.md"
            recap_path.write_text(document, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR_PATH), str(recap_path)],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

    @staticmethod
    def run_execute_result_bash(
        plan_passed: str,
    ) -> tuple[dict[str, object] | None, list[str]]:
        values: dict[str, object] = {
            "plan_passed": plan_passed,
            "delta_passed": "false",
        }
        steps = top_level_steps()
        start = next(
            index for index, step in enumerate(steps) if step[0] == "execute-plan"
        )
        end = next(index for index, step in enumerate(steps) if step[0] == "recap")
        problems = []
        result_data: dict[str, object] | None = None
        with tempfile.TemporaryDirectory() as directory:
            logs_dir = Path(directory) / "logs"
            logs_dir.mkdir()
            for step_id, section in steps[start:end]:
                try:
                    enabled = condition_allows(section, values)
                except (KeyError, ValueError) as error:
                    problems.append(f"{step_id} condition is undefined: {error}")
                    continue
                if not enabled or step_field(section, "output") != "execute_result":
                    continue
                if step_field(section, "type") != "bash":
                    # A successful execute-plan would normally supply this output.
                    # This probe deliberately models that output being lost.
                    continue
                command = step_command(section).replace(
                    "{{workspace.logs_dir}}", str(logs_dir)
                )
                result = subprocess.run(
                    ["bash", "-c", command],
                    check=False,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
                if result.returncode != 0:
                    problems.append(
                        f"{step_id} failed with {result.returncode}: {result.stderr.strip()}"
                    )
                    continue
                try:
                    parsed = json.loads(result.stdout)
                except json.JSONDecodeError as error:
                    problems.append(f"{step_id} did not emit JSON: {error}")
                    continue
                if not isinstance(parsed, dict):
                    problems.append(f"{step_id} output is not an object")
                    continue
                result_data = parsed
                values["execute_result"] = parsed
        return result_data, problems

    @staticmethod
    def run_rendered_bash(
        step_id: str,
        values: dict[str, str],
        directory: Path,
    ) -> subprocess.CompletedProcess[str]:
        command, environment = render_bash_step(step_section(step_id), values)
        environment.update(
            HOME=str(directory),
            THE_USUAL_BUNDLE_DIR=str(ROOT),
        )
        return subprocess.run(
            ["bash", "-c", command],
            cwd=directory,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    @staticmethod
    def prepare_path_step(
        step_id: str,
        sandbox: Path,
        logs_dir: Path,
    ) -> dict[str, object] | None:
        logs_dir.mkdir()
        if step_id == "write-plan-collect":
            plan_path = sandbox / "committed-plan.md"
            plan_path.write_text("# Committed plan\n", encoding="utf-8")
            payload: dict[str, object] = {
                "plan_path": str(plan_path),
                "feature": "safe fixture",
            }
            (logs_dir / "write-plan-result.json").write_text(
                json.dumps(payload) + "\n", encoding="utf-8"
            )
            return payload
        if step_id == "load-bearing-collect":
            payload = {
                "halt": "false",
                "halt_reason": "",
                "verified_count": 2,
                "falsified_count": 0,
                "acceptable_decisions": "none",
                "ledger_path": str(logs_dir / "load-bearing-ledger.md"),
            }
            (logs_dir / "load-bearing-result.json").write_text(
                json.dumps(payload) + "\n", encoding="utf-8"
            )
            return payload
        if step_id == "execute-collect":
            payload = {
                "blocked": "false",
                "blocked_reason": "",
                "tasks_completed": 2,
                "total_tasks": 2,
                "final_review_verdict": "PASSED",
                "execution_notes": "complete",
            }
            (logs_dir / "execute-result.json").write_text(
                json.dumps(payload) + "\n", encoding="utf-8"
            )
            return payload
        if step_id == "recap-outcome-validate":
            payload = {
                "schema_version": 1,
                "status": "success",
                "reason": None,
                "execution_tasks": {"completed": 1, "total": 1},
                "full_suite_gate": {"result": "passed"},
                "review_loops": {
                    "plan": {"rounds": 1, "final_verdict": "PASSED"},
                    "delta": {"rounds": 1, "final_verdict": "PASSED"},
                },
                "head_commit_sha": "0123456789abcdef0123456789abcdef01234567",
            }
            (logs_dir / "recap.md").write_text(
                "# Recap\n\nComplete.\n\n## Outcome Block\n\n```json\n"
                f"{json.dumps(payload)}\n```\n",
                encoding="utf-8",
            )
            return None
        raise AssertionError(f"no fixture for bash step {step_id}")

    @staticmethod
    def tree_snapshot(directory: Path) -> set[str]:
        return {path.relative_to(directory).as_posix() for path in directory.rglob("*")}

    def test_task_brief_executes_exact_structural_extraction(self):
        sentinel = "REQUEST_PAYLOAD_MUST_NOT_BE_ECHOED_7f31"
        user_request = (
            "## User Request\n"
            "\n"
            "### Requested result\n"
            f"Deliver {sentinel} while ordinary prose mentions **Goal:** safely.\n"
            "Inline code such as `**Goal:** example` remains literal request text.\n"
            "**Goal:** this entire line is ordinary prose inside Requested result.\n"
            "\n"
            "```markdown\n"
            "**Goal:** a line beginning with the label inside a backtick fence\n"
            "```\n"
            "\n"
            "~~~text\n"
            "**Goal:** a line beginning with the label inside a tilde fence\n"
            "~~~\n"
            "\n"
            "### Explicit constraints\n"
            "- Preserve every harmless literal above byte-for-byte.\n"
            "- Generate a brief for each selected task.\n"
            "\n"
            "### Accepted tradeoffs and residuals\n"
            "- The examples remain documentation only.\n"
            "\n"
        )
        planner_goal = "**Goal:** Build the actual planner-owned result.\n"
        plan = (
            user_request
            + planner_goal
            + "**Architecture:** Keep the planner architecture out of task briefs.\n"
            + "**Tech Stack:** Standard tools.\n"
            + "\n"
            + "---\n"
            + "\n"
            + "## Global Constraints\n"
            + "- GLOBAL_ONLY: applies to every task.\n"
            + "- Keep the current User Request unchanged.\n"
            + "\n"
            + "---\n"
            + "\n"
            + "### Task 1: First component\n"
            + "- TASK_ONE_ONLY\n"
            + "- Implement the first component.\n"
            + "\n"
            + "### Task 2: Second component\n"
            + "- TASK_TWO_ONLY\n"
            + "- Implement the second component.\n"
            + "\n"
            + "## Architecture Notes\n"
            + "ARCHITECTURE_NOT_A_TASK\n"
        )

        errors = []
        for task_number, selected, other in (
            (1, b"TASK_ONE_ONLY", b"TASK_TWO_ONLY"),
            (2, b"TASK_TWO_ONLY", b"TASK_ONE_ONLY"),
        ):
            result, brief = self.run_task_brief(plan, task_number)
            if result.returncode != 0 or brief is None:
                errors.append(
                    f"task {task_number} did not produce a brief: "
                    f"{result.returncode} {result.stderr.strip()}"
                )
                continue
            request_bytes = user_request.encode()
            if brief.count(request_bytes) != 1:
                errors.append(
                    f"task {task_number} did not carry the exact User Request once"
                )
            request_at = brief.find(request_bytes)
            constraints_at = brief.find(b"## Global Constraints")
            task_at = brief.find(f"### Task {task_number}:".encode())
            if not (request_at == 0 < constraints_at < task_at):
                errors.append(
                    f"task {task_number} brief order is not User Request, "
                    "Global Constraints, selected task"
                )
            if selected not in brief or other in brief:
                errors.append(f"task {task_number} selected the wrong task text")
            if b"GLOBAL_ONLY" not in brief:
                errors.append(f"task {task_number} lost Global Constraints content")
            for leaked in (
                planner_goal.encode(),
                b"**Architecture:**",
                b"## Architecture Notes",
                b"ARCHITECTURE_NOT_A_TASK",
            ):
                if leaked in brief:
                    errors.append(
                        f"task {task_number} leaked planner-only content: "
                        f"{leaked.decode()}"
                    )

        malformed = {
            "missing User Request": plan.replace(
                "## User Request\n", "## Missing User Request\n", 1
            ),
            "duplicate User Request": plan.replace(
                "## User Request\n",
                "## User Request\n\n## User Request\n",
                1,
            ),
            "missing planner Goal": plan.replace(planner_goal, "", 1),
            "duplicate planner Goal": plan.replace(
                planner_goal, planner_goal + planner_goal, 1
            ),
            "misordered Goal": planner_goal + plan.replace(planner_goal, "", 1),
        }
        for label, malformed_plan in malformed.items():
            result, brief = self.run_task_brief(malformed_plan, 1)
            if result.returncode == 0 or brief is not None:
                errors.append(f"{label} produced a usable task brief")
            combined_output = result.stdout + result.stderr
            if sentinel in combined_output:
                errors.append(f"{label} echoed request content while failing closed")

        if errors:
            self.fail("\n".join(errors))

    def test_capped_plan_review_has_terminal_nonconvergence_route(self):
        errors = []

        expected_validator = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                "HEAD:scripts/validate-recap-outcome.py",
            ],
            check=True,
            capture_output=True,
        ).stdout
        if (
            hashlib.sha256(expected_validator).digest()
            != hashlib.sha256(VALIDATOR_PATH.read_bytes()).digest()
        ):
            errors.append("recap validator schema/script changed from current HEAD")

        false_values: dict[str, object] = {
            "plan_passed": "false",
            "delta_passed": "false",
        }
        for implementation_step in ("execute-plan", "fresheyes-delta"):
            if condition_allows(step_section(implementation_step), false_values):
                errors.append(
                    f"{implementation_step} runs after capped plan-review failure"
                )

        execute_result, route_problems = self.run_execute_result_bash("false")
        errors.extend(route_problems)
        if execute_result is None:
            errors.append(
                "plan-failure route reaches recap without a defined execute_result"
            )
        else:
            completed = execute_result.get("tasks_completed")
            total = execute_result.get("total_tasks")
            if (
                type(completed) is not int
                or type(total) is not int
                or completed != 0
                or total < 0
            ):
                errors.append(
                    "plan-failure route does not report honest nonnegative "
                    f"execution counts (got {completed}/{total})"
                )
            payload = {
                "schema_version": 1,
                "status": "non-convergence",
                "reason": "Plan review hit its cap without passing; execution did not run.",
                "execution_tasks": {"completed": completed, "total": total},
                "full_suite_gate": {"result": "not-run"},
                "review_loops": {
                    "plan": {"rounds": 3, "final_verdict": "FAILED"},
                    "delta": {"rounds": 0, "final_verdict": "NOT_RUN"},
                },
                "head_commit_sha": "0123456789abcdef0123456789abcdef01234567",
            }
            validation = self.run_validator(payload)
            if validation.returncode != 0:
                errors.append(
                    "unchanged terminal validator rejects the plan-failure route: "
                    f"{validation.stderr.strip()}"
                )

        recap = norm(step_section("recap"))
        for required in (
            "If plan_passed is not 'true'",
            "must NOT recommend merging",
            "no success and no merge recommendation",
        ):
            if required.lower() not in recap.lower():
                errors.append(f"recap lost plan-failure rule: {required}")

        lost_result, lost_problems = self.run_execute_result_bash("true")
        if lost_result is not None:
            lost_payload = {
                "schema_version": 1,
                "status": "success",
                "reason": None,
                "execution_tasks": {
                    "completed": lost_result.get("tasks_completed"),
                    "total": lost_result.get("total_tasks"),
                },
                "full_suite_gate": {"result": "passed"},
                "review_loops": {
                    "plan": {"rounds": 1, "final_verdict": "PASSED"},
                    "delta": {"rounds": 1, "final_verdict": "PASSED"},
                },
                "head_commit_sha": "0123456789abcdef0123456789abcdef01234567",
            }
            lost_validation = self.run_validator(lost_payload)
            if lost_validation.returncode == 0:
                errors.append(
                    "lost successful-plan execution evidence can masquerade as "
                    f"success with {lost_result.get('tasks_completed')}/"
                    f"{lost_result.get('total_tasks')} tasks"
                )
        elif not lost_problems:
            # No result is acceptable only when the route cannot continue as success.
            execute_collect = step_section("execute-collect")
            if 'on_error: "fail"' not in execute_collect:
                errors.append(
                    "lost successful-plan execution output is undefined without "
                    "a loud failing gate"
                )

        if errors:
            self.fail("\n".join(errors))

    def test_bash_dynamic_bindings_are_non_code_and_injection_safe(self):
        classification = {
            "workspace.logs_dir": "untrusted dynamic path from workspace output",
            "load_bearing_result.halt_reason": "untrusted agent-produced string",
            "load_bearing_result.ledger_path": "untrusted agent-produced path",
        }
        expected_path_channels = {
            "write-plan-collect": "workspace.logs_dir",
            "load-bearing-collect": "workspace.logs_dir",
            "execute-collect": "workspace.logs_dir",
            "recap-outcome-validate": "workspace.logs_dir",
        }
        bash_steps = {
            step_id: section
            for step_id, section in top_level_steps()
            if step_field(section, "type") == "bash"
        }

        raw_inventory = []
        unclassified = []
        missing_channels = []
        unsafe_variable_use = []
        for step_id, section in bash_steps.items():
            command = step_command(section)
            for binding in sorted(set(re.findall(r"\{\{([^}]+)\}\}", command))):
                if binding not in classification:
                    unclassified.append(f"{step_id} -> {binding}")
                    continue
                raw_inventory.append(
                    f"{step_id} -> {binding} [{classification[binding]}]"
                )

        for step_id, binding in expected_path_channels.items():
            section = bash_steps[step_id]
            command = step_command(section)
            env_bindings = step_env_bindings(section)
            variables = [
                variable
                for variable, mapped_binding in env_bindings.items()
                if mapped_binding == binding
            ]
            if not variables:
                missing_channels.append(f"{step_id} -> {binding}")
                continue
            for variable in variables:
                shell_references = list(
                    re.finditer(
                        rf"\$(?:\{{{re.escape(variable)}\}}|{re.escape(variable)}\b)",
                        command,
                    )
                )
                for reference in shell_references:
                    line_start = command.rfind("\n", 0, reference.start()) + 1
                    if command[line_start : reference.start()].count('"') % 2 == 0:
                        unsafe_variable_use.append(
                            f"{step_id} uses unquoted ${variable}"
                        )
                if re.search(
                    rf"(?m)^\s*echo\b[^\n]*\$(?:\{{{re.escape(variable)}\}}|{re.escape(variable)}\b)",
                    command,
                ):
                    unsafe_variable_use.append(
                        f"{step_id} echoes dynamic ${variable} instead of "
                        "printf/safe Python"
                    )

        canaries = {
            "dollar_substitution": "$(printf injected > SENTINEL_DOLLAR)",
            "backticks": "`printf injected > SENTINEL_BACKTICK`",
            "double_quote": 'dq"; printf injected > SENTINEL_DQUOTE; printf "',
            "single_quote": "sq'; printf injected > SENTINEL_SQUOTE; printf '",
            "semicolon": "semi;printf injected > SENTINEL_SEMICOLON",
            "newline": "line\nprintf injected > SENTINEL_NEWLINE",
            "glob": "glob*?[ab]",
            "leading_dash": "-n",
            "pipe_ampersand": "pipe|printf injected > SENTINEL_PIPE &",
        }
        executed_canaries = set()
        behavior_failures = set()
        unintended_paths = set()
        privacy_leaks = set()

        for step_id, binding in expected_path_channels.items():
            for label, canary in canaries.items():
                with tempfile.TemporaryDirectory() as directory:
                    sandbox = Path(directory)
                    logs_dir = sandbox / canary
                    expected_payload = self.prepare_path_step(
                        step_id, sandbox, logs_dir
                    )
                    before = self.tree_snapshot(sandbox)
                    values = {
                        "workspace.logs_dir": str(logs_dir),
                        "load_bearing_result.halt_reason": "unused",
                        "load_bearing_result.ledger_path": str(
                            logs_dir / "load-bearing-ledger.md"
                        ),
                    }
                    result = self.run_rendered_bash(step_id, values, sandbox)
                    created = self.tree_snapshot(sandbox) - before
                    sentinel_paths = {path for path in created if "SENTINEL_" in path}
                    if sentinel_paths:
                        executed_canaries.add(f"{step_id} -> {binding} ({label})")
                        unintended_paths.update(
                            f"{step_id}: {path}" for path in sentinel_paths
                        )
                    if result.returncode != 0:
                        behavior_failures.add(
                            f"{step_id} -> {binding} ({label}) returned "
                            f"{result.returncode}"
                        )
                        continue
                    if expected_payload is None:
                        if result.stdout or result.stderr:
                            behavior_failures.add(
                                f"{step_id} -> {binding} ({label}) changed "
                                "validator output"
                            )
                        continue
                    try:
                        actual_payload = json.loads(result.stdout)
                    except json.JSONDecodeError:
                        behavior_failures.add(
                            f"{step_id} -> {binding} ({label}) emitted invalid JSON"
                        )
                    else:
                        if actual_payload != expected_payload:
                            behavior_failures.add(
                                f"{step_id} -> {binding} ({label}) changed "
                                "benign result data"
                            )

        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            canary = canaries["single_quote"]
            logs_dir = sandbox / canary
            logs_dir.mkdir()
            before = self.tree_snapshot(sandbox)
            values = {
                "workspace.logs_dir": str(logs_dir),
                "load_bearing_result.halt_reason": "unused",
                "load_bearing_result.ledger_path": str(
                    logs_dir / "load-bearing-ledger.md"
                ),
            }
            result = self.run_rendered_bash("load-bearing-collect", values, sandbox)
            created = self.tree_snapshot(sandbox) - before
            sentinel_paths = {path for path in created if "SENTINEL_" in path}
            if sentinel_paths:
                executed_canaries.add(
                    "load-bearing-collect -> workspace.logs_dir (single_quote fallback)"
                )
                unintended_paths.update(
                    f"load-bearing-collect: {path}" for path in sentinel_paths
                )
            try:
                fallback = json.loads(result.stdout)
            except json.JSONDecodeError:
                behavior_failures.add(
                    "load-bearing-collect -> workspace.logs_dir "
                    "(single_quote fallback) emitted invalid JSON"
                )
            else:
                expected_ledger = str(logs_dir / "load-bearing-ledger.md")
                if (
                    result.returncode != 0
                    or fallback.get("ledger_path") != expected_ledger
                ):
                    behavior_failures.add(
                        "load-bearing-collect -> workspace.logs_dir "
                        "(single_quote fallback) changed benign result data"
                    )

        guard_step = "load-bearing-halt-guard"
        for binding in (
            "load_bearing_result.halt_reason",
            "load_bearing_result.ledger_path",
        ):
            for label, canary in canaries.items():
                with tempfile.TemporaryDirectory() as directory:
                    sandbox = Path(directory)
                    sensitive = f"SENSITIVE_{label}_{binding}::{canary}"
                    values = {
                        "workspace.logs_dir": str(sandbox / "logs"),
                        "load_bearing_result.halt_reason": "safe reason",
                        "load_bearing_result.ledger_path": str(
                            sandbox / "safe-ledger.md"
                        ),
                    }
                    values[binding] = sensitive
                    before = self.tree_snapshot(sandbox)
                    result = self.run_rendered_bash(guard_step, values, sandbox)
                    created = self.tree_snapshot(sandbox) - before
                    sentinel_paths = {path for path in created if "SENTINEL_" in path}
                    if sentinel_paths:
                        executed_canaries.add(f"{guard_step} -> {binding} ({label})")
                        unintended_paths.update(
                            f"{guard_step}: {path}" for path in sentinel_paths
                        )
                    if result.returncode != 1:
                        behavior_failures.add(
                            f"{guard_step} -> {binding} ({label}) did not fail closed"
                        )
                    if "SENSITIVE_" in result.stdout + result.stderr:
                        privacy_leaks.add(f"{guard_step} -> {binding}")

        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            logs_dir = sandbox / "safe-logs"
            logs_dir.mkdir()
            blocked_reason = (
                "SENSITIVE_BLOCKER_REASON $(printf injected > SENTINEL_BLOCKER)"
            )
            (logs_dir / "execute-result.json").write_text(
                json.dumps(
                    {
                        "blocked": "true",
                        "blocked_reason": blocked_reason,
                        "tasks_completed": 0,
                        "total_tasks": 1,
                        "final_review_verdict": "NOT_RUN",
                        "execution_notes": "blocked",
                    }
                ),
                encoding="utf-8",
            )
            before = self.tree_snapshot(sandbox)
            result = self.run_rendered_bash(
                "execute-collect",
                {
                    "workspace.logs_dir": str(logs_dir),
                    "load_bearing_result.halt_reason": "unused",
                    "load_bearing_result.ledger_path": "unused",
                },
                sandbox,
            )
            created = self.tree_snapshot(sandbox) - before
            sentinel_paths = {path for path in created if "SENTINEL_" in path}
            if sentinel_paths:
                executed_canaries.add(
                    "execute-collect -> execute_result.blocked_reason"
                )
            if result.returncode != 1:
                behavior_failures.add(
                    "execute-collect blocker diagnostic did not fail closed"
                )
            if "SENSITIVE_BLOCKER_REASON" in result.stdout + result.stderr:
                privacy_leaks.add("execute-collect -> execute_result.blocked_reason")

        failures = []
        if raw_inventory:
            failures.append(
                "raw untrusted substitutions in bash command source:\n- "
                + "\n- ".join(sorted(raw_inventory))
            )
        if unclassified:
            failures.append(
                "unclassified bash substitutions:\n- "
                + "\n- ".join(sorted(unclassified))
            )
        if missing_channels:
            failures.append(
                "missing env/non-code channels:\n- "
                + "\n- ".join(sorted(missing_channels))
            )
        if unsafe_variable_use:
            failures.append(
                "unsafe shell-variable use:\n- "
                + "\n- ".join(sorted(set(unsafe_variable_use)))
            )
        if executed_canaries:
            failures.append(
                "executed injection canaries:\n- "
                + "\n- ".join(sorted(executed_canaries))
            )
        if unintended_paths:
            failures.append(
                "unintended paths created:\n- " + "\n- ".join(sorted(unintended_paths))
            )
        if behavior_failures:
            failures.append(
                "benign data behavior changed:\n- "
                + "\n- ".join(sorted(behavior_failures))
            )
        if privacy_leaks:
            failures.append(
                "privacy-unsafe blocker diagnostics:\n- "
                + "\n- ".join(sorted(privacy_leaks))
            )
        if failures:
            self.fail("\n\n".join(failures))


class TestReleaseAndPriorProtections(unittest.TestCase):
    """v3.13 metadata advances without weakening the v3.9-v3.12 gates."""

    def test_v313_versions_and_changelog_are_synchronized(self):
        self.assertEqual("3.13.1", version_of(RECIPE))
        self.assertEqual("3.13.1", version_of(BUNDLE))
        self.assertEqual("3.13.1", version_of(BEHAVIOR))
        self.assertRegex(RECIPE, r"(?m)^# v3\.13\.1 \(")

    def test_v39_through_v312_protections_remain(self):
        recipe = norm(RECIPE)
        for protection in (
            "Adopt a valid passing result as the current logical invocation",
            'exactly one "## Outcome Block"',
            "## Baseline (recorded at workspace setup)",
            "a same-family selection is rejected, not run",
            "CONFLICTING markers in one report",
            "reviewer identity label",
        ):
            self.assertIn(protection, recipe)


if __name__ == "__main__":
    unittest.main()
