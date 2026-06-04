# /evaluate — EVALUATE stage (the gate before "done")

You are running the EVALUATE stage. All tasks in `tasks.md` are checked.
Your job is to walk the evaluate checklist, record the outcome, and
either bump the spec to `done` OR surface the failure with four
explicit options for the user to choose.

EVALUATE is NOT just "tests pass." Per Constitution §6 (Definition of
Done — eight items), a spec is not done until every checklist item is
verified, including the **eval-regression gate** for retrieval/agent/
chunking changes and the **Code Walkthrough** for every implemented task.

## When to use

- `/evaluate <YYYY-MM-DD-slug>` — the user names the spec to evaluate.
- `/evaluate` (no arg) — the active spec, if obvious from context.
- Re-evaluation: `/evaluate <slug>` against a previously-done spec
  (audit, regression, post-mortem). Allowed and useful.

Verify before walking:

- The spec folder exists at `specs/<slug>/`.
- `tasks.md` exists and every task is `[x]` (or has a one-line note
  explaining a dropped task).
- The spec frontmatter `status` is `implement` (normal case) or
  `done` (re-evaluation case).

If preconditions fail (tasks still `[ ]`, status `clarify`/`plan`),
ASK the user — don't EVALUATE half-done work.

## Required reads

1. **`specs/<slug>/spec.md`** — for Acceptance Criteria.
2. **`specs/<slug>/plan.md`** — for the Risks (constitution sections
   the plan named), the Test Strategy (named test paths / cheap-eval
   checks / golden-set entries), and the eval-baseline impact it
   declared.
3. **`specs/<slug>/tasks.md`** — to verify every task is `[x]` and any
   "Discovered work" was handled.
4. **`.claude/skills/sdd-feature-cycle/references/evaluate-checklist.md`**
   — the canonical checklist this command walks. It enumerates the
   specific items in each section and the prescribed output format.
5. **`docs/constitution.md`** — every principle the plan named, plus any
   others the implementation actually touched.
6. **The diff** for this spec, on the single trunk:
   `git log -G "Spec: <slug>"` (or `git log --grep="Spec: <slug>"`).
   There is ONE repo and ONE trunk — no parent/child or origin/dev vs
   origin/main split.

## File written

```
specs/<slug>/evaluate.md
```

If the file already exists (re-evaluation), append a new dated run
rather than overwriting. The history of evaluations is itself
auditable.

Plus an in-place edit to the spec's frontmatter:
- On PASS: `status: implement` → `status: done`, append `closed:
  <YYYY-MM-DD>`.
- On FAIL: `status` stays where it was. Append a `last-evaluate:
  <YYYY-MM-DD>` line.

## evaluate.md template

```markdown
---
spec: <YYYY-MM-DD-slug>
type: evaluate-record
created: <YYYY-MM-DD>
---

# EVALUATE — <YYYY-MM-DD>

## Section A — Acceptance Criteria
| # | Item | Result | Evidence / Note |
|---|---|---|---|
| A.1 | Every AC maps to an entry below | PASS / FAIL | ... |
| A.2 | Each AC verified via plan's named test/check | PASS / FAIL | ... |
| A.3 | No AC silently dropped | PASS / FAIL | ... |

(then a per-AC table)
| AC | Description | Result | Evidence |
|---|---|---|---|
| AC1 | <from spec.md> | PASS | <test path or cheap-eval observation> |
| AC2 | <from spec.md> | PASS | ... |

## Section B — Tests & Evaluation
| # | Item | Result | Evidence |
|---|---|---|---|
| B.1 | Feature-relevant unit tests pass | PASS / FAIL | <command + summary> |
| B.2 | Cheap deterministic eval tier passes (if retrieval/agent/chunking touched) | PASS / FAIL / N/A | <numeric-vs-XBRL, hit@k> |
| B.3 | Heavy eval tier (LLM-judge / re-embedding) named + queued | NOTED / N/A | <list> |
| B.4 | Tests + golden-set entries required by plan exist now | PASS / FAIL | <list new tests/entries> |
| B.5 | No tests or golden entries disabled to make it green | PASS / FAIL | — |

## Section C — Evaluation regression gate (retrieval / agent / chunking)
| # | Item | Result | Evidence |
|---|---|---|---|
| C.1 | Full golden-set eval shows NO regression vs the last committed baseline in `eval/baselines/` (RAG triad + agent-loop metrics) | PASS / FAIL / N/A | <metric-by-metric vs baseline> |
| C.2 | Any intended baseline movement is an improvement, recorded, and the baseline updated deliberately | PASS / N/A | <which metric, why> |
| C.3 | No silent-failure signal regressed (groundedness floor, max-iter loops) | PASS / N/A | — |

(N/A only if the change does not touch retrieval, the agent graph,
chunking, or a tool. Say so with a one-line reason.)

## Section D — Constitution
| # | Principle | Result | Evidence |
|---|---|---|---|
| D.§1.1 | Financial fidelity | PASS / TENSION / VIOLATE | — |
| D.§1.2 | Numbers from XBRL, not LLM transcription | PASS / N/A | — |
| D.§1.3 | Entity & period disambiguation | PASS / N/A | — |
| D.§1.4 | Validator is a non-skippable gate | PASS / N/A | — |
| D.§1.5 | Every claim cited | PASS / N/A | — |
| D.§1.6 | Layer separation (downward imports only) | PASS / N/A | — |
| D.§1.7 | Config via config.settings | PASS / N/A | — |
| D.§5.1 | Secrets clean (no committed .env) | PASS / N/A | — |
| D.foot | `Spec: <id>` footer on every commit | PASS / FAIL | <git log -G output count> |
(only sections the plan named OR the implementation touched, plus the
footer audit, which is always run)

## Section E — Documentation
| # | Item | Result | Evidence |
|---|---|---|---|
| E.1 | architecture.md updated if a module boundary / contract changed | PASS / N/A | — |
| E.2 | constitution.md updated if a principle changed (via its own spec) | PASS / N/A | — |
| E.3 | roadmap.md module status flipped to `done` if a module completed | PASS / N/A | — |
| E.4 | Summary states explicitly which docs changed | PASS / N/A | — |

## Section F — Reporting Protocol (Constitution §2 / §6.5)
| # | Item | Result | Evidence |
|---|---|---|---|
| F.1 | A Code Walkthrough was delivered for EVERY implemented task | PASS / FAIL | <which tasks> |
| F.2 | Walkthrough substance captured here (module-then-file) | PASS / FAIL | <summary below> |

(Capture the module-then-file walkthrough substance for the spec as a
whole, so this record is the durable artifact of what was built and why.)

## Section G — Spec folder hygiene
| # | Item | Result | Evidence |
|---|---|---|---|
| G.1 | tasks.md all [x] | PASS / FAIL | — |
| G.2 | Discovered work handled or moved | PASS / FAIL | — |
| G.3 | Open Questions resolved | PASS / FAIL | — |
| G.4 | Behavior matches what was built | PASS / AMENDED | — |
| G.5 | Status ready to bump | PASS / FAIL | — |

## Section H — Next-engineer pass
| # | Item | Result | Evidence |
|---|---|---|---|
| H.1 | spec+plan+tasks+evaluate+diff are self-contained | PASS / FAIL | — |
| H.2 | Names match what they do | PASS / FAIL | — |
| H.3 | Comments say WHY, not WHAT | PASS / FAIL | — |
| H.4 | No commented-out code | PASS / FAIL | — |
| H.5 | Logging via logger, not print | PASS / N/A | — |
| H.6 | [RATIFY]/[VERIFY:] markers resolved or carried forward | PASS / FAIL | — |

## Outcome

**Result:** PASS  / FAIL
**Human summary:** <one paragraph>

## On FAIL only — recommended next step

The user picks ONE of:
1. Refine implementation (loop to IMPLEMENT)
2. Refine plan (loop to PLAN)
3. Refine spec (loop to CLARIFY)
4. Abandon
```

## Procedure

1. **Verify preconditions** (see "When to use"). Fail closed on miss.
2. **Read every input** listed in "Required reads."
3. **Walk Section A** — for each AC in spec.md, verify observably. Run
   the test or perform the cheap-eval check named in plan.md. Record
   evidence verbatim.
4. **Walk Section B** — run the tests. For the unit suite, run
   `python -m pytest tests/unit -q` (or the named feature-targeted
   subset). Run the cheap deterministic eval tier if the change touched
   chunking/retrieval/agent/tools. The heavy LLM-judge / re-embedding
   tier is NOTED as queued, not run — it's the pre-merge/scheduled gate.
5. **Walk Section C — the eval-regression gate.** If the change touched
   retrieval, the agent graph, chunking, or a tool, run the full
   golden-set evaluation and compare metric-by-metric against the last
   committed baseline in `eval/baselines/`. Any regression is a FAIL
   (§4.2). An intended improvement requires the baseline to be updated
   deliberately and recorded. If the change touches none of these, mark
   N/A with reason.
6. **Walk Section D** — for each constitution principle named in plan.md
   Risks AND each principle the implementation actually touched (e.g.
   plan didn't mention §1.7 but the implementation reads config — verify
   it goes through `config.settings`; or it produces a claim — verify a
   Citation is attached, §1.5; or it touches the graph — verify the
   validator edge is intact, §1.4). Always run the `git log -G "Spec:
   <id>"` footer audit on the trunk.
7. **Walk Section E** — if a module boundary or a typed contract (§5)
   changed, is `architecture.md` updated? If a principle changed, did it
   go through its own spec and is `constitution.md` updated? If a module
   completed, is its `roadmap.md` row flipped to `done`?
8. **Walk Section F — the Reporting Protocol.** Verify a Code Walkthrough
   was delivered for every implemented task (Constitution §2 / §6.5), and
   capture its module-then-file substance here so this record is durable.
9. **Walk Section G** — tasks.md hygiene, Discovered work disposition,
   Open Questions, spec body consistency.
10. **Walk Section H** — the next-engineer pass. Be honest. Names
    suspiciously generic? Old code commented out instead of deleted?
    `[RATIFY]`/`[VERIFY:]` markers still open?
11. **Compose the evaluate.md record** in the template's format.
12. **Decide outcome.** PASS only if every item is PASS or N/A (with
    reason). Any FAIL → outcome is FAIL.
13. **On PASS:** bump spec.md status `implement` → `done`, append
    `closed: <YYYY-MM-DD>`. If a module completed, remind the user to
    flip its `roadmap.md` row (or confirm it was flipped). Tell the user.
    STOP.
14. **On FAIL:** leave status as-is. Surface the failures with the four
    options (refine impl / refine plan / refine spec / abandon) per
    `references/evaluate-checklist.md` "On failure" section. Let the user
    choose. STOP.

## Forbidden actions

- **Auto-passing on partial evidence.** Every item gets a real result —
  PASS, FAIL, or N/A with reason. "Probably fine" is not an option.
- **Auto-fixing failures.** If Section H.4 fails because there's
  commented-out code in the diff, that's a FAIL — surface it. Don't
  silently delete the code.
- **Silently descoping AC.** If an AC is no longer satisfiable as
  written, you don't get to call it N/A — you call it FAIL, and the user
  decides whether to amend the spec.
- **Skipping the eval-regression gate** (Section C) for a retrieval/
  agent/chunking change. A green unit suite is not sufficient; the
  golden-set baseline comparison is the §4.2 gate.
- **Skipping the Reporting-Protocol check** (Section F). A spec whose
  tasks shipped without walkthroughs is not done (§6.5).
- **Skipping the footer audit** (Section D footer row).
- **Editing source code.** EVALUATE is read-only on code.
- **Committing.** Writes `specs/<slug>/evaluate.md` and updates the spec
  frontmatter — both uncommitted. The user commits on their own cadence.

## Version control interaction

- Read-only on `src/`. The audit uses `git log` only.
- Writes `evaluate.md` and updates `spec.md` frontmatter. No commits.
- Does NOT push, merge, branch, or otherwise mutate refs.

## End-of-stage rules

When the EVALUATE record is written:

1. Show the user the file path.
2. Surface the per-section result and the overall outcome.
3. On PASS: confirm status bump to `done`; if a module completed, confirm
   the `roadmap.md` row is flipped to `done`.
4. On FAIL: list each failed item with one-line reason, then present the
   four options and ASK the user to pick.
5. STOP. Do not auto-loop to PLAN or anywhere else.
