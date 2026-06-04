# /tasks — TASKS stage

You are running the TASKS stage. The plan has been confirmed. Your job
is to decompose the plan into an ordered, PR-sized checklist and write
`tasks.md`.

## When to use

After the user has confirmed `specs/<dated-slug>/plan.md` and said
"tasks" or `/tasks`. Verify before writing:

- The plan exists at `specs/<dated-slug>/plan.md`.
- The spec's frontmatter `status` field reads `plan`.
- The user has explicitly confirmed the plan.
- Outstanding `spec-reviewer` findings on the plan are resolved.

If any precondition fails, ASK the user instead of writing.

## Required reads

1. **`specs/<dated-slug>/plan.md`** — the source of truth for what
   needs to happen.
2. **`specs/<dated-slug>/spec.md`** — for acceptance criteria mapping.
3. **`docs/constitution.md` §4 (Testing & Evaluation)** — to ensure each
   task carries its feature-relevant test, and that retrieval/agent/
   chunking tasks carry their cheap-eval check and any golden-set entry.

## File written

```
specs/<dated-slug>/tasks.md
```

Plus an in-place edit to the spec's frontmatter:
```yaml
status: tasks       # was: plan
```

## Task design rules (read carefully — these are load-bearing)

1. **PR-sized.** Each task should land in under ~2 hours of focused work.
   Larger = split. If you can't see how to split, surface it as an Open
   Question and pause.
2. **Independently testable.** Each task names ONE acceptance check —
   either a specific test (`tests/...::Class::method`) or a cheap-eval
   check (exact-match numeric vs XBRL, retrieval hit@k on the fixed set).
   The check must be decisive: it passes or it doesn't.
3. **One concern per task.** A task does not bundle a refactor with a
   feature, or a test fix with a behavior change, or a chunking change
   with a retrieval change. If something needs both, it's two tasks
   linked by ordering. (There is ONE repo — concern-splitting is by
   module/layer, not by repo.)
4. **Module-scoped.** Each task names files within ONE module/layer of
   `src/` where practical (`ingestion`, `chunking`, `index`, `retrieval`,
   `agent`, `api`, `eval`, `config`). A task that legitimately spans two
   layers carries the justifying note from the plan (§1.6).
5. **Ordered.** The list is sequential. A task depends only on tasks
   above it. If two tasks are truly parallel-safe, mark them
   `[parallel-with N]`.
6. **Files named.** Each task lists the file paths it expects to
   touch. Best guess is fine; the implementer will refine. "Unknown"
   is a smell — go read the code.
7. **Tests included.** A task that adds behavior includes (in the same
   task) the test that proves it. Tests aren't a separate task — they
   ride with the change. For retrieval/agent/chunking behavior the test
   includes the golden-set entry (§4.4). Exception: pre-existing failing
   tests get their own preparatory task at the top.

## tasks.md template

```markdown
---
spec: <YYYY-MM-DD-slug>
status: tasks
created: <YYYY-MM-DD>
---

# Tasks: <spec title>

## Pre-flight (if needed)

- [ ] T0. <preparatory work — e.g. "Branch off the trunk as
      spec/<slug>", or "Confirm test env — run `python -m pytest
      tests/unit -q`, capture baseline", or "Capture the current eval
      baseline for the affected metric from eval/baselines/">
      Files: <list>
      Acceptance: <one-line>

## Tasks

- [ ] T1. <imperative task name>
      Files: src/retrieval/<file>.py, tests/unit/test_<file>.py
      Acceptance: tests/unit/test_<file>.py::TestX::test_y passes
      Notes: <optional — any context the implementer needs>

- [ ] T2. <next task>
      Files: src/agent/tools/<file>.py, src/eval/golden/<entry>.json
      Acceptance: cheap-eval — exact-match numeric vs XBRL for
                  <question> passes (deterministic tier, §4.3); golden
                  entry <id> added.
      Depends-on: T1

- [ ] T3. <task>
      ...
```

Use `Depends-on:` only when ordering matters. The default reading is
"sequential."

If a task needs new test or eval infrastructure (e.g. a new
`tests/integration/` folder, or a new golden-set fixture file), make
that infrastructure its own preparatory task.

## Sizing self-check

Before finalizing, walk the list and ask:

- Is any task more than 2 hours? Split.
- Is any task less than 15 minutes AND not preparatory? Combine with a
  neighbor.
- Could a teammate pick up any task and finish it from `tasks.md`
  alone, without re-deriving the plan? If not, add a `Notes:` line.
- Does a retrieval/agent/chunking task carry both its unit test AND its
  cheap-eval check / golden-set entry?
- Does the last task's acceptance check correspond to ALL of the
  spec's Acceptance Criteria being satisfied? If not, what's missing?

## Forbidden actions

- **Bundling concerns.** A "fix the filter and add the rerank" task is
  two tasks. Split.
- **Editing source code.** Do not touch any file under `src/` other than
  reading it.
- **Auto-advance.** When `tasks.md` is written, STOP. Do not invoke
  `/implement` unprompted.
- **Hand-waving acceptance.** "Looks right" is not an acceptance
  check. Every task names a test or a cheap-eval check.
- **Ignoring tests.** A task that adds behavior without a corresponding
  test (and, for retrieval/agent behavior, a golden-set entry) is
  rejected. State it as such if you can't see how to test it, and ask
  the user — that's an Open Question.

## Version control interaction

- Writes only under `specs/<slug>/tasks.md`, plus an in-place status
  bump to `spec.md`'s frontmatter.
- No git commits.
- No interaction with `src/` git state — only reads files.

## End-of-stage rules

When `tasks.md` is written:

1. Show the user the task list with task IDs and one-line summaries.
2. Flag any task that's borderline-large or whose acceptance check is
   weak.
3. Tell the user the next step is `/implement T1` (or whichever task
   ID is first) and that you will NOT auto-invoke it.
4. Stop.

Status bumps from `tasks` to `implement` happen on the FIRST
`/implement` invocation, not now.
