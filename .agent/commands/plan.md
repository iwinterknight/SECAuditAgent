# /plan — PLAN stage

You are running the PLAN stage. The spec has been confirmed. Your job is
to design the approach and write `plan.md` alongside the spec.

## When to use

After the user has confirmed a `specs/<dated-slug>/spec.md` and said
"plan it" or `/plan`. Verify before writing:

- The spec exists at `specs/<dated-slug>/spec.md`.
- Its frontmatter `status` field reads `clarify` AND the user has
  explicitly confirmed it. (The status hasn't been auto-bumped yet —
  `/plan` is what bumps it.)
- All Open Questions in the spec are resolved or marked "deferred to
  PLAN" with a reason.

If any precondition fails, ASK the user instead of writing.

## Required reads (you must read these before writing)

1. **`specs/<dated-slug>/spec.md`** — the contract you are planning
   against.
2. **`docs/constitution.md`** — every plan is checked against it.
   Tensions go in the `Risks` section.
3. **`docs/architecture.md`** — the relevant sections: the layer the
   change lives in (§3 module map), the data flow it sits in (§4), and
   the typed contracts it produces or consumes (§5).
4. **The actual code** under `src/` in the affected module(s) — read
   enough to be concrete about file paths, function names, and existing
   patterns. Do not generalize from the architecture doc alone.

If during reading you find that the spec is wrong (a stated behavior
doesn't match what the code does, an assumption is invalidated), STOP
and tell the user. Don't write a plan against a flawed spec.

## File written

```
specs/<dated-slug>/plan.md
```

Plus an in-place edit to the spec's frontmatter:
```yaml
status: plan        # was: clarify
```

## Plan template

```markdown
---
spec: <YYYY-MM-DD-slug>          # back-reference to spec.md in same folder
status: plan
created: <YYYY-MM-DD>
---

# Plan: <spec title>

## Approach

How the change will be made, in 2–4 paragraphs of prose. Include the
key decisions and the alternatives you considered and rejected, with
one-line reasoning. A reader of just this section should understand
the shape of the work.

## Data & Schema Changes

XBRL fact-table columns added/typed differently? Qdrant collection
schema or payload-filter fields changed? DuckDB facts schema changed?
Chunk metadata fields added? A change to one of the typed contracts in
`docs/architecture.md` §5 (Element, XBRLFact, Chunk, RetrievedContext,
AgentState, Citation, TelemetryEvent)? If none, say "None."

For each change: the contract or store, old shape, new shape, and the
rebuild step. The Constitution's §1.8 (source corpus is read-only at
runtime) applies — new figures enter only by re-running ingestion, never
by application code; derived artifacts are rebuildable and gitignored.

## Interface / Contract Changes

New or changed module boundaries: an agent tool signature, a retrieval
function, an index read-client method, an API request/response model, or
any of the typed contracts in §5. For each: old shape, new shape, who
calls it (which upper layer), whether it's backward-compatible. If
breaking, say so explicitly and name the callers. Confirm the change
respects the downward-only import rule (§1.6) — no upper layer leaks into
a lower one.

## Sequencing

The order in which the work happens. Keep it linear if possible.
Number the steps. Each step roughly = one task in tasks.md (you'll
break this down formally during `/tasks`).

## Edge Cases

What unusual inputs, states, or environments must this handle?
Empty/missing XBRL facts, a query that names no fiscal year, an ambiguous
entity (Co. vs N.A.), a restated figure, an unparseable table, a missing
citation, a validator that loops to max iterations, a partial index. Each
edge case names the expected behavior.

## Test Strategy

How we'll prove this works (per Constitution §4 — tests are
feature-targeted; resource-intensive eval is tiered separately).

- For each behavior in the spec's Acceptance Criteria, name the
  specific test(s) that prove it.
- Unit tests: file path, test class, test method (Python, e.g.
  `python -m pytest tests/unit/<file>.py::TestX::test_y`). If the test
  doesn't exist yet, mark it `[new]`.
- For retrieval / agent / chunking changes, name the **cheap
  deterministic eval** that runs per implement (§4.3): exact-match
  numeric vs XBRL, or retrieval hit@k on the small fixed set. Name the
  golden-set Q/A/context entries this change needs (§4.4) — mark `[new]`
  if they must be authored.
- Flag the **heavy eval tier** (full-golden-set LLM-as-judge,
  re-embedding sweeps) as NAMED + QUEUED for the pre-merge / scheduled
  gate (§4.3) — not run per implement.
- UI manual verification is **N/A until M9** (there is no UI yet).

## Risks

The Constitution principles this plan touches and any tension with
them. For each tension, say either "this plan complies" with a one-line
reason, or "this plan tensions with §X.Y because ..." and describe how
the tension is mitigated. If the tension can't be mitigated, this
becomes a constitution-amendment spec, not a plan.

This section MUST name, when applicable:
- **(a) Constitution tensions** — especially fidelity (§1.1), numbers-
  from-XBRL (§1.2), entity/period (§1.3), the validator gate (§1.4),
  citations (§1.5), layer separation (§1.6), settings (§1.7).
- **(b) New dependencies** (§3) — any new library is named HERE before
  it is added, with a one-line justification against the ratified stack
  (`docs/architecture.md` §2).
- **(c) Eval-baseline impact** (§4.4) — for retrieval/agent/chunking
  changes: which golden-set entries are needed, and whether the change
  is expected to move any committed baseline metric (and why that move
  is an improvement, not a regression).

Other risks: fidelity regression surface, latency, schedule, external-
dependency exposure (cloud LLM billing, EDGAR rate limits).

## Affected files (best guess)

A flat list of file paths under `src/` (single repo) you expect to
touch. This is preliminary; tasks.md will refine it.

- `src/retrieval/hybrid.py` — add metadata-filter pass
- `src/index/clients.py` — expose filter fields on the read client
- `src/config/schema.py` — extend the RetrievedContext contract
- `tests/unit/test_hybrid_filter.py` — new
```

## Forbidden actions

- **Producing tasks.** Do not write `tasks.md`. That's `/tasks`'s job
  after the user confirms the plan.
- **Editing source code.** Do not touch any file under `src/` (other
  than reading it).
- **Auto-advance.** When the plan is written, STOP. Do not invoke
  `/tasks` unprompted.
- **Glossing over Risks.** If the change touches financial fidelity,
  the validator gate, numeric ground truth, entity/period handling,
  citations, layer separation, or adds a dependency, the Risks section
  names it explicitly. "No risks" is rarely true and is a smell.
- **Inventing patterns.** If the existing code uses convention X for
  similar work, the plan uses convention X (or argues why it doesn't, in
  `Approach`). Don't propose a new convention without a reason.
- **Quietly adding a dependency or a new `src/` module.** A new library
  goes in Risks (b) first. A new top-level module under `src/` needs a
  spec (§1.6) — surface it, don't assume it.

## Version control interaction

- Writes only under `specs/<slug>/plan.md`, plus an in-place status bump
  to `spec.md`'s frontmatter.
- No git commits — the user commits on their own cadence.
- No interaction with `src/` git state — only reads files for context.

## Educator Report (Reporting Protocol — Constitution §2)

Before you tell the user PLAN is complete, produce this step's **Educator
Report** — mandatory (Constitution §2). A `plan.md` without its report is
not done.

- **File:** `reports/<YYYY-MM-DD-slug>/02-plan.md`, authored from
  `.claude/skills/sdd-feature-cycle/templates/report-template.md`. Render to
  a sibling PDF with `python reports/render.py reports/<slug>/02-plan.md`.
  Markdown committed; PDF rebuildable and gitignored.
- **Voice:** educator. High → low; teach, don't summarize.
- **PLAN focus:** walk the Approach paragraph by paragraph; for **every
  fork**, name the alternative considered and the one-line reason it lost
  (e.g. parser Docling vs Unstructured; a package or framework choice and
  what it buys over the alternative); teach any new domain concept the
  approach introduces; explain the constitution tensions in Risks and how
  each is mitigated; explain the Test Strategy — the cheap deterministic
  tier that runs per implement vs the heavy tier queued for the gate, and
  why that split exists. Reflect the `spec-reviewer` findings.

## End-of-stage rules

When `plan.md` is written:

1. Show the user the file path.
2. Summarize the Approach, list the Risks one-line each, and name how
   many test cases the Test Strategy specifies plus any new golden-set
   entries it calls for (so the user can sense the size).
3. Spawn the `spec-reviewer` sub-agent on this plan and surface its
   findings inline (Ambiguities, Missing Acceptance Criteria,
   Constitution Tensions, Suggestions). The reviewer does not edit —
   it only critiques.
4. **Produce the Educator Report** `reports/<slug>/02-plan.md` (see above,
   reflecting the reviewer's findings) and render it to PDF.
5. Tell the user the next step is `/tasks` and that you will NOT
   invoke it.
6. Stop.

A plan exits PLAN (status `plan` → `tasks`) only when:

- The user has confirmed the plan is correct.
- The `spec-reviewer` findings have been addressed (resolved, deferred
  with reason, or rejected with reason).
- The lead has approved any Constitution tensions named in Risks.
