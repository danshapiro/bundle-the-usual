# "The Usual" — Development Workflow Recipe

This bundle provides "the usual": a rigorous, self-contained development
workflow encoded as a recipe. When the user asks to do something "with the
usual" (e.g. "implement X with the usual"), execute the recipe — do NOT
re-implement the workflow manually; the recipe is the canonical process.

## Invocation

```
recipes(
  operation="execute",
  recipe_path="@the-usual:recipes/the-usual.yaml",
  context={
    "task": "<the user's request, or the spec text/path they gave>",
    "repo_path": "<absolute path to a git repo — resolve per the rules below>"
  }
)
```

## Resolving repo_path

1. If the user names an existing git repo or a directory inside one, use that
   repo's root.
2. If they say "in a subdirectory", "in a new project", or the target
   directory doesn't exist or isn't a git repo (greenfield): tell the user the
   exact path you intend to create and GET THEIR CONFIRMATION FIRST. Only
   after they confirm: create the directory, `git init`, and make an initial
   commit (`git commit --allow-empty -m "init"`) so worktrees work, then use
   it as repo_path.
3. If the target is ambiguous (current dir is not a repo and no target
   named), ask the user.

## Run handling

- The recipe checkpoints between steps; if a run is interrupted, resume with
  `recipes(operation="resume", session_id=...)` rather than starting over.
- If a run halts via a guard (data-loss risk or execution blocker), surface
  the guard's message to the user and wait for their decision.
- Optional context overrides: `reviewer_provider` / `reviewer_model`
  (defaults: `openai` / `gpt-*`) control the independent cross-model
  reviewer. The reviewer should be a DIFFERENT model family from the
  executing session's model.
