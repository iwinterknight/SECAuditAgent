# /implement — IMPLEMENT stage (one task)

You are running the IMPLEMENT stage. The user has named a single task ID
from `tasks.md`. Your job is to make that one change, run its
feature-relevant acceptance check, **deliver the Code Walkthrough**,
propose a commit message, wait for approval, commit, and STOP.

This is the most rule-bound command in the SDD workflow. Read every
rule below before acting.

## When to use

- The user invokes `/implement T<N>` where T<N> is a task ID from
  `specs/<dated-slug>/tasks.md`.
- If the user says `/implement next`, find the first unchecked task.
- Verify before acting:
  - The task's checkbox is `[ ]` (not `[x]`).
  - The task's `Depends-on:` items (if any) are `[x]`.
  - The spec's `status` frontmatter is `tasks` or `implement`.

If preconditions fail, ASK before doing anything.

## The discipline (this is the load-bearing part)

1. **One task, period.** You implement exactly the named task. Not the
   one before, not the one after, not "while I'm here let me also...".
   If you find another change that needs to happen, you MAKE A NOTE
   for the user and STOP.
2. **Don't touch unrelated files.** Even import reorders, whitespace
   normalization, or a "tiny" refactor in an adjacent function are
   forbidden. Each commit reflects exactly one task.
3. **Run feature-relevant checks, not the world.** Constitution §4.3 —
   the bar per implement is "tests relevant to the changed feature pass,
   plus the cheap deterministic eval tier when the task touches
   chunking/retrieval/agent/tools." The task lists those checks. If they
   don't exist yet, you write them as part of this task.
4. **Checks must actually run.** Don't claim a test or eval check passes
   without running it. If you can't run it locally (e.g. it needs Qdrant
   up, the DuckDB facts built, or a cloud LLM key), flag that as a
   precondition and ask the user.
5. **Deliver the Code Walkthrough.** Before you propose the commit, you
   produce the two-level walkthrough (see "The Reporting Protocol"
   below). A task whose code is written but whose walkthrough is missing
   is NOT done (Constitution §2 / §6.5).
6. **Commit at the end, with approval.** Propose the commit message,
   show the staged files and diff scope, and WAIT for the user's "yes."
   Never commit without confirmation. Never push. Pushing is the user's
   job.
7. **STOP after one task.** Do not start the next task. Even if it
   looks easy. Even if the user said `/implement` without a task ID and
   you defaulted to T1 — you do T1 only.

## The single-repo commit rule (deliberate divergence from RFI)

This is an intentional difference from the sibling RFI project. **State
it explicitly so no one ports RFI's two-repo habit here.**

- In RFI, application code lives in a *child* repo and the SDD artifacts
  live in the *parent* repo. So RFI's `/implement` commits the code in
  the child repo and leaves `tasks.md` / `spec.md` **uncommitted** in the
  parent for the user to commit later.
- **AuditAgent is ONE repo.** Code in `src/` and SDD artifacts in
  `specs/` live together. That split does not exist here.

**RULE for AuditAgent:** the `/implement` commit is a single atomic
"task done" commit that includes:
- the CODE change (the files in the task's `Files:` list), AND
- the `tasks.md` edit (checkbox `[x]` + the dated outcome line), AND
- the `spec.md` frontmatter `status` bump (if it changed this task),

ending with the `Spec: <id>` footer. After the commit the working tree
is clean. (Everything else stands: propose the message, show the staged
files and diff size, WAIT for user approval, never push.)

## Required reads (before any code changes)

1. `specs/<dated-slug>/spec.md` — for acceptance criteria.
2. `specs/<dated-slug>/plan.md` — for approach and risks.
3. `specs/<dated-slug>/tasks.md` — for the task description, files,
   and acceptance check.
4. The files the task names, under `src/`.
5. Adjacent code to understand the local conventions, and
   `docs/architecture.md` §3/§5 for the module's role and the contracts
   it touches (you will need this for the walkthrough).

## Process

1. **Confirm the task** — restate the task ID, summary, files, and
   acceptance check back to the user in 4 lines. This is your last
   chance to surface a misunderstanding before changing code.
2. **Make the change.** Stay inside the named files. If the change
   genuinely requires touching a file not in the task's `Files:`
   list, surface it before editing — that's a sign the task should
   be split or the plan amended.
3. **Run the acceptance check.** Run the named unit test (`python -m
   pytest <path>`), capture pass/fail and output verbatim. If the task
   touches chunking/retrieval/agent/tools, ALSO run the named cheap
   deterministic eval check (exact-match numeric vs XBRL, or retrieval
   hit@k on the small fixed set — §4.3). Any heavy LLM-judge /
   re-embedding run named by the plan is NOTED as queued, not run here.
   (UI manual verification is N/A until M9.)
4. **Produce the Code Walkthrough** (Reporting Protocol — see below).
   This is a required step, not an optional nicety.
5. **Update `tasks.md`** — mark the task `[x]` and append a one-line
   note: `done <YYYY-MM-DD>: <brief outcome>`. If the task uncovered a
   follow-up, add it to a "Discovered work" section at the bottom of
   `tasks.md` rather than handling it now.
6. **Update spec frontmatter** — bump `status` to `implement` if it was
   `tasks`. (Stays at `implement` for subsequent tasks.)
7. **Propose a commit message.** Format:

   ```
   <Imperative summary under 70 chars>

   <Optional 2-4 line body explaining why, not what.>

   Spec: <YYYY-MM-DD-slug>
   ```

   Show the user:
   - the proposed message,
   - the list of staged file paths (code + `tasks.md` + `spec.md`),
   - the size of the diff (lines added/removed).

8. **Wait for approval.** The user says "commit" or "yes." Then make the
   single atomic commit (code + `tasks.md` + `spec.md`) with the
   proposed message. If the user requests edits to the message, apply
   and re-confirm before committing.
9. **Report and STOP.** Final message: which task is done, which check
   ran with what outcome, the Code Walkthrough, what the next task ID
   is, and that you are stopping.

## The Reporting Protocol (mandatory — Constitution §2)

Every `/implement` task MUST end with a **Code Walkthrough** at two
granularities. This is the project's defining process addition: the lead
must be able to re-present every line, top-down, at any altitude.

- **Module level** — name which module (per `docs/architecture.md` §3
  layer map) the task belongs to, its role and where it sits in the data
  flow (§4), and what changed at the module boundary: the inputs,
  outputs, contracts, and dependencies. Reference the typed contracts in
  §5 by name (Element, XBRLFact, Chunk, RetrievedContext, AgentState,
  Citation, TelemetryEvent) when the change touches one.
- **File level** — for each file and function touched: what it does and
  WHY it exists, in plain language the lead can re-present top-down to
  line level. Not a diff dump — an explanation.

The walkthrough is delivered IN the `/implement` response. Its substance
is captured later in the spec's `evaluate.md` when the spec closes. A
task without its walkthrough is not done.

## Forbidden actions

- **Touching unrelated files.** Period.
- **Declaring a task done without the Code Walkthrough.** The
  walkthrough is part of "done" (Constitution §2 / §6.5). Code committed
  without it is an incomplete task — do not skip it, do not defer it.
- **Auto-pushing.** `/implement` never runs `git push`. The user pushes
  when they're ready.
- **Skipping checks.** Even if the task is "obviously" correct. The
  acceptance check (and the cheap-eval tier where applicable) is gospel.
- **Multi-task invocations.** You finish T1, you stop. If the user
  wants T2, they invoke `/implement T2`.
- **Bypassing approval.** No `git commit` until the user has explicitly
  approved the message.
- **Force pushes, hard resets, branch deletions, history rewrites,
  --no-verify, --no-gpg-sign** — all forbidden. The Constitution and the
  global git-safety rules apply.
- **Hiding check failures.** If the test or eval check fails, report it,
  leave the task `[ ]`, and stop. Do not "loop back and try again
  silently." The user decides whether to amend the plan, debug, or
  abandon.
- **Skipping the `Spec:` footer.** Every commit produced by `/implement`
  ends with `Spec: <id>` — this is the spec-linkage mechanism (AGENTS.md
  "Commit format").

## On check failures

If the feature-relevant test OR the cheap-eval check fails:

1. Report the failure verbatim (output, line numbers, the metric and
   its baseline if it's an eval regression).
2. Do NOT auto-debug aggressively. Briefly diagnose (one or two
   targeted hypotheses), but do not start making speculative changes.
3. Tell the user the task is NOT done, leave the checkbox `[ ]`, and
   stop.
4. Three options for the user:
   - Refine the implementation (continue the task).
   - Refine the plan (loop back to PLAN — failures sometimes mean the
     design was wrong, not the code).
   - Abandon the task and amend the spec.

A cheap-eval **regression** against the committed baseline in
`eval/baselines/` is a fail, not a "close enough" — surface it (§4.2).

## Boundary decisions for this codebase specifically

These are the recurring fidelity / architecture judgment calls; apply
them deterministically and FAIL CLOSED when they trip:

- **Layer separation (§1.6).** A task must not introduce an *upward*
  import — e.g. `retrieval/` importing `agent/`, or `index/` importing
  `retrieval/`. Imports flow downward only. If the task seems to need
  one, the task or the plan is wrong: surface and stop.
- **The validator gate (§1.4).** A task touching the agent graph must
  NOT let the LLM route around the validator/critic edge. The validator
  is a non-skippable edge, not a tool the model may choose. Any path that
  emits a user-visible financial claim must route through (or replicate)
  it. Removing or bypassing it is a constitution-level change — surface
  it, do not implement it under a feature task.
- **Numbers from XBRL (§1.2).** A calc/numeric task reads figures from
  the DuckDB XBRL fact store; it never transcribes a number from a
  parsed table or prose, and it never has the LLM do arithmetic. If the
  task as written asks for LLM transcription or LLM arithmetic on
  figures, fail closed and surface — the plan should have routed the math
  through the deterministic calc tool.
- **Citations (§1.5).** A task that produces a user-visible claim
  without attaching a Citation (narrative tuple or `xbrl_fact_id`) is
  incomplete: no citation → no claim.
- **Settings (§1.7).** New configuration is read through
  `config.settings`, never `os.getenv` in business code. If the task
  needs a new value, it goes through settings.
- **Secrets (§5.1).** No committed `.env` or secret in a tracked file.
  If the task requires a NEW secret, that is a precondition fail — the
  plan should have routed it through the environment / `.env.example`
  (names only). Surface and stop.
- **New dependency (§3).** A new library must have been named in the
  plan's Risks before being added. If the task needs an un-named
  dependency, stop and ask — don't silently `pip install` and import it.
- **New top-level `src/` module (§1.6 / §3).** Needs a spec. If the task
  appears to require one, surface it; do not invent the module.

## On scope creep temptations

| Temptation | What to do |
|---|---|
| "This adjacent function has the same bug." | Note it in a "Discovered work" section in tasks.md. Don't fix here. |
| "The naming here is awkward." | Note it. Don't rename here. |
| "There's no test for this neighboring code." | Note it. Don't add here. |
| "While I'm here, let me update the dependency." | Don't. That's its own spec. |
| "I'll just clean up these imports." | Don't. |
| "I could fold the figure straight from the parsed table." | Don't — numbers come from XBRL (§1.2). |

If a temptation is so load-bearing that you can't complete the task
without yielding to it, the task itself is wrong — STOP and tell the
user the task should be split or the plan amended.

## Version control interaction

- **Reads** git state to understand the working tree before changing
  files. If the working tree isn't clean, ASK the user — don't blindly
  add to whatever they had pending.
- **Writes** code in the named module under `src/`, plus `tasks.md` and
  `spec.md` (status field).
- **Commits** ONE atomic "task done" commit (code + `tasks.md` +
  `spec.md`) with the user-approved message including the `Spec: <id>`
  footer. Working tree clean afterward. Never pushes.
- **Never** runs destructive git commands. If you encounter a merge
  conflict or detached HEAD, stop and surface it.

## End-of-task report format

```
✓ Task T<N> done
   Spec: <id>
   Module: <ingestion | chunking | index | retrieval | agent | api | eval | config>
   Files changed: <count>, +<added> -<removed>  (code + tasks.md + spec.md)
   Check: <path::class::method> — <pass | fail>
   Eval (if applicable): <cheap-tier check> — <pass | fail>; heavy tier: <queued | n/a>
   Commit: <hash> "<summary>"

— Code Walkthrough —
Module level: <module, role, data-flow position, boundary change vs §5 contracts>
File level:
  <file>::<fn> — <what it does and why it exists>
  <file>::<fn> — ...

Next: T<N+1> (run /implement T<N+1>)
Stopping.
```

Do not auto-continue.
