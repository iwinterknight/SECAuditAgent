# PLAN review rubric — what a good plan looks like in this project

Use this when reviewing a `plan.md` (whether you're the author doing
self-review, or the `spec-reviewer` sub-agent). It's the project-specific
complement to the generic heuristics in
`.agent/agents/spec-reviewer.md`.

A good plan in this project does **all** of the following:

---

## 1. References the constitution by section number

Every plan touches at least one Constitution principle. The Risks
section names them and decides "complies / tensions / violates" with a
one-line reason. "No risks" is almost always wrong — it means the author
hasn't thought hard enough.

**The principles most plans touch:**

| Principle | When it's relevant |
|---|---|
| §1.1 Financial fidelity | ANY change in `agent/`, `retrieval/`, the calc tool, or anything that surfaces a user-visible number or claim |
| §1.2 Numbers from XBRL | Any numeric/calc path — figures must come from DuckDB XBRL, math from the deterministic tool, never LLM transcription/arithmetic |
| §1.3 Entity & period | Anything that returns a figure scoped to an entity (Co. vs N.A.) or a period (instant vs duration), or that handles restatements |
| §1.4 Validator gate | Any change in the agent graph that could add or move a claim-producing path; the validator edge must stay non-skippable |
| §1.5 Citations | Anything that emits a claim — narrative tuple or `xbrl_fact_id` required |
| §1.6 Layer separation | Anything crossing `api`/`agent`/`retrieval`/`index`/`chunking`/`ingestion`; imports flow downward only |
| §1.7 Config via settings | New config values, model names, store URLs, thresholds |
| §1.8 Corpus read-only | Any path that would mutate PDFs/XBRL at runtime (it must not) |
| §3 Code Standards | New top-level `src/` module, new dependency, new convention |
| §4 Testing & Eval | Always — every plan has a Test Strategy naming test paths; retrieval/agent/chunking plans name cheap-eval checks + golden-set entries |
| §4.2 Eval-regression gate | Any retrieval/agent/chunking change — name baseline impact |
| §5.1 Secrets | New secret or `.env` mention |

---

## 2. Names specific test paths and eval checks

Every Acceptance Criterion in the spec has a test entry in the plan's
Test Strategy table. Each entry names:

- For unit: `tests/<path>::<class>::<method>` (or marked `[new]` if not
  yet existing).
- For retrieval/agent/chunking: the **cheap deterministic eval** check
  that runs per implement (exact-match numeric vs XBRL, or retrieval
  hit@k on the small fixed set), AND the golden-set Q/A/context entries
  it needs (§4.4), marked `[new]` if they must be authored.
- The **heavy eval tier** (full-golden-set LLM-judge, re-embedding
  sweeps) named as `eval-heavy` and flagged QUEUED for the pre-merge /
  scheduled gate (§4.3) — not run per implement.
- The test/check type: `unit`, `eval-cheap`, `eval-heavy`, or
  `integration`.

A plan that says "we'll add tests" without paths is incomplete. (UI
manual verification is N/A until M9.)

---

## 3. Uses real file paths from the codebase

Plans that say `<some module>` or `<TBD>` haven't been grounded in the
code. The author should have read the relevant files under `src/` before
planning.

If the author genuinely doesn't know yet, they write `[VERIFY: ...]`
rather than guessing. But "I don't know" should be rare — it's the plan
stage, not the spec stage.

---

## 4. Sequences in dependency order, not in time order

Sequencing reflects what depends on what, not "Monday I do this, Tuesday
that." If T2 depends on T1, T1 comes first. Parallel-safe work goes in
any order or is marked parallel.

The implementer can then pick T1, finish, pick T2, finish. The sequence
is the dependency graph linearized. (Note the project's bottom-up build
order: you cannot retrieve before you index, index before you chunk,
chunk before you parse.)

---

## 5. Splits work by concern / layer into separate tasks

A plan that says "modify the hybrid retriever AND the validator check"
is a plan for TWO commits across TWO layers, not one. The plan flags
this; tasks.md splits it. (There is ONE repo — the split is by
concern/module/layer, not by repo.) A task that legitimately spans two
layers carries the §1.6 justifying note.

---

## 6. Acknowledges existing debt rather than working around it

If the plan touches a debt area or an open decision (an unresolved
[RATIFY] item, a still-open model/parser choice from architecture §9, a
gitignored derived artifact that needs rebuilding), the plan acknowledges
it explicitly rather than quietly assuming a resolution:

- Depending on a [RATIFY] default → name it, and note the spec is
  contingent on the lead confirming it.
- Touching a still-open choice (embedding model, reranker, LLM provider)
  → pin it in this module's plan with a one-line rationale, since
  architecture §9 defers it to the module that forces the decision.

A plan that quietly pretends the open decision is settled is failing at
this.

---

## 7. Edge cases name the expected behavior, not just the case

"What if the year is missing?" is not edge-case coverage. "If the query
names no fiscal year, the system answers for the most recent filed FY
and states the FY explicitly in the answer (§1.3)" is.

The Edge Cases section is contractual — it tells the implementer what to
write tests for.

---

## 8. Backward-compat is explicit, not implicit

If the plan changes a module boundary (an agent tool signature, a
retrieval function, an index read-client method, an API model, a §5
typed contract), it says either "backward compatible because <reason>"
or "BREAKING — callers to update: <list>". Not silent. Confirm the
change keeps imports flowing downward (§1.6).

---

## 9. The Approach is at the right altitude

A good Approach paragraph covers:

- The shape of the change in one sentence.
- The key decisions and the alternatives considered.
- One-line reasoning for picking the chosen approach.

It's NOT:

- A line-by-line description of every file change (that's tasks.md).
- A vague "we'll add a thing" (that's not enough to disagree with).
- A pure code listing (that's IMPLEMENT).

If a teammate disagrees with the Approach, they should be able to
disagree from the Approach paragraph alone, without reading the rest.
That's the right altitude.

---

## Common failure modes (watch for these)

| Failure mode | Smell | Fix |
|---|---|---|
| **No Risks** | "This is straightforward" | Re-examine §1.1 / §1.2 / §1.4 / §1.6 / §4 — usually one applies |
| **No test paths** | "Tests will be added" | Specify file/class/method or mark `[new]` |
| **No golden-set entry** | Retrieval/agent change with only a unit test | Name the §4.4 golden entry and the cheap-eval check |
| **No eval-baseline note** | Retrieval/agent/chunking change silent on metrics | State which baseline metrics could move and why it's an improvement (§4.2) |
| **Vague Approach** | "We'll integrate the filter into retrieval" | Name HOW (which filter fields? hard or soft? fusion weighting?) |
| **Tasks bundled** | T1 says "retriever and validator" | Plan should already separate these by layer |
| **Numbers off-XBRL** | Plan reads a figure from a parsed table | Route through DuckDB XBRL + calc tool (§1.2) |
| **Validator bypass** | New claim path skips the validator edge | Surface as constitution tension (§1.4) |
| **Unnamed dependency** | New library appears in Affected files, not Risks | Name it in Risks (b) first (§3) |
| **Upward import** | `retrieval/` imports `agent/` | Reverse the dependency or justify (§1.6) |
| **Backward-compat invisible** | Contract changed without flag | Add explicit statement |
| **Missing affected files** | List has 1 file but the change clearly touches a contract + a test | Re-read the code, expand |
| **Sequencing by time, not deps** | "Day 1: ..., Day 2: ..." | Reframe as ordered steps |
| **Plan re-does the spec** | Plan repeats Behavior section in full | Just reference the spec; plan is HOW |

---

## What a great plan looks like

The bar to clear:

1. A new contributor could read just `spec.md` + `plan.md` and start
   writing tasks without asking questions.
2. The Risks section reads like a senior engineer's pre-mortem — and for
   a retrieval/agent/chunking change, it names the golden-set entries and
   the eval-baseline impact.
3. The Test Strategy is concrete enough to write the failing tests (and
   the golden entries) before any implementation code.
4. The Affected files list, if rigorously expanded into tasks, produces
   a tasks.md that maps cleanly to the constitution (§1.6 layers) and the
   architecture (§5 contracts).
