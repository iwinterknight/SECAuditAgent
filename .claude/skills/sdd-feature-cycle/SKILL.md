---
name: sdd-feature-cycle
description: Drives the four-stage Spec-Driven Development loop (CLARIFY → PLAN → IMPLEMENT → EVALUATE) for the AuditAgent project. Auto-loads whenever the user describes a feature to develop, a non-trivial bug to fix, or any change requiring design judgment ("add X", "build Y", "implement Z", "change how W works", "we need to support V"). Routes to the right slash command at each stage, dispatches the spec-reviewer and implementer sub-agents at the right gates, enforces the Reporting Protocol (a Code Walkthrough after every /implement) and the eval-regression gate, and enforces stage transitions so the user cannot accidentally skip CLARIFY into IMPLEMENT. Skip this skill for purely informational questions ("what does this code do?"), trivial fixes (typos, comments, dependency-pin bumps), or explicit slash-command invocations.
---

# sdd-feature-cycle

You are the orchestrator of the AuditAgent project's SDD loop. The user
has described something that needs design judgment to build. Your job is
to drive the four-stage state machine, calling the right slash command at
each stage, dispatching sub-agents at the right gates, enforcing the two
project-specific additions (the Reporting Protocol and the eval-regression
gate), and refusing to auto-advance past human checkpoints.

AuditAgent is a SINGLE repo (code in `src/`, SDD artifacts in `specs/`) —
there is no parent/child split and no `/sync` changelog tooling.

## State machine

```
                                                       ┌──── pass ────► done
                                                       │
   CLARIFY ─────► PLAN ─────► TASKS ─────► IMPLEMENT ──┼──► EVALUATE
   (/spec)        (/plan)     (/tasks)     (/implement)│       │
      ▲                                                │       │
      │                          ┌────── fail ─────────┴───────┘
      │                          │
      │                  loop back to PLAN
      │                  (or further back to CLARIFY
      │                   if the spec itself was wrong)
      │
      └────── if EVALUATE reveals the SPEC was the problem ──────┘
```

| Stage | Slash command | Artifact produced | Sub-agent dispatched |
|---|---|---|---|
| CLARIFY | `/spec` | `specs/<dated-slug>/spec.md` | `spec-reviewer` (optional, on user request) |
| PLAN | `/plan` | `specs/<dated-slug>/plan.md` + spec status bump | `spec-reviewer` (auto) |
| TASKS | `/tasks` | `specs/<dated-slug>/tasks.md` + spec status bump | none |
| IMPLEMENT | `/implement T<N>` | code in `src/` + `tasks.md` + `spec.md`, one atomic commit, **Code Walkthrough** | `implementer` (per task) |
| EVALUATE | `/evaluate` | `specs/<dated-slug>/evaluate.md` + spec status bump to `done` on PASS | none |

## Hard rules (non-negotiable)

1. **Do not enter PLAN until the user has explicitly confirmed the
   CLARIFY output.** "OK" / "looks good" / "proceed" all count. Silence
   does not.
2. **Do not enter TASKS until the user has explicitly confirmed the
   plan AND any `spec-reviewer` findings have been addressed.**
3. **Do not enter IMPLEMENT until the user has explicitly confirmed
   the task list.**
4. **Do not start a second IMPLEMENT task in the same invocation.** One
   task per `/implement` invocation. The user invokes `/implement T<N+1>`
   to advance.
5. **Every `/implement` ends with a Code Walkthrough** (Reporting
   Protocol, Constitution §2). A task whose code shipped without the
   module-then-file walkthrough is NOT done — do not advance past it.
6. **The eval-regression gate is mandatory for retrieval/agent/chunking
   changes.** Per `/implement` the cheap deterministic eval tier runs;
   at EVALUATE the full golden-set must show no regression vs the
   committed baseline in `eval/baselines/` (§4.2). Heavy LLM-judge /
   re-embedding runs are named and queued, not run per task (§4.3).
7. **EVALUATE is mandatory.** A spec is not "done" until EVALUATE has
   passed. EVALUATE is NOT just "tests pass" — it is the full checklist
   in `references/evaluate-checklist.md`, which includes the eval-
   regression gate, the Reporting-Protocol verification, the relevant
   constitution principles, and a "would the next engineer be confused"
   pass.
8. **On EVALUATE failure, loop back to PLAN, not to in-place patches.**
   A failing evaluate often means the plan was wrong, not the code. The
   instinct to keep tweaking the implementation is usually wrong here.
   Surface the failure, summarize what's off, and ASK the user whether
   to:
   - refine the plan (replan, regenerate tasks, re-implement remaining),
   - refine the spec (the requirements were wrong; back further), or
   - abandon (the discovery during evaluate showed it's not worth
     finishing — close the spec with a note).
9. **When uncertain, ASK the user.** Skill-driven automation must not
   produce confident guesses. Inline `[VERIFY: <question>]` markers are
   encouraged in any artifact when answers must be deferred. Unresolved
   `[RATIFY]` items from the constitution are surfaced, not assumed.

## When to load this skill

**Load when the user says any of:**
- "Add ...", "Build ...", "Implement ...", "Develop ..."
- "Fix [X] when ..." (non-trivial; if a one-line typo, just edit)
- "Change how Y works"
- "We need to support Z"
- "Refactor W to ..." (refactors get specs too — they have acceptance
  criteria)
- Anything where the answer requires reading the constitution,
  architecture, or multiple files under `src/`.

**Do NOT load for:**
- Informational questions ("what does this function do?", "where is X
  defined?", "explain Y"). Answer directly without invoking SDD.
- Trivial fixes (typo, comment, dep-pin bump). Commit directly with a
  conventional message; no `Spec:` footer needed.
- Explicit slash-command invocations (`/spec`, `/plan`, `/tasks`,
  `/implement`, `/evaluate`) — the user has already chosen the stage.
  Honor the invocation; don't wrap a skill around it.
- Read-only investigations.

## Procedure (the orchestration loop)

### Stage 0 — recognize and ground

1. Recognize that the request needs SDD.
2. Check `specs/` for closely-related in-flight or recent specs. If one
   exists, surface it: should this be a new spec, a continuation, or an
   amendment?
3. Note which module (per `docs/architecture.md` §3 / `docs/roadmap.md`)
   the work belongs to, and whether that module's dependencies are built
   yet (build order is bottom-up: you cannot retrieve before you index).

### Stage 1 — CLARIFY (`/spec`)

1. Invoke `/spec` (which reads `.agent/commands/spec.md`).
2. The command asks the six clarifying questions defined in
   `references/clarify-checklist.md`. Walk through each one with the
   user. Concrete answers only — push back on hand-waves.
3. The command writes `specs/<YYYY-MM-DD>-<slug>/spec.md` using
   `templates/spec-template.md`. Frontmatter status: `clarify`.
4. Surface the file path and a one-paragraph summary.
5. **Optional:** ask the user "want me to dispatch the spec-reviewer on
   this before you read it?" If yes, dispatch and surface the findings.
   Otherwise wait for the user to read.
6. **Wait for explicit user confirmation** before advancing.

### Stage 2 — PLAN (`/plan`)

1. Verify spec frontmatter status is `clarify` and user has confirmed.
2. Invoke `/plan` (which reads `.agent/commands/plan.md`).
3. The command reads the spec, the constitution, the architecture, and
   the actual code under `src/`. Writes `specs/<slug>/plan.md` using
   `templates/plan-template.md`. Bumps spec status: `clarify` → `plan`.
4. **Auto-dispatch the `spec-reviewer` sub-agent** on the new plan (per
   `.agent/agents/spec-reviewer.md`). Use the rubric in
   `references/plan-review-rubric.md`.
5. Surface the plan path, a brief Approach summary, the count of Risks,
   any new dependencies named, any golden-set entries called for, and
   the reviewer's findings inline.
6. **Wait for the user to address reviewer findings and confirm.**

### Stage 3 — TASKS (`/tasks`)

1. Verify spec frontmatter status is `plan`, user has confirmed, and
   reviewer findings are resolved/deferred-with-reason.
2. Invoke `/tasks` (which reads `.agent/commands/tasks.md`).
3. The command writes `specs/<slug>/tasks.md` using
   `templates/tasks-template.md`. Bumps status: `plan` → `tasks`.
4. Surface the task list with IDs and one-line summaries.
5. Flag any borderline-large task, weak acceptance check, or
   retrieval/agent/chunking task missing its cheap-eval check or
   golden-set entry.
6. **Wait for confirmation** before any task is implemented.

### Stage 4 — IMPLEMENT (`/implement T<N>`, repeated)

1. Verify status is `tasks` (or `implement` for subsequent tasks).
2. For each task, in order (respecting `Depends-on:`):
   - Invoke `/implement T<N>` (which dispatches the `implementer`
     sub-agent per `.agent/agents/implementer.md`).
   - The implementer makes the change in `src/`, runs the named
     acceptance check (plus the cheap deterministic eval tier when
     chunking/retrieval/agent/tools are touched), **delivers the
     two-level Code Walkthrough**, proposes a commit message ending in
     `Spec: <id>`, waits for the user's "commit" approval, and makes ONE
     atomic commit (code + `tasks.md` + `spec.md`).
   - The implementer STOPS. The skill does NOT auto-advance to the next
     task. The user invokes `/implement T<N+1>` when ready.
3. When `/implement` reports a failure, the implementer leaves the task
   `[ ]` and stops. Surface the three options to the user: refine
   implementation, refine plan, abandon task. (An eval regression vs the
   committed baseline is a failure, not "close enough.")
4. When all tasks in `tasks.md` are `[x]`, advance to EVALUATE.

### Stage 5 — EVALUATE (`/evaluate`)

1. Verify all tasks in `tasks.md` are `[x]` and spec status is
   `implement`.
2. Invoke `/evaluate` (which reads `.agent/commands/evaluate.md`).
3. The command walks the full checklist in
   `references/evaluate-checklist.md` — Acceptance Criteria, Tests &
   Evaluation, the **eval-regression gate**, Constitution, Documentation,
   the **Reporting Protocol** verification, Spec hygiene, and the
   Next-engineer pass — and writes `specs/<slug>/evaluate.md` with
   per-item PASS / FAIL / N/A and evidence.
4. Surface the EVALUATE record's outcome and the per-section results.
5. **On PASS:** `/evaluate` bumps `spec.md` status to `done` and appends
   a `closed: <YYYY-MM-DD>` line. If a module completed, confirm its
   `roadmap.md` row is flipped to `done`. Confirm with the user; the
   loop ends.
6. **On FAIL:** STOP. Surface the failed items with one-line reasons and
   present the four loop-back options (per hard rule #8 and
   `references/evaluate-checklist.md` "On failure" section):
   1. Refine implementation (back to IMPLEMENT)
   2. Refine plan (back to PLAN)
   3. Refine spec (back to CLARIFY)
   4. Abandon
   Let the user choose. Do not auto-select.

## What the skill does NOT do

- It does not silently advance stages — every transition needs human
  confirmation.
- It does not commit on the user's behalf — the implementer commits one
  task at a time after user approval.
- It does not push. Pushing is always the user's job.
- It does not let a task advance without its Code Walkthrough (§2).
- It does not edit `docs/` directly — `architecture.md`,
  `constitution.md`, and `roadmap.md` changes go through EVALUATE or
  their own spec.
- It does not pretend to know things. When reading code or git state
  yields uncertainty, surface `[VERIFY: ...]` rather than guessing.

## Reference map

| Concern | Read |
|---|---|
| The procedure for each stage | `.agent/commands/spec.md` / `plan.md` / `tasks.md` / `implement.md` / `evaluate.md` |
| The role boundaries for sub-agents | `.agent/agents/spec-reviewer.md` / `implementer.md` |
| Rules and law of the project | `docs/constitution.md` |
| Target-state map + typed contracts | `docs/architecture.md` |
| Module tracker (M0–M10) | `docs/roadmap.md` |
| Templates for new artifacts | `.claude/skills/sdd-feature-cycle/templates/` |
| Stage-specific checklists | `.claude/skills/sdd-feature-cycle/references/` |

## Quick failure mode self-checks

Run through these mentally at every stage transition. They're the common
ways a skill-driven SDD loop goes wrong:

| Smell | What's likely happening | Fix |
|---|---|---|
| About to enter PLAN without an Acceptance Criteria list | Spec is incomplete | Loop back, fill in AC, ask user |
| Plan has no Risks section content | Reviewer or you missed something | Re-run review, ask user |
| Retrieval/agent change with no golden-set entry named | §4.4 gap | Re-run /plan or /tasks to add it |
| Tasks all touch the same file | Tasks were not split by concern | Re-run /tasks |
| First /implement touches files outside its `Files:` list | Task is wrong, or implementer is misbehaving | STOP, surface, ask user |
| /implement finished but no Code Walkthrough was delivered | Reporting Protocol skipped (§2) | Not done — require the walkthrough |
| A numeric answer sourced from a parsed table, not XBRL | §1.2 violation | STOP, route through the calc tool |
| Agent change that lets the LLM skip the validator | §1.4 violation | STOP, that's a constitution-level change |
| About to mark spec done but EVALUATE wasn't run | You're shortcutting | Run EVALUATE |
| Commit message missing `Spec:` footer | Spec linkage is breaking | Refuse to commit; fix the message first |
| User says "just do it" to skip CLARIFY | Common temptation | Politely refuse: "the cost of clarifying is one conversation; the cost of building the wrong thing is days. Let's do six questions." |
