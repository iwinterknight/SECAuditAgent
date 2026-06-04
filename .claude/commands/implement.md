---
description: IMPLEMENT one task. Dispatches the implementer sub-agent to make the change in the single repo, run the named acceptance check (+ cheap-eval tier), deliver the Code Walkthrough, propose a commit message ending with Spec:<id>, wait for user approval, commit atomically (code + tasks.md + spec.md), then STOP. Never pushes. Never bundles tasks.
argument-hint: <task-id e.g. T1>
---

Follow the instructions in `.agent/commands/implement.md`.

The user has provided the task ID as an argument: $ARGUMENTS.

If $ARGUMENTS is empty or the literal text "next", resolve to the
first unchecked task in the active spec's `tasks.md` (respecting
`Depends-on:`).
