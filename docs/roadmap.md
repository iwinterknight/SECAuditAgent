# Roadmap — AuditAgent

The durable module tracker. The constitution is the *law*, the architecture
is the *map*, this is the *itinerary*: which modules exist, in what order
they unlock, and which spec built each one.

Build order is bottom-up along the dependency chain in `architecture.md` §3:
you cannot retrieve before you index, index before you chunk, chunk before
you parse. The answer engine (M1–M6) comes first, the trust engine (M7–M8)
wraps it, then UI (M9) and cloud (M10) — exactly the order the lead asked
for: **core modules first, UI second-to-last, cloud last.**

Status legend: `done` · `in-progress` · `planned` · `blocked`.

---

## At a glance

| # | Module | Layer (`src/`) | Unlocks | Status |
|---|---|---|---|---|
| **M0** | Scaffolding & SDD framework | — / `config/` | everything | **in-progress** |
| **M1** | Ingestion & parsing | `ingestion/` | M2, the XBRL store | planned |
| **M2** | Chunking & enrichment | `chunking/` | M3 | planned |
| **M3** | Index builders | `index/` | M4, the calc tool | planned |
| **M4** | Retrieval | `retrieval/` | M5 | planned |
| **M5** | Agent (router · tools · validator) | `agent/` | M6, real answers | planned |
| **M6** | API / chat surface | `api/` | M7 telemetry, M9 | planned |
| **M7** | Evaluation foundation | `eval/` | the regression gate | planned |
| **M8** | Evaluation automation | `eval/` | drift / silent-failure alerts | planned |
| **M9** | UI | `ui/` | demo / usability | planned |
| **M10** | Cloud deployment | infra | external access | planned |

The **first answer end-to-end** is possible at the end of M5 (CLI/script).
The **first evaluated answer** at M7. The **first usable product** at M9.

---

## M0 — Scaffolding & SDD framework  *(in-progress)*

**Goal.** Lay the framework, principles, and module roadmap before any
application code — Spec-Driven from line one.

**Deliverables.**
- Git repo + Git LFS (`*.pdf`), `.gitignore`, `.gitattributes` — **done**
- `AGENTS.md`, `CLAUDE.md`, `README.md` — **done**
- `docs/constitution.md`, `docs/architecture.md`, `docs/roadmap.md` — **done**
- `.agent/commands/` (spec, plan, tasks, implement, evaluate) + `.agent/agents/`
  (spec-reviewer, implementer), `.claude/` shims + sdd-feature-cycle skill —
  **pending (M0 Phase 2)**, adapted for single-repo with the Reporting
  Protocol baked into implement, and the eval-regression gate baked into
  evaluate.
- `src/config/` minimal settings + logging skeleton — **pending** (may land
  with M1 if M0 stays docs-only).

**Spec.** This bootstrap (no dated spec folder; it *is* the framework that
specs use).

**Dependencies.** None. **Done when.** Phase 2 machinery exists and the
scaffold walkthrough is delivered (Reporting Protocol).

---

## M1 — Ingestion & parsing  *(planned)*

**Goal.** Turn each 10-K into two normalized streams: **Elements** (text /
tables / headings with provenance) and **XBRLFacts** (machine-readable
figures). This is the fidelity foundation — everything numeric traces here.

**Key decisions forced here.** PDF parser (Docling vs Unstructured);
restatement source-of-truth per FY ([RATIFY], Constitution §1.3); EDGAR XBRL
pull mechanism.

**Deliverable files (indicative).**
`src/ingestion/pdf.py` (layout/table-aware parse → Elements),
`src/ingestion/xbrl.py` (EDGAR fetch + parse → XBRLFacts),
`src/ingestion/elements.py` (the normalized Element schema, in `config/`),
`src/config/settings.py` (paths, EDGAR config).

**Dependencies.** M0. **Unlocks.** M2 (chunking needs Elements), M3 (DuckDB
needs XBRLFacts).

**Done when.** All 5 filings parse to Elements with FY/section/page
provenance; XBRL facts load for all 5 FYs with entity + period type; a cheap
test asserts a known figure (e.g. a CET1 ratio) matches the XBRL value.

---

## M2 — Chunking & enrichment  *(planned)*

**Goal.** Convert Elements into retrieval-ready **Chunks**: hierarchical
parent/child splits, table-to-text summaries, and financial metadata
stamping (section, metric/topic, entity, period).

**Why it's its own module.** This is where 10-K-specific RAG technique lives
— the parent/child hierarchy preserves context a flat chunker destroys, and
table-to-text is how semantic search ever reaches a number's surrounding
meaning.

**Deliverable files (indicative).**
`src/chunking/hierarchy.py` (parent/child), `src/chunking/tables.py`
(table → text summary), `src/chunking/metadata.py` (entity/period/section
stamping), `Chunk` schema in `config/`.

**Dependencies.** M1. **Unlocks.** M3.

**Done when.** Elements → Chunks with parent links and complete metadata;
table chunks carry a faithful text summary; a golden-set retrieval entry can
name the chunk it expects.

---

## M3 — Index builders  *(planned)*

**Goal.** Build the two stores: **Qdrant** (dense + sparse vectors + payload
for narrative) and **DuckDB** (XBRL facts for numeric lookup). Provide read
clients for M4 and the calc tool.

**Key decisions forced here.** Exact embedding model; Qdrant collection
schema (vector dims, payload filter fields); DuckDB facts table schema.

**Deliverable files (indicative).**
`src/index/qdrant_build.py`, `src/index/duckdb_build.py`,
`src/index/clients.py` (read-side), embedding wiring in `config/`.

**Dependencies.** M2 (Qdrant) + M1 (DuckDB). **Unlocks.** M4, the calc tool
in M5.

**Done when.** A built Qdrant collection returns sane neighbors for a probe
query; DuckDB answers an exact fact lookup by (entity, period, concept); both
rebuild from source deterministically (gitignored artifacts).

---

## M4 — Retrieval  *(planned)*

**Goal.** Hybrid search (dense + sparse) with metadata filtering (FY /
section / entity), reranking, and parent expansion — returning
**RetrievedContext** with citations attached.

**Key decisions forced here.** Reranker model; fusion weighting; filter
strategy (hard vs soft).

**Deliverable files (indicative).**
`src/retrieval/hybrid.py`, `src/retrieval/rerank.py`,
`src/retrieval/expand.py` (parent expansion), `src/retrieval/filters.py`.

**Dependencies.** M3. **Unlocks.** M5.

**Done when.** Retrieval hit@k passes on the small fixed set (cheap eval
tier); every returned chunk carries a valid citation tuple; entity/period
filters demonstrably exclude the wrong-entity chunk.

---

## M5 — Agent (router · tools · validator)  *(planned)*

**Goal.** The LangGraph graph: **router** (narrative / numeric / hybrid) →
**retrieval tool** + **numeric/calc tool** (deterministic DuckDB math) →
**validator/critic** (the hard gate). First real end-to-end answer.

**Key decisions forced here.** Cloud LLM provider (OpenAI vs Anthropic);
calc-tool sandbox bounds (Constitution §5.3); validator check thresholds.

**Deliverable files (indicative).**
`src/agent/graph.py` (LangGraph wiring), `src/agent/router.py`,
`src/agent/tools/retrieval_tool.py`, `src/agent/tools/calc_tool.py`,
`src/agent/validator.py`, `AgentState` in `config/`.

**Dependencies.** M4 + M3. **Unlocks.** M6, and the first answers eval can
score.

**Done when.** A question end-to-end returns a cited, validated answer; the
validator is a non-skippable edge (§1.4); numeric answers come from the calc
tool over XBRL, never LLM arithmetic; a "cannot ground this" path exists.

---

## M6 — API / chat surface  *(planned)*

**Goal.** Wrap the agent in an HTTP/WS chat surface with request/response
models, and emit the **TelemetryEvent** stream eval depends on.

**Deliverable files (indicative).**
`src/api/app.py`, `src/api/models.py` (request/response),
`src/api/telemetry.py` (event emission, secret scrubbing §5.4).

**Dependencies.** M5. **Unlocks.** M7 (telemetry), M9 (UI has a backend).

**Done when.** A chat request returns a cited answer over HTTP/WS; every
request writes a scrubbed telemetry event; `api/` imports `agent/` but not
vice-versa (§1.6).

---

## M7 — Evaluation foundation  *(planned)*

**Goal.** The golden set + the scorers: **RAG triad** (context relevance,
groundedness, answer relevance), **agent-loop metrics** (tool-call accuracy,
trajectory efficiency), and the **two-tier** runner (cheap deterministic per
implement; heavy LLM-judge queued). Establishes the first committed
**baseline** and the **regression gate**.

**Key decisions forced here.** Golden-set format; judge model; the
groundedness alert floor (Constitution §1.7 names it in settings);
observability backend (Phoenix vs LangSmith vs file).

**Deliverable files (indicative).**
`src/eval/golden/` (Q/A/context + XBRL-derived numeric truth),
`src/eval/triad.py`, `src/eval/agent_metrics.py`, `src/eval/runner.py`,
`eval/baselines/` (committed), `eval/runs/` (gitignored).

**Dependencies.** M6 (telemetry) + M5 (answers to score). **Unlocks.** M8;
the §4.2 regression gate for all later changes.

**Done when.** The golden set scores end-to-end; the cheap tier runs in a
single `/implement`; a baseline is committed; the gate can detect a seeded
regression.

---

## M8 — Evaluation automation  *(planned)*

**Goal.** Make the trust engine *autonomous*: scheduled runs, **drift
detection** (data / concept / retrieval), **silent-failure monitoring**
(groundedness floor, max-iteration loops), and alerting/statistics.

**Deliverable files (indicative).**
`src/eval/drift.py` (the three drift types), `src/eval/monitors.py`
(silent-failure triggers), `src/eval/scheduler.py` (cron/auto-trigger),
`src/eval/report.py` (statistics output).

**Dependencies.** M7. **Unlocks.** Hands-off trust monitoring.

**Done when.** A scheduled run produces a drift + silent-failure report;
each drift type has a concrete detector; crossing a threshold raises a
visible alert.

---

## M9 — UI  *(planned)*

**Goal.** The chat front-end — the first time the system is *usable* rather
than *scriptable*. Deliberately late: the lead asked for it second-to-last,
after the engine and eval prove out.

**Deliverable files (indicative).** `ui/` (framework TBD at M9), wired to the
M6 API; surfaces citations prominently (they are the UX of fidelity, §1.5).

**Dependencies.** M6 (+ enough of M5 to answer well). **Unlocks.** Demos,
usability feedback.

**Done when.** A user can ask a question and see a cited, grounded answer in
a browser; citations are click-traceable to (FY, section, page).

---

## M10 — Cloud deployment  *(planned)*

**Goal.** Move the proven local system to the cloud — last, by design.
Container the stores, host the API, manage secrets and the LLM key off the
repo.

**Key decisions forced here.** Hosting target; Qdrant local→hosted;
secret management; scheduled-eval in the cloud.

**Dependencies.** M9 (a working product to deploy). **Unlocks.** External
access.

**Done when.** The system runs in the cloud with the same fidelity gates and
eval as local; secrets are injected, never committed (§5.1).

---

## How this doc stays honest

- A module flips to `in-progress` when its spec opens, `done` when
  `/evaluate` passes (Constitution §6).
- Each module's real spec folder (`specs/YYYY-MM-DD-<slug>/`) is linked here
  once it exists — this table is the index into them.
- Boundaries refine as code lands; when they do, update `architecture.md`
  and this row in the same change. The roadmap is a living plan, not a
  promise carved at kickoff.
