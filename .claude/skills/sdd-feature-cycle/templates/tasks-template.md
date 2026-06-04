---
spec: <YYYY-MM-DD-slug>
status: tasks
created: <YYYY-MM-DD>
---

# Tasks: <spec title>

## Pre-flight (if needed)

Use this section for setup work that doesn't itself implement the spec
but must happen before T1 — e.g. branching, baseline test/eval runs,
infrastructure scaffolding.

- [ ] T0. <preparatory work>
      Files: <list>
      Acceptance: <one-line>
      Notes: <optional>

## Tasks

Each task: PR-sized (under ~2 hours), independently testable, one
concern per task, named files under `src/`, named acceptance check
(a Python test path OR a cheap-eval check).

- [ ] T1. <imperative task name — start with a verb>
      Files:
        - src/<module>/<file>.py
        - tests/unit/test_<file>.py
      Acceptance: tests/unit/test_<file>.py::TestX::test_y passes
      Notes: <optional context for the implementer>

- [ ] T2. <next task>
      Files:
        - src/<module>/<file>.py
        - src/eval/golden/<entry>.json
      Acceptance: cheap-eval — exact-match numeric vs XBRL for
                  <question> passes (deterministic tier, §4.3);
                  golden entry <id> added.
      Depends-on: T1

- [ ] T3. <task>
      Files:
        - src/<module>/<file>.py
      Acceptance: cheap-eval — retrieval hit@k on the small fixed set
                  passes (§4.3).
      Depends-on: T2

<!-- Continue numbering. Tasks that legitimately span two layers carry
     the justifying note from the plan (§1.6). One concern per task. -->

## Discovered work

Append items found during IMPLEMENT that weren't in the original plan.
Do not act on these without going back through PLAN — they may or may
not belong in this spec. Each item dated.

- <YYYY-MM-DD>: <discovered item> — <handled now | follow-up spec needed | TBD>

<!--
Sizing self-check before finalizing:
  - Any task > 2h? Split.
  - Any task < 15 min and not preparatory? Combine.
  - Could a teammate finish each task from this list alone, without
    re-deriving the plan? If not, add Notes.
  - Does a retrieval/agent/chunking task carry both its unit test AND
    its cheap-eval check / golden-set entry?
  - Does the last task's acceptance check correspond to ALL of the
    spec's Acceptance Criteria being satisfied?

Status transitions:
  - tasks → implement: bumped on first /implement invocation.
  - implement → done: bumped after EVALUATE passes.
-->
