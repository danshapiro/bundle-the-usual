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
        raise ValidationError("missing leading Outcome Block")
    if len(headings) != 1:
        raise ValidationError("exactly one Outcome Block is required")
    if headings[0].start() != 0:
        raise ValidationError("outcome block must come first")

    suffix = document[headings[0].end():]
    opener = "\n\n```json\n"
    if not suffix.startswith(opener):
        raise ValidationError("expected one leading json fence")

    rest = suffix[len(opener):]
    closing = re.search(r"\n```", rest)
    if closing is None:
        raise ValidationError("expected one leading json fence")
    body = rest[: closing.start()]

    try:
        return json.loads(body)
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
