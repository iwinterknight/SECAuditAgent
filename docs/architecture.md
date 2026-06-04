# Architecture — AuditAgent

The target-state map. Where the constitution says *what must be true*, this
doc says *how the system is shaped* so those truths hold. It is the
reference a plan checks itself against ("does my module fit here?").

It describes the **destination**, not today's state — most modules below are
not built yet. `docs/roadmap.md` tracks which ones exist. When a module
spec refines a boundary here, update this doc in the same change (Constitution
§6.7).

---

## 1. The system in one picture

Two subsystems share a corpus and a telemetry stream. One answers; one
judges.

```
            ┌──────────────────────── OFFLINE (build time) ────────────────────────┐
            │                                                                       │
  PDFs ─────┤  ingestion ──► chunking ──► index ──┐                                 │
  (LFS)     │   (parse)      (enrich)    (build)   ├──► Qdrant  (dense+sparse vecs)  │
            │       │                              └──► DuckDB  (XBRL facts)         │
  XBRL ─────┘       └──► XBRL facts ───────────────────────────────────┘            │
  (EDGAR)                                                                           │
            └───────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼  (stores are read at query time)
            ┌──────────────────────── ONLINE (request path) ───────────────────────┐
            │                                                                       │
  user ──►  api ──►  agent ─────────────────────────────────────────► cited answer │
            │       (LangGraph)                                            ▲        │
            │          │  router ──┬──► retrieval tool ──► Qdrant ─► rerank │        │
            │          │           └──► numeric/calc tool ──► DuckDB        │        │
            │          └──────────────► validator/critic ─────────────────►┘        │
            │                                    │                                  │
            └────────────────────────────────────┼──────────────────────────────────┘
                                                 ▼
                                            telemetry  ──►  eval  (offline, decoupled)
                                                            golden set · RAG triad ·
                                                            agent-loop metrics · drift
```

The **dominant value is financial fidelity** (Constitution §1.1). Every
arrow into "cited answer" passes through the validator first; the numeric
arrow originates in DuckDB (XBRL), never in an LLM's transcription of a
table.

---

## 2. Ratified stack

Settled at kickoff (2026-06-04). Each row is a fork we will *not* relitigate
casually — changing one is a constitution-level change (spec + lead
approval). The "why" is the part that matters; the tool is replaceable, the
reasoning is the commitment.

| Concern | Choice | Why this and not the alternative |
|---|---|---|
| **Version control** | One Git repo + **Git LFS** for PDFs | Single repo (unlike RFI's two) — SDD artifacts and code co-evolve. PDFs are large binaries; LFS keeps history lean (Constitution §5.2). |
| **Orchestration** | **LangGraph** | Explicit, inspectable state graph. The validator must be a *non-skippable edge* (§1.4) — a graph encodes that structurally; a plain agent loop relies on prompt goodwill. Consistent with RFI. |
| **Generation + validation LLM** | **Cloud LLM** (provider pinned in M5) | Frontier reasoning for routing, synthesis, and the critic. The hard part (entity/numeric judgment) needs the strong model. |
| **Embeddings** | **Local / open** model (pinned in M2/M3) | Bulk corpus embedding is the expensive, repeated step. Local keeps rebuilds free and offline-capable. Hybrid = local embed + cloud generate. |
| **Numeric ground truth** | **EDGAR XBRL** facts | The financial-fidelity keystone. XBRL is the machine-readable figures the registrant *filed*. Reading them from DuckDB removes the LLM from the transcription-and-arithmetic loop (§1.2) — the single largest error source. |
| **Vector store** | **Qdrant** (Docker, local) | First-class hybrid (dense + sparse) search and rich metadata filtering — both load-bearing for 10-K retrieval (filter by FY/section/entity). Runs locally in a container; same engine ports to cloud later. |
| **Structured store** | **DuckDB** over XBRL facts | In-process, zero-server, fast analytical SQL over a few hundred-thousand facts. The calc tool queries it deterministically. |
| **Language** | **Python 3.13** | Ecosystem (LangGraph, parsers, Ragas). Constitution §3. |

Still open, pinned to the module that forces the decision (not decided
here): exact embedding model, exact cloud LLM provider, PDF parser (Docling
vs Unstructured), reranker model, and the [RATIFY] restatement
source-of-truth default (Constitution §1.3). See §9.

---

## 3. Module map (the layers)

Code lives in `src/`, one module per layer. **Imports flow downward only**
(Constitution §1.6) — a lower layer never imports an upper one. This is what
keeps the system testable in isolation and lets eval read telemetry without
sitting in the request path.

```
src/
  api/         M6   chat surface (HTTP/WS), request/response models
  agent/       M5   LangGraph: router, tools, validator/critic, agent state
  retrieval/   M4   hybrid search, rerank, parent expansion, metadata filters
  index/       M3   Qdrant + DuckDB builders and read clients
  chunking/    M2   parent/child split, table-to-text, metadata stamping
  ingestion/   M1   PDF + XBRL → normalized elements
  eval/        M7/M8 golden set, RAG triad, agent-loop metrics, drift, scheduler
  config/      M0/M1 settings, logging, shared schema/types  (cross-cutting)
```

`config/` is the one module everything may import — it holds the settings
object (Constitution §1.7) and the shared dataclasses/Pydantic types that
define the contracts in §5. It depends on nothing above it.

`eval/` is deliberately **off the request path**. It reads the telemetry
stream and the committed golden set; it never sits between the user and an
answer. That decoupling is what lets it run on a schedule and localize
*which stage* failed (Constitution §4).

**Dependency direction (who may import whom):**

```
api ─► agent ─► retrieval ─► index ─► chunking ─► ingestion
  └──────┴─────────┴──────────┴──────────┴───────────┴──► config
eval ─► (reads telemetry + golden set + index read-clients; imports config)
```

A function that legitimately spans two layers needs a justifying note in its
plan. No new top-level module under `src/` without a spec.

---

## 4. Data flow in detail

### 4.1 Ingest path (offline, deterministic, rebuildable)

Run by the pipeline, not by application code (Constitution §1.8). Every
stage is reproducible from source — derived artifacts are gitignored and can
be deleted and rebuilt.

```
data/SEC/10-K Filings/yearly/*.pdf  ─┐
                                     ├─► [ingestion] ─► normalized Elements ─┐
EDGAR XBRL (per filing)  ────────────┘        │  (text, tables, headings,    │
                                              │   page, section, FY tagged)  │
                                              │                              ▼
                                              │                       [chunking]
                                              │                  parent/child split,
                                              │                  table → text summary,
                                              │                  metadata stamping
                                              │                              │
                                              │                              ▼
                                              │                      enriched Chunks
                                              │                              │
                                              ▼                              ▼
                                       XBRL Facts ──► [index: DuckDB]  [index: Qdrant]
                                                      facts table        dense + sparse
                                                                         vectors + payload
```

Why two destinations: **narrative** lives in Qdrant (semantic search over
prose and table-summaries); **numbers** live in DuckDB (exact lookup by
entity/period/concept). A query about *"why did credit costs rise"* hits
Qdrant; *"CET1 ratio in 2024"* resolves against DuckDB. The agent decides
which (§4.2).

### 4.2 Query path (online, the request)

```
user query
   │
   ▼
[api]  validate request → AgentState
   │
   ▼
[agent · router]  classify intent:  narrative │ numeric │ hybrid/multi-hop
   │
   ├─(narrative)─► [retrieval]  hybrid search (dense+sparse) → filter by
   │                            FY/section/entity → rerank → parent expansion
   │                                   │
   ├─(numeric)───► [agent · calc tool]  deterministic lookup in DuckDB XBRL
   │                            facts (entity, period, concept) → compute via
   │                            tool, not LLM arithmetic
   │                                   │
   └─(hybrid)────► both, in the order the router plans
                                       │
                                       ▼
                       [agent · validator / critic]   ◄── HARD GATE (§1.4)
                         context check · entity check · numeric check
                                       │
                          ┌────────────┴────────────┐
                     pass │                          │ fail
                          ▼                          ▼
                   cited answer            loop back (re-retrieve / re-plan)
                          │                  or return "cannot ground this"
                          ▼
                        [api] → user
                          │
                          └─► telemetry event (query, route, chunk ids, scores,
                                                tool calls, validator verdict)
```

The validator is an **edge in the graph**, not a function the LLM may choose
to call. Any future path that emits a user-visible financial claim must
route through it or replicate it — a new bypass is a constitution-level
change (§1.1).

---

## 5. The contracts between layers

These are the typed objects that cross module boundaries. They live in
`config/` (shared schema) so no layer has to import another just for a type.
Exact field lists are ratified in the owning module's spec; this is the
shape and the intent.

| Contract | Produced by | Consumed by | Carries (intent) |
|---|---|---|---|
| **Element** | ingestion | chunking | One parsed unit (paragraph, table, heading) + provenance: filing FY, page, section/Item, element kind. |
| **XBRLFact** | ingestion | index→DuckDB, calc tool | One machine-readable figure: entity, concept (us-gaap tag), period (instant/duration), value, unit, source filing. |
| **Chunk** | chunking | index→Qdrant, retrieval | Child text + parent id + financial metadata (section, metric/topic, entity, period) + the table-to-text summary when applicable. |
| **RetrievedContext** | retrieval | agent | Ranked chunks after rerank + parent expansion, each with its citation tuple (FY, Item/section, page or chunk id). |
| **AgentState** | api / agent | agent (all nodes) | The LangGraph state: query, route decision, retrieved context, tool results, validator verdict, citations, final answer. |
| **Citation** | retrieval / calc | validator, api | `(filing FY, Item/section, page or chunk id)` for narrative; `xbrl_fact_id` for numeric. **No citation → no claim** (§1.5). |
| **TelemetryEvent** | api / agent | eval | The decoupling seam: per-request record of route, chunk ids, scores, tool calls, validator verdict, latency. Secrets scrubbed at write (§5.4). |

The **Citation** and **TelemetryEvent** contracts are the two that make
fidelity *machine-checkable*: citations let the validator and eval verify
grounding; telemetry lets eval localize which stage failed without being in
the request path.

---

## 6. Evaluation architecture

Eval is a subsystem, not a test folder. It answers *"is the answer engine
still trustworthy, and if not, which stage broke?"* It couples to the RAG
system through exactly two seams: the **committed golden set** (inputs +
ground truth) and the **telemetry stream** (what actually happened).

```
              golden set (committed)              telemetry stream
              Q · expected A · expected ctx ·      (per-request events)
              XBRL-derived numeric truth                │
                     │                                  │
                     ▼                                  ▼
        ┌─────────────────────────── eval ───────────────────────────┐
        │                                                             │
        │  RAG triad        agent-loop metrics      drift detection   │
        │  ─ context rel.   ─ tool-call accuracy    ─ data drift      │
        │  ─ groundedness   ─ trajectory efficiency ─ concept drift   │
        │  ─ answer rel.    ─ max-iter / loops      ─ retrieval drift │
        │                                                             │
        │  cheap tier (per /implement):  exact-match numeric vs XBRL, │
        │       retrieval hit@k on a small fixed set  (deterministic) │
        │  heavy tier (pre-merge / scheduled):  full golden-set       │
        │       LLM-as-judge, re-embedding sweeps  (billed, queued)   │
        └─────────────────────────────────────────────────────────────┘
                     │
                     ▼
        baselines (committed)  ──►  regression gate: no metric regresses
        eval/baselines/             vs the last committed baseline (§4.2)
```

Two design commitments from the constitution shape this:

- **Tiering (§4.3).** The cheap, deterministic subset runs every
  `/implement`; the expensive LLM-judge / re-embedding runs are *named and
  queued* for the pre-merge / scheduled gate. This keeps the inner loop fast
  and the bill bounded.
- **Regression gate (§4.2).** A retrieval/agent/chunking change is not done
  until eval shows **no regression vs the committed baseline**. Baselines
  live in `eval/baselines/` and are committed; runs in `eval/runs/` are
  transient (gitignored).

**Silent-failure detection** is the point of component-level scoring: a
groundedness score below the alert floor, or a validator that keeps looping
to max-iterations, is a *stage* signal, not just "the answer was wrong." The
drift types are distinct on purpose — *data* drift (corpus/query
distribution shifts), *concept* drift (the meaning of a good answer shifts),
*retrieval* drift (the same query starts pulling different chunks).

---

## 7. How it runs locally

Local-first is a hard requirement (the whole system must run on the lead's
machine before any cloud talk).

| Piece | Local form |
|---|---|
| Qdrant | Docker container, persisted to a gitignored volume |
| DuckDB | A single `.duckdb` file (gitignored, rebuildable) |
| Embeddings | Local model — no network needed to embed/rebuild |
| Cloud LLM | The one external call: generation + validation. Key in `.env` (§5.1). |
| Corpus | PDFs already present under `data/SEC/10-K Filings/yearly/` (LFS) |
| XBRL | Pulled from EDGAR by the ingestion pipeline into a gitignored derived path |

The only thing that reaches the network at query time is the cloud LLM.
Everything else — index, facts, embeddings — is local and rebuildable from
the committed PDFs + EDGAR.

---

## 8. External dependencies

- **EDGAR (SEC)** — source of XBRL facts (and the canonical filings). Pulled
  at ingest time, not query time. Read-only.
- **Cloud LLM provider** — generation + validation. The one paid, networked
  dependency on the request path. Provider pinned in M5; key in `.env`.
- **Docker** — runs Qdrant locally.
- **Git LFS** — versions the PDFs.

Everything else is a Python library, declared per module in its plan's Risks
section before it is added (Constitution §3).

---

## 9. Open decisions (pinned, not yet ratified)

Deliberately deferred to the module that is forced to decide, so we choose
with code in front of us rather than guessing now:

| Decision | Forced by | Default leaning (not binding) |
|---|---|---|
| PDF parser: Docling vs Unstructured | M1 ingestion | Decide against real 10-K table fidelity. |
| Exact embedding model | M2/M3 | A strong open model with a long context for table-summaries. |
| Reranker model | M4 retrieval | Cross-encoder reranker; cheap tier may skip. |
| Cloud LLM provider (OpenAI vs Anthropic) | M5 agent | Pick on entity/numeric judgment quality + tool-use. |
| **[RATIFY]** restatement source-of-truth per FY | M1/M3 (XBRL load) | Original filing for FY *N*, not later restatement (Constitution §1.3). |
| Telemetry/observability backend (Phoenix vs LangSmith vs file) | M7/M8 | Start file-based + local Phoenix; defer hosted. |

Each becomes a row in the owning module's plan, decided there, then promoted
into the Ratified-stack table (§2) once settled.

---

## 10. Sharp edges

The things most likely to cause a fidelity bug if forgotten:

1. **Entity confusion (§1.3).** "Chase" = JPMorgan Chase & Co. (consolidated
   registrant, JPM) ≠ JPMorgan Chase Bank, N.A. (subsidiary). Both appear in
   the same filing with *different* numbers. Entity is a first-class
   metadata field and a validator check — never a free-text afterthought.
2. **Period mixing.** Balance-sheet "as of" (instant) vs income "for the
   year" (duration) figures must not be blended. The XBRL period type
   distinguishes them; preserve it through to the answer.
3. **Restatements.** A figure for FY2022 differs between the 2022 10-K and
   the 2024 10-K (which restates it). The source-of-truth rule (§9 [RATIFY])
   must be applied at load time, not guessed at answer time.
4. **Tables are where parsing dies.** Dense financial tables are the hardest
   parse and the highest-value content. Table-to-text summaries (M2) are how
   semantic search reaches a number's *context*; the number itself still
   comes from XBRL (M1/M3), not the parsed table.
5. **The validator must stay non-skippable.** It is an edge, not a tool
   call. Any refactor that lets the LLM route around it is a constitution
   violation, not a bug.
