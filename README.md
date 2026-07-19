# The Usual

**A disciplined, review-heavy way to have an AI build software for you.**

"The usual" is an add-on for [Amplifier](https://github.com/microsoft/amplifier),
a command-line AI assistant from Microsoft. Once installed, you can say things
like:

> implement tetris with the usual in a subdirectory

…and instead of the AI just writing code and hoping for the best, it runs a
rigorous end-to-end process: plan, verify assumptions, get independently
reviewed by a *different* AI, build test-first, get reviewed again, and report
back in plain language.

## What actually happens

When you ask for something "with the usual", the assistant works through seven
stages, printing a big banner as it enters each long-running one:

1. **Safe workspace** — work happens on an isolated branch in a dedicated
   folder inside your project. Nothing you have is touched until you decide to
   merge the result.
2. **Plan** — it writes a detailed, step-by-step implementation plan with
   tests planned first, small tasks, exact file paths, and no hand-waving
   ("add error handling later" is not allowed).
3. **Check the risky assumptions** — it identifies the claims the plan quietly
   depends on ("this library supports X", "the config lives in Y") and
   verifies each with real evidence: running code, reading source, checking
   documentation. If something can't be verified, it tries alternative
   approaches and picks the most defensible path, recording its reasoning.
4. **Independent plan review** — the plan is reviewed by a second AI from a
   different company, with zero knowledge of the conversation so far (fresh
   eyes, no groupthink). Problems get fixed and re-reviewed, up to 3 rounds.
5. **Build** — implementation happens one small task at a time, test-first,
   with each task's output checked against the plan before moving on.
6. **Independent review of the result** — the complete set of changes gets
   the same fresh-eyes treatment, up to 5 rounds, until it passes.
7. **Recap** — you get a report of what was found at every stage plus a
   jargon-free summary of what was built, and options for merging it.

It only stops mid-run for serious problems (for example, anything that risks
data loss). Everything else is handled and reported at the end.

## Install

1. **Install Amplifier** — follow the instructions at
   [github.com/microsoft/amplifier](https://github.com/microsoft/amplifier).
2. **Add this package:**

   ```bash
   amplifier bundle add git+https://github.com/danshapiro/bundle-the-usual@main --name the-usual
   amplifier bundle use the-usual
   ```

   Already have a customized Amplifier setup you don't want to replace? Layer
   just the trigger onto it instead — add this line under `bundle.app` in
   `~/.amplifier/settings.yaml`:

   ```yaml
   bundle:
     app:
       - git+https://github.com/danshapiro/bundle-the-usual@main#subdirectory=behaviors/the-usual.yaml
   ```

## Use

Start Amplifier (`amplifier`) and ask for work "with the usual":

> implement a markdown-to-html converter with the usual in a subdirectory

- If the target isn't an existing git project, it tells you exactly what
  folder it wants to create and asks for your OK first.
- Long stages announce themselves with unmissable banners, so you can tell
  where the run is at a glance.
- If a run is interrupted, it can resume where it left off rather than
  starting over.

You can also skip the conversation and run it directly:

```bash
amplifier tool invoke recipes operation=execute \
  recipe_path=@the-usual:recipes/the-usual.yaml \
  context='{"task": "describe what to build, or a path to a spec file", "repo_path": "/absolute/path/to/your/git/repo"}'
```

## What you need

- **git** — the isolated-workspace stage uses git branches and worktrees.
- **Two AI provider accounts** (for example Anthropic + OpenAI), configured in
  Amplifier. The independent reviews deliberately use a different AI company
  than the one doing the work — that separation is the point. By default the
  work is done by whatever model your session runs and reviews go to OpenAI;
  override with the `reviewer_provider` / `reviewer_model` options if your
  setup is reversed.

## What's in this repository

| Path | What it is |
|---|---|
| `recipes/the-usual.yaml` | The workflow itself — every stage, rule, and review prompt |
| `context/the-usual-instructions.md` | Teaches the assistant to recognize "with the usual" |
| `behaviors/the-usual.yaml` | The hook that loads those instructions into your sessions |
| `bundle.md` | The package definition Amplifier installs |

## License

MIT — see [LICENSE](LICENSE).
