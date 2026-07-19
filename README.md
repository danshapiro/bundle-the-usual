# bundle-the-usual

An [Amplifier](https://github.com/microsoft/amplifier) bundle providing
**"the usual"** — a rigorous, self-contained development workflow, invoked by
saying things like *"implement X with the usual"*.

## What it does

One recipe (`recipes/the-usual.yaml`) drives seven stages, end to end, with
loud progress banners and no routine approval gates (it halts only on serious
issues):

1. **Workspace** — dedicated git worktree under `.worktrees/<slug>/`
2. **Plan** — zero-context, no-placeholder TDD implementation plan with
   bite-sized tasks and a self-review pass
3. **Load-bearing validation** — enumerates the falsifiable assumptions the
   plan depends on (stateful finder + strategist, parallel stateless
   validators); unverifiable assumptions get an explicit `acceptable`
   decision after alternatives are tried
4. **Fresh eyes on the plan** — independent zero-context review by a
   *different model family*, up to 3 iterations or until it passes
5. **Execute** — subagent-driven development: fresh implementer per task,
   spec review per task, durable progress ledger
6. **Fresh eyes on the delta** — independent cross-model review of the full
   diff vs the original fork point, up to 5 iterations or until it passes
7. **Recap** — what was found at each stage, plus a low-jargon summary of
   what was built

## Install

```bash
amplifier bundle add git+https://github.com/danshapiro/bundle-the-usual@main --name the-usual
amplifier bundle use the-usual
```

Or layer just the behavior onto your existing bundle stack — add to
`bundle.app` in `~/.amplifier/settings.yaml`:

```yaml
bundle:
  app:
    - git+https://github.com/danshapiro/bundle-the-usual@main#subdirectory=behaviors/the-usual.yaml
```

(For local development, a local path works in either place, e.g.
`/path/to/bundle-the-usual/behaviors/the-usual.yaml`.)

## Use

In any session with the bundle composed:

> implement tetris with the usual in a subdirectory

Or run the recipe directly:

```bash
amplifier tool invoke recipes operation=execute \
  recipe_path=@the-usual:recipes/the-usual.yaml \
  context='{"task": "<spec text or path>", "repo_path": "/abs/path/to/repo"}'
```

Optional context overrides: `reviewer_provider` / `reviewer_model`
(defaults `openai` / `gpt-*`) select the independent cross-model reviewer —
configure at least two provider families for the fresh-eyes stages to be
meaningful.

## Requirements

- The `recipes` tool (included via this bundle's dependency on
  `amplifier-bundle-recipes`; already present in most Amplifier setups)
- `git` (worktrees are used for isolation)
- Two configured provider families (e.g. Anthropic + OpenAI) for
  cross-model review
