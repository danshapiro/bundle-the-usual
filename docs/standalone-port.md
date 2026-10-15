# Maintaining the standalone-to-Amplifier port

## Adopted sources

This port adopts `danshapiro/skill-the-usual` commit
`d57367b3ceadcd8e69514d28f69deaa169594e28` (standalone PR #8).
That version deliberately adapted the six corresponding Superpowers v7.0.0
packages at `bb92a77741419a4ab5f06e711a283343f1ada0c3`.
`LICENSE.superpowers` preserves the upstream MIT notice.

This is a one-time adoption, not synchronization. `recipes/the-usual.yaml`
remains the complete runtime methodology. Neither the standalone checkout,
this maintenance document, nor installed Superpowers skills are runtime inputs.
The historical changelog records older ports; the current step prompts govern.

## Method ownership

| Standalone source | Recipe owner |
| --- | --- |
| `usual-using-git-worktrees.md` | `workspace-setup` |
| `usual-writing-plans.md` | `write-plan` |
| `usual-executing-plans.md` | Execution coordination within `execute-plan` |
| `usual-subagent-driven-development.md` | Task execution within `execute-plan` |
| `usual-test-driven-development.md` and its embedded test-writing guide | TDD within `execute-plan`; complete method goes to implementers and fixers |
| `usual-requesting-code-review.md` and its three embedded templates | Informed task, fix, and whole-branch reviews within `execute-plan` |

Keep applicable source wording verbatim, including examples and companion
prompts. Replace an inapplicable instruction in its existing span; do not keep
it active and append a contradictory override. Preserve local interfaces by
mapping them explicitly rather than summarizing the method in a new voice.

## Amplifier-specific interfaces

- Dispatch uses the native `delegate` tool with `context_depth="none"`.
  Use the registered `the-usual:step-runner` target for recipe-owned task and
  review assignments, with each role's template governing its exploration
  boundary. Select the supported `model_role` for implementation and informed review;
  preserve the configured provider, model and reasoning effort for Fresh Eyes.
  Calls block until their child returns; batch independent ready calls before
  dispatch and reconcile results after return. Use only supported
  delegation/resume mechanisms, never invented wait/list APIs or CLI routes.
  The standalone shell reviewer and its PID-test fixture are not copied: the
  bundle uses native delegation rather than that process transport.
- A fresh worker receives the complete current User Request, scope policy and
  turn-economy policy, plus its complete applicable method and template.
  Naming a section without supplying its text cannot transfer that context.
- Recipe checkpointing, existing step receipts and logs own run recovery.
  The SDD progress ledger remains in the worktree Git directory and its first
  entry remains the recorded Baseline. Do not introduce a second run-state
  schema or a second durable current-request document.
- `workspace` output, `write-plan-result.json`, `execute-result.json` and
  their collectors remain the bundle interfaces. The committed plan is the
  current User Request carrier. Put its complete request block immediately
  before Goal so task-brief extraction preserves it unchanged; keep Review
  Focus separate from Global Constraints.
- The execution-step controller coordinates task-boundary gate decisions,
  final gating, and informed whole-branch review without restarting the recipe
  step. Preserve `full_suite_commits`, exact-command/HEAD evidence reuse,
  complete remediation batches, baseline reproduction receipts and service
  cleanup. Gate again at final fix commits.
- Informed fix re-review may receive prior findings. Context-isolated Fresh
  Eyes never receives earlier findings or verdicts. Their budgets stay separate.
- The conversational parent retains the greenfield-target confirmation and
  changed-intent handling documented in `context/the-usual-instructions.md`.

## Failure routing

Distinguish completed review findings from an inability to perform independent
review. A substantive malformed report remains feedback and does not become a
clean pass. Missing execution, exhausted supported routes, same-family refusal,
or an explicit unable-to-review response stops the workflow without consuming
a substantive review round. Preserve last completed counts and verdicts;
`NOT_RUN` with zero means no review completed.

Both the model's instructions and the recipe's loop/guard control flow must
implement this distinction. A focused review execution failure propagates out
of the delta step; it cannot start another focused/delta round, repair, or
full-suite gate. Persist blocker evidence before returning, and honor it on
resume. A failure guard emits `review-execution-failure.md` with only available facts,
without replacing an earlier recap or claiming a full-suite gate result.
Ordinary completion uses the existing recap and its validator. Never mark a blocked review
passed merely to escape a loop.

## Validation and future ports

Start from a named, committed standalone version. Read its conversion guide,
corresponding methods, companion templates and local contracts; then record
only the platform mappings that this recipe actually requires. Update the
runtime instructions and their representations together. No silent upstream
or downstream synchronization is allowed.

Run `python3 -m unittest discover -s tests -v`. Exercise the embedded Bash
with disposable repositories and paths containing spaces. Verify recipe YAML,
step schema and actual while-loop behavior using an available Amplifier recipe
engine. Script review outcomes to cover first-attempt failure, failure after a
completed review, focused failure, ordinary non-convergence, malformed feedback,
valid pass and blocked resume. A scripted engine test is not a live-provider
review; describe that distinction in the change's validation record.
