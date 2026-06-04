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
the shape of the work without reading the rest.

## Data & Schema Changes

XBRL fact-table columns added/typed differently? Qdrant collection schema
or payload-filter fields changed? DuckDB facts schema changed? Chunk
metadata fields added? A change to a typed contract in
`docs/architecture.md` §5 (Element, XBRLFact, Chunk, RetrievedContext,
AgentState, Citation, TelemetryEvent)? If none, write `None.`

For each change: the contract or store, old shape, new shape, rebuild
step. Constitution §1.8 (source corpus read-only at runtime) applies —
new figures enter only by re-running ingestion, never by application
code; derived artifacts are rebuildable and gitignored.

## Interface / Contract Changes

New or changed module boundaries: an agent tool signature, a retrieval
function, an index read-client method, an API request/response model, or
a §5 typed contract. For each: old shape, new shape, who calls it (which
upper layer), whether it's backward-compatible. If breaking, say so
explicitly and name the callers. Confirm the change respects the
downward-only import rule (§1.6). If none, write `None.`

## Sequencing

The order in which the work happens. Keep it linear if possible.
Number the steps. Each step roughly = one task in tasks.md.

1. <step>
2. <step>
3. <step>

## Edge Cases

What unusual inputs, states, or environments must this handle?
Empty/missing XBRL facts, a query naming no fiscal year, an ambiguous
entity (Co. vs N.A.), a restated figure, an unparseable table, a missing
citation, a validator looping to max-iterations, a partial index. Each
edge case names the expected behavior.

- **<case>**: <expected behavior>
- **<case>**: <expected behavior>

## Test Strategy

How we'll prove this works (per Constitution §4 — tests are
feature-targeted; resource-intensive eval is tiered separately).

For each behavior in the spec's Acceptance Criteria, name the specific
test(s) that prove it.

| AC | Test path / check | Type | Notes |
|---|---|---|---|
| AC1 | `tests/unit/<file>.py::TestX::test_y` | unit (new) | |
| AC2 | cheap-eval: exact-match numeric vs XBRL for `<question>` | eval-cheap | deterministic tier (§4.3); golden entry `<id>` [new] |
| AC3 | cheap-eval: retrieval hit@k on the small fixed set | eval-cheap | per implement (§4.3) |
| AC4 | full golden-set RAG triad + agent-loop metrics | eval-heavy | NAMED + QUEUED, pre-merge/scheduled gate (§4.3) |

(UI manual verification is N/A until M9 — there is no UI yet.)

## Risks

The Constitution principles this plan touches and any tension with
them. For each tension, say either:

- "**§X.Y — <name>**: complies. <one-line reason>"
- "**§X.Y — <name>**: tensions because <reason>. Mitigation: <how>."
- "**§X.Y — <name>**: violates. This plan needs a constitution
  amendment first — see <amendment-spec-id>."

This section MUST name, when applicable:

- **(a) Constitution tensions** — financial fidelity (§1.1),
  numbers-from-XBRL (§1.2), entity/period (§1.3), the validator gate
  (§1.4), citations (§1.5), layer separation (§1.6), settings (§1.7),
  secrets (§5.1). If the change touches any, it MUST appear here. "No
  risks" is rarely true and is a smell.
- **(b) New dependencies** (§3) — any new library is named HERE before
  it is added, with a one-line justification against the ratified stack
  (`docs/architecture.md` §2).
- **(c) Eval-baseline impact** (§4.4) — for retrieval/agent/chunking
  changes: which golden-set entries are needed, and whether the change
  is expected to move any committed baseline metric (and why that move
  is an improvement, not a regression).

Other risks (fidelity regression surface, latency, schedule,
external-dependency exposure — cloud LLM billing, EDGAR rate limits):

- <risk>: <mitigation>
- <risk>: <mitigation>

## Affected files (best guess)

A flat list of file paths under `src/` (single repo) this plan expects
to touch. tasks.md will refine this — the goal here is "approximately
right" so the user can sense scope.

- `src/retrieval/<file>.py` — <reason>
- `src/index/clients.py` — <reason>
- `src/config/schema.py` — <reason>
- `tests/unit/<file>.py` — <reason>
- `src/eval/golden/<entry>.json` — <reason>
