# "the-usual" speed report — trace analysis, experiments, and validated changes

Date: 2026-08-09 · Author: autonomous workstream (Amplifier) for Dan Shapiro
Recipe under study: `/home/dan/code/bundle-the-usual/recipes/the-usual.yaml` (v3.7.0 on main — the task brief said v3.6.0, but main gained a v3.7.0 release-hygiene commit `33e9079` on 2026-08-08; no recipe-logic changes in it. The draft here is therefore **v3.8.0-draft**, on branch `speed-v3.8.0-draft`.)

## 1. Where the time actually goes (real-run trace analysis)

### 1.1 Data mined

- 34 recipe sessions for project `home-dan-code-shapiroserver2` under
  `/home/dan/.amplifier/projects/'{project}'/recipe-sessions/.../recipe-sessions/*/state.json`,
  of which **14 completed 9-step runs in the 2026-08-06 → 2026-08-08 window** (incl.
  `81a3c032db04462d-20260807-182631`, the frontmatter-py312 run that produced runtime
  commits 3664ad7/6f38592).
- 136 step-runner sub-session event logs
  (`~/.amplifier/projects/-home-dan-code-shapiroserver2/sessions/*_the-usual-step-runner/events.jsonl`),
  parsed with jq field projections only (`ts`, `event`, `tool_name`, fork metadata
  `recipe_step`, slug captured from the step prompt) — raw lines never entered context.
- Progress ledgers/reports under `/home/dan/code/nanoclaw-frontmatter-py312/.worktrees/.the-usual-logs/`
  and `/home/dan/code/shapiroserver2/.worktrees/.the-usual-logs/` (29 slugs).

Recent full runs took 2h10m–5h27m wall-clock (state.json `started` → last write):
81a3c032 (frontmatter-py312) 2h44m; a5e1ac5d 5h27m; 192aaf8e 4h31m; eed6f520 5h16m;
ea6c8a8b 4h24m; 9d5b52c1 2h10m; b7fbf496 2h48m; 0faf029a 3h30m; a5c76187 3h12m; etc.

### 1.2 Per-step wall-clock across all Aug 6–8 step-runner sessions

| step | n sessions | mean | max |
|---|---|---|---|
| execute-plan | 17 | **60.0 min** | 100 min |
| load-bearing | 18 | **54.0 min** | 119 min |
| write-plan | 16 | **33.2 min** | 62 min |
| fresheyes-plan | 31 (≈2.2 iterations/run) | 15.3 min/iter | 33 min |
| fresheyes-delta | 15 | 12.0 min | 30 min |
| workspace-setup | — | ~1.4 min | — |
| recap | 13 | 0.8 min | 0.9 min |

### 1.3 Inside the big steps (event-timeline microscopy)

**load-bearing** (frontmatter-py312 run, 48.5 min, session `…34fdc56f…`):

```
02:04–02:05  setup                                 ~1 min
02:05–02:17  delegate #1: FINDER                   12.1 min  ← SERIAL, re-surveys repo
02:18–02:20  step-runner model turn                 2.3 min
02:20–02:26  delegate #2: STRATEGIST                6.4 min  ← SERIAL
02:27–02:30  step-runner model turn                 2.7 min
02:30–02:43  delegates #3–6: 4 VALIDATORS          13.0 min  ← already PARALLEL (good)
02:43–02:52  plan fixes, ledger, commit             9.5 min  (incl. 3.2m + 2.0m solo model turns)
```

The parallel validator wave is only ~27% of the step. The serial finder+strategist chain
(18.5 min) plus step-runner turn latency dominates. The finder's 12-minute survey
re-explores the repository write-plan's explorer wave just surveyed — its report
(`finder.md`) lands in the same `reports/` dir as write-plan's `conventions.md`,
`build-tooling.md`, etc., but nothing told it to read them.

**write-plan** (same run, 35 min): 4 explorers dispatched in ONE batch (15.5 min,
parallel — good), a 4.3-min model turn, a serial 5th explorer (2.3 min), then ~11 min of
plan-writing model turns where tool calls take 1 s and inter-turn gaps run 2.9–5.6 min.
≈49% of the step is step-runner model-turn latency, not tools.

**execute-plan** (same run, 41 min): strictly serial per task — implementer (4.5m) →
reviewer (1.7m) → implementer#2 (4.5m) → reviewer (1.3m) → implementer#3 (12m) →
reviewer (1.5m) → full-suite gate → final whole-branch review (3.6m) — with a 20–60 s
step-runner turn between every hop. Parallel implementer dispatch is prohibited by the
SDD methodology (same-worktree commit conflicts) — see §5.

### 1.4 Top 3 time sinks (with numbers)

1. **Step-runner model-turn latency on single-tool turns** — 35–50% of heavy-step
   wall-clock; 100–150 step-runner turns per run, many making one 1-second tool call.
   Extreme cases: load-bearing sessions with **19, 25, and 46 `edit_file` calls**
   (io-attribution-sampler, msgvault-restore-io-caps, nightly-compiler-host-wiring) —
   ≈1 plan/ledger edit per turn at 1–3 min latency each ⇒ ~20–45 min of pure
   bookkeeping latency inside a single step.
2. **Serial, redundant exploration across stages** — write-plan explorer wave (up to
   15.5 min) → load-bearing finder re-survey (12 min, serial) → fresheyes fix-phase
   explorers → per-task implementer re-reads, all over the same unchanged repo. The
   prevention artifacts already exist (`logs_dir/reports/*.md`) but were never handed
   forward.
3. **execute-plan's serial task pipeline** — 60 min mean, the largest step. Its inner
   loop is serial *by design* for correctness (one worktree). Tractable waste: the
   coordination turns between hops and per-task re-exploration, not the reviews.

### 1.5 Infra bugs confirmed while tracing

- **write-plan garbage output**: run `fc5e8cba…-20260808-130736` has `context.plan` =
  the raw string `"roles that are missing coverage: image-gen"`; every later
  `{{plan.plan_path}}` template then fails ("Cannot access plan_path on {{plan}} — it's
  a str"). `last30days-redeploy` shows the same failure as three consecutive ~6-second
  write-plan attempts (1 LLM call each, no tools, 08-07 11:03–11:13); `f39aecb2`
  (08-07 04:00) died the same way right after workspace-setup. write-plan was the only
  heavy step with **no file-based output pickup** (load-bearing and execute got theirs
  in commit `8a67483`).
- **Shared anchor file**: `/tmp/the-usual-pending-output.json` is a fixed path written
  by every run's workspace-setup. At analysis time it held values from an *unrelated*
  repo's run (`mutastic/pl81-multi-light`, written 2026-08-08 22:52) while other recipe
  sessions were live — the observed cross-run contamination channel.

## 2. Variant design (targets from §1.4/§1.5)

One variant (**v3.8.0-draft**), four changes, **zero gate/review/methodology-coverage
reductions** (nothing about validator counts, fresheyes caps, full-suite gates, or
review verdict handling changed):

1. **TURN ECONOMY** block in the five heavy step prompts (write-plan, load-bearing,
   execute-plan, fresheyes-plan, fresheyes-delta): batch independent tool calls into
   one turn; dispatch independent delegates in one batch; apply plan/ledger updates as
   consolidated edit sweeps (never one edit-turn per finding); no solo-turn
   bookkeeping. Framed as "changes turn count, not work done."
2. **EXPLORATION REUSE** block in the same five steps: `logs_dir/reports/` + a new
   `INDEX.md` is the run's shared exploration digest. Later stages seed subagents
   (load-bearing finder/validators, implementers, task reviewers, fix explorers) with
   existing report paths and explore only gaps. Orientation only: validators/reviewers
   still independently verify the claims they check; stale/contradicted reports must be
   re-explored. (The verbatim cross-model fresheyes reviewer prompt is untouched.)
3. **Per-run anchor path** (robustness): workspace-setup anchor is now
   `/tmp/the-usual-pending-output.{{session.id}}.json`.
4. **write-plan file-based output pickup** (robustness): write-plan writes
   `write-plan-result.json`; new `write-plan-collect` bash step reads it (result file →
   pending-output anchor → loud failure), mirroring `8a67483`.

Versioning note: the engine rejects pre-release version fields, so the YAML `version:`
reads `3.8.0` while the changelog entry is explicitly marked DRAFT.

## 3. Benchmark method

- Bench area `/tmp/usual-bench/`: six tiny seeded git repos (Python, stdlib-only,
  `python3 -m unittest` suites), two independent copies each (`-base`/`-var`), identical
  spec files per task. Tasks: (t1) fix a bug exposed by failing tests, (t2) add a small
  feature with tests, (t3) refactor with zero behavior change, (t4) add coverage to an
  untested module, (t5) docs↔code consistency fix, (t6) config/tooling (Makefile +
  pyproject).
- Baseline = pristine v3.7.0 YAML copy; variant = the v3.8.0-draft YAML from the branch.
- Executed end-to-end via `amplifier tool invoke recipes operation=execute …` from
  `/tmp/usual-bench` (own project namespace), 12 runs total in two waves; each task's
  base/var pair launched at the same second (fairness under shared API load); baseline
  starts staggered 4 min so baseline workspace-setups never overlap on the shared
  anchor bug.
- Timing: wall-clock from launcher timestamps; per-step from the step-runner
  sub-session event logs (same jq method as §1). No run hit the write-plan infra
  failure; no retries were needed.

## 4. Results

### 4.1 Wall-clock matrix (12 runs)

| task | baseline | variant | Δ wall-clock |
|---|---|---|---|
| t1 bugfix | 40.4 min | 39.3 min | **−2.7%** |
| t2 feature | 44.0 min | 40.5 min | **−7.8%** |
| t3 refactor | 57.2 min | 74.9 min | **+30.9%** ← 3 fresheyes-plan iterations vs 1 (see below) |
| t4 coverage | 42.7 min | 47.8 min | **+11.7%** ← load-bearing validators ran 5.8 min longer |
| t5 docs | 46.8 min | 49.3 min | **+5.2%** |
| t6 config | 46.3 min | 42.2 min | **−8.8%** |
| **total** | **4h37m** | **4h54m** | **+6.0%** (median Δ +1.3%) |

t3 confound: the variant run's plan drew a **major** executable-plan finding from the
cross-model reviewer and needed 3 review iterations (8.9+10.2+6.0 min) vs baseline's 1
(7.6 min). That is the ≤3× review loop doing its job on plan content (verdict noise
across arms), not variant machinery: subtracting the two extra iterations, t3-var ≈
58.7 min ≈ baseline +1.5 min, and the 12-run totals land at parity (+0.1%).

**Honest verdict: at toy-benchmark scale the variant is wall-clock NEUTRAL (3/6 faster,
3/6 slower; regressions flagged above, not cherry-picked).**

### 4.2 What the variant measurably DID change (mechanism validation)

Step-runner LLM-turn counts, summed over the six runs per arm (equal work, all gates
passed):

| step | baseline turns | variant turns | Δ |
|---|---|---|---|
| write-plan | 65 | 48 | **−26%** |
| load-bearing | 85 | 72 | **−15%** |
| execute-plan | 107 | 81 | **−24%** |
| fresheyes-plan (iter 1) | 48 | 36 | **−25%** |
| fresheyes-delta | 49 | 30 | **−39%** |
| overall | 354 | 267 | **−25%** |

Exploration-reuse evidence: load-bearing delegate dispatches dropped where reports
existed to reuse — t1: 6→3 (finder consumed the write-plan survey and the strategist
grouped 4 assumptions into ONE validator), t5: 6→4, t2: 8→7; INDEX.md was created and
maintained in every variant run.

Why turn reduction didn't move toy-scale wall-clock: on 3-file repos a step-runner turn
costs ~20–40 s (short context) and exploration is 1–2 min, so there was little latency
to reclaim — while the real runs the sinks were measured on have 1–3 min turns and
12–15 min re-survey waves. The −25% turns and reused reports are precisely the
mechanisms that attack §1.4 sinks #1 and #2; their wall-clock payoff scales with repo
size and context length and **remains unproven until A/B'd on a real-scale run** (§6).

### 4.3 Quality gates (the win condition): held on ALL benchmarks

All 12 runs, both arms: plan fresheyes **passed**; delta fresheyes **passed**; tasks
completed **n/n** (1/1, 1/1, 2/2, 1/1, 2/2, 2/2); load-bearing ledger written with
verified/falsified verdicts; **full-suite gate ran and PASSED in 12/12 progress
ledgers** (`Gate:`/`GATE:` entries with end-of-execution trigger); independent
post-run verification: `python3 -m unittest discover` **green in all 12 worktrees**;
final whole-branch review verdict "ready to merge: yes" in all 12. Variant runs
additionally produced sharper load-bearing outcomes in two cases (t1-var falsified 4
stale plan-quote assumptions and fixed the plan; baseline verified 3 without catching
the stale quotes).

### 4.4 Robustness fixes validated

- **Per-run anchor**: all six variant runs wrote
  `/tmp/the-usual-pending-output.<session-id>.json` (six distinct files observed); no
  shared-path writes. Baseline runs kept overwriting the single shared path.
- **write-plan-collect**: executed in 6/6 variant runs; `plan` context was a proper
  object in all cases; the garbage-string failure mode is structurally closed (result
  file → anchor → loud failure instead of silent str propagation).

## 5. Tried / considered and rejected (no cherry-picking)

- **Parallel implementer dispatch in execute-plan**: rejected without testing. All
  implementers share ONE worktree and commit as they go; concurrent implementers race
  on the git index and break the BASE..HEAD review-package flow. The recipe's SDD
  section already lists it as a known mistake; doing it safely needs per-task worktrees
  + merge machinery — a redesign with direct risk to review integrity.
- **Cheaper model roles for mechanical steps**: workspace-setup (~1.4 min) + recap
  (0.8 min) are <2% of a run — nothing to win; downgrading the step-runner on heavy
  steps risks controller-checkpoint judgment.
- **Reducing fresheyes caps / gates**: out of bounds by definition.
- **Merging load-bearing finder+strategist into one delegate**: plausible ~6–9 min/run
  saving but removes the controller checkpoint between extraction and strategy —
  methodology change, deferred.
- **Turn economy + reuse as a toy-scale wall-clock win**: tested honestly, did NOT
  materialize at this scale (§4.1); shipped anyway because the mechanism is proven
  (−25% turns, reused reports), quality held 12/12, and the targeted sinks only exist
  at real scale.

## 6. What I'd do next

1. **Real-scale A/B**: run v3.8.0-draft head-to-head against v3.7.0 on the next 2–3
   real shapiroserver2 tasks (the per-run anchor makes concurrent A/B safe). The §1.4
   sinks predict 30–60 min/run savings (finder re-survey + turn latency); verify
   against per-step traces with the same jq method.
2. **Per-task worktree parallel execution** (attack sink #3 properly): independent-task
   groups from the plan, one worktree per group, controller merges + re-reviews at
   join points. Biggest remaining prize (60-min mean step), needs design work.
3. **Engine-level fix for the write-plan garbage**: the three 6-second retries with 1
   LLM call each suggest a provider/parse failure upstream of the prompt; the collect
   step is a recipe-side seatbelt, not the root-cause fix.
4. Consider merging finder+strategist with an explicit controller checkpoint kept
   between strategy and validation (6–9 min/run, needs a rigor review first).

## 7. Deliverables

- This report: `/tmp/the-usual-speed-report.md`
- Branch: `speed-v3.8.0-draft` in `/home/dan/code/bundle-the-usual` (main untouched),
  changelog entry in the file header in house style, committed with Amplifier
  co-author attribution.
- Bench area preserved: `/tmp/usual-bench/` (seeds, specs, both recipe YAMLs, all 12
  run repos with worktrees/ledgers, launcher + scoring scripts, timing logs).
