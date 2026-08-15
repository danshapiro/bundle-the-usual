# "The Usual" — Development Workflow Recipe

When the user asks for work "with the usual", execute
`@the-usual:recipes/the-usual.yaml`; do not reimplement the workflow manually.
The conversational parent alone has the full conversation and therefore owns
the current User Request supplied to the recipe.

## Build the current User Request

Silently derive one standalone snapshot from the full conversation. Exclude
bare workflow activation ("use the usual"). Atomize direct instructions and
clearly adopted proposals, resolve references, and apply later explicit
direction: it supersedes, adds, or withdraws earlier atoms. Render only active
obligations and explicitly accepted tradeoffs; omit rejected, unresolved,
unsupported, and irrelevant history. Concision removes rationale and
repetition, never requirements.

Use exactly this revision-free shape:

## User Request

### Requested result
<compact standalone current outcome>

### Explicit constraints
- <active user-stated or clearly adopted constraint>
- None stated.

### Accepted tradeoffs and residuals
- <explicitly accepted tradeoff or residual>
- None stated.

Before storing or delegating either input, sanitize literal credentials,
private keys, Authorization headers, token values, secret values, and
sensitive payloads. Keep safe behavior through names or references. Never log
removed values.

## Invocation

```
recipes(
  operation="execute",
  recipe_path="@the-usual:recipes/the-usual.yaml",
  context={
    "task": "<separate sanitized initial provenance or safe spec locator>",
    "user_request": "<complete sanitized User Request block>",
    "repo_path": "<absolute target git repository root>"
  }
)
```

`task` never overrides the current `user_request`. Resolve `repo_path` to an
existing repository root. For greenfield work, state the intended path and get
confirmation before creating and initializing it; ask when the target is
ambiguous.

## Later direction and run handling

If later explicit direction arrives, update the current User Request block and
relevant plan or docs, assess practical impact, and use judgment to notify,
redirect, cancel, replace, restart, reuse, disregard stale results, or leave
agents or work alone. Coordinate only affected work and preserve unaffected
valid work. An active blocking recipe can adjust only after the blocking recipe
call returns or is interrupted.

For an unchanged interruption, use
`recipes(operation="resume", session_id=...)`. Changed direction is not an
automatic resume decision. Surface guard messages and await the user's
decision. `reviewer_provider` / `reviewer_model` remain optional cross-model
review overrides.
