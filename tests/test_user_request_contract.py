"""Behavior tests for the revision-free User Request flow's executable paths.

Only pieces of the User Request contract that are actually executed are
covered here: task-brief extraction via embedded bash, the terminal
non-convergence route through the recap validator, and injection safety of
the dynamic bash bindings. Whether the parent/README/recipe *describe* the
flow in expected prose is not asserted here — matching expected wording is
not a behavior test.
"""

from __future__ import annotations

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
VALIDATOR_PATH = ROOT / "scripts" / "validate-recap-outcome.py"

RECIPE = RECIPE_PATH.read_text(encoding="utf-8")


def norm(text: str) -> str:
    """Collapse formatting differences while retaining contract wording."""
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).strip()


def step_section(step_id: str) -> str:
    """Return one top-level recipe step."""
    start = RECIPE.index(f'  - id: "{step_id}"')
    nxt = RECIPE.find("\n  - id: ", start + 1)
    return RECIPE[start:] if nxt == -1 else RECIPE[start:nxt]


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


if __name__ == "__main__":
    unittest.main()
