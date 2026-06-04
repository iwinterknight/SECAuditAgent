---
description: EVALUATE stage. Walk the checklist (Acceptance Criteria, Tests, Eval-regression gate, Constitution, Documentation, Reporting Protocol, Spec hygiene, Next-engineer pass) for a spec whose tasks are all done. Writes specs/<slug>/evaluate.md and on PASS bumps the spec to "done". On FAIL surfaces four loop-back options (refine impl / refine plan / refine spec / abandon).
argument-hint: <spec-slug e.g. 2026-06-10-table-to-text-summaries>
---

Follow the instructions in `.agent/commands/evaluate.md`.

The user has provided the spec slug as an argument: $ARGUMENTS.

If $ARGUMENTS is empty, resolve to the most recently-modified spec
folder under `specs/` whose status is `implement` (i.e. all tasks
done, awaiting evaluate). If multiple are eligible, ask the user
which to evaluate.
