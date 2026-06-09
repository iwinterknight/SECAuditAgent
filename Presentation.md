# TECHNICAL REPORT: AGENTIC RAG OVER FINANCIAL FILINGS (JPMORGAN 10-K)
### A System Architecture, Evaluation, and Code-Walkthrough Guide for Data-Science Teams

> Each section has the same shape: a **Visual**, the **Key Technical Points**, and a
> **Source-Code Walkthrough** (which file/symbol to open). Code references and claims here
> match the shipped code.

---

## SECTION 1: CORE THESIS & PROBLEM DEFINITION

### Visual Architecture

```
+---------------------------------------------------------------------------------+
|                                 THE FIDELITY BAR                                 |
|                                                                                  |
|   [ Traditional PDF RAG ]   --> chunks --> LLM    --> "plausibly close" figures  |
|                                                       (CRITICAL FAILURE RISK)    |
|                                                                                  |
|   [ Our agentic framework ] --> XBRL   --> DuckDB --> exact filed number         |
|                             --> prose  --> Qdrant --> isolated context snippet   |
+---------------------------------------------------------------------------------+
```

### Key Technical Points
* **The absolute fidelity constraint:** in regulatory and corporate finance a financial number is **exact or absent**. RAG tuned for conversational fluency is unsuited to reporting where a flipped sign or shifted decimal is a catastrophic failure.
* **The failure mode of naive RAG:** slicing financial statements into uniform token blocks strips metadata — it drops minus signs, mismatches footnoted conditions, and confuses parent disclosures with subsidiary columns.
* **Structural isolation:** we split quantitative financials from narrative prose **at ingestion**. The LLM never reads a raw figure out of prose, so reliability is *structural*, not a hope pinned on the prompt.

### Source-Code Walkthrough
* **Reference:** `docs/constitution.md` (the **Fidelity-over-Fluency** mandate, §1.2) — and where it is *enforced*: `src/config/schema.py` + `src/ingestion/xbrl.py` (the sole place a numeric fact is constructed).

---

## SECTION 2: DOMAIN MASTERY — INLINE XBRL (iXBRL)

### Visual Ingestion Topology

```
              +------------------------------------------+
              |   SEC EDGAR document  (inline XBRL .htm)  |
              +--------------------+---------------------+
                                   |
                 +-----------------+-----------------+
                 |                                   |
                 v                                   v
      Human-readable layout                Machine-readable tags
      (renders in a browser)               (FASB US-GAAP taxonomy)
                 |                                   |
                 |                                   v
                 |                          [ ingestion engine ]
                 |                          - _build_fact()
                 |                          - _dedupe_facts()
                 |                                   |
                 v                                   v
       Narrative Elements                  Clean XBRLFact JSONL
```

### Key Technical Points
* **What iXBRL is:** one SEC-mandated document where human-readable HTML carries embedded machine-readable tags defined by **FASB's US-GAAP** taxonomy (+ DEI for cover-page fields).
* **The auditing asymmetry:** independent auditors (e.g., PwC) audit the **statements**; the **XBRL tags themselves are the filer's own, generally un-audited** assertion. The engine must therefore tolerate duplicate taggings and surface contradictions.
* **De-duplication policy:** skip `nil` facts (never coerce to a false `0`); keep the **most-precise** of duplicate taggings; if two equally-precise values disagree, **log it loudly** (a source error) rather than silently pick.

### Source-Code Walkthrough
* **Reference:** `src/ingestion/xbrl.py` → `_dedupe_facts`, `_build_fact` (module functions).
  ```python
  def _dedupe_facts(facts: list[XBRLFact]) -> list[XBRLFact]:
      # group by fact_id (concept + context + unit); keep the most-precise tagging;
      # if two equally-precise taggings disagree, log loudly and keep one (a source error).
  ```
* Point out where `_build_fact` returns `None` (skips) for `nil` / un-parseable / "forever"-period facts — so a missing value is never coerced to `0`.

---

## SECTION 3: DATA FOUNDATION & THE FIREWALL RULE

### Ingestion Flow and Type Boundaries

```
                       +--------------------------------+
                       |     Raw SEC 10-K filing pack    |
                       +---------------+----------------+
                                       |
                    +------------------+------------------+
                    |                                     |
                    v                                     v
          [ stream A: narrative ]               [ stream B: numeric ]
          Docling (layout + tables)             Arelle (XBRL engine)
                    |                                     |
                    v                                     v
          Elements (located text)               XBRLFacts (Decimal)
          (16-page windows -> no OOM)           (no float conversion)
                    |                                     |
                    +------------------+------------------+
                                       |
                                       v
                        +------------------------------+
                        |     THE STRUCTURAL FIREWALL   |
                        |  the two streams never mix    |
                        +------------------------------+
```

### Key Technical Points
* **Strict stream bifurcation:** narrative `Element`s (from the PDF) and `XBRLFact`s (from the iXBRL instance) are produced by two isolated paths; neither imports the other's type. A number a table happens to contain is *text for retrieval*, never a figure to answer with.
* **Layout parsing + windowing:** Docling (layout model + **TableFormer**) extracts reading-order text; a 300-page 10-K is parsed in **16-page windows** (released between windows) to cap peak memory and avoid OOM.
* **Type-safe exact numbers:** every figure from Arelle (run **offline**) is parsed into a Python **`Decimal`** — floats are banned, so exact-match fidelity survives the pipeline.

### Source-Code Walkthrough
* **References:** `src/config/schema.py` (the `Element` and `XBRLFact` contracts), `src/ingestion/elements.py` (Docling → Elements; `_PAGE_WINDOW`), `src/ingestion/xbrl.py` (Arelle → XBRLFacts).
* Show `Element` vs `XBRLFact` in `schema.py`, then `parse_elements` (windowing) and `extract_facts` (the `Decimal` values) — two separate constructors, one firewall.

---

## SECTION 4: STRUCTURAL CHUNKING STRATEGY

### Table Row-Wise Segmentation

```
  Original table  (~7,200 chars)
  +-------------------------------------------------------------+
  | Year | Tier 1 Common Capital | Total Risk-Weighted Assets |  <- header row (repeated)
  +-------------------------------------------------------------+
  | 2024 | ...                   | ...                        |  <- row
  | 2025 | ...                   | ...                        |  <- row
  +-------------------------------------------------------------+
                       |
                       v   split row-wise; header prepended to each group
  Sub-chunk A:  "<table><tr>HEADER</tr><tr>2024 row</tr></table>"
  Sub-chunk B:  "<table><tr>HEADER</tr><tr>2025 row</tr></table>"
  (illustrative values; the point is the structure)
```

### Key Technical Points
* **No fixed-length windows:** the index unit is the parser's **natural block** — a paragraph, a heading, or a whole table — not an arbitrary token slice.
* **Table self-description:** long tables are split **row-wise**, with the **header row repeated** on each group, so every sub-chunk is self-describing when embedded (a headerless row group is meaningless).
* **Bug-fix validation:** a ~7.2k-char table was **~89% invisible** to a single dense vector (the embedding input was capped at 800 chars). Splitting it into self-describing sub-chunks puts every part back into the index.

### Source-Code Walkthrough
* **Reference:** `app/retrieval.py` → `_subchunks`, `_table_subchunks`.
  ```python
  def _table_subchunks(html: str) -> list[str]:
      # split the table HTML row-wise (<tr>...</tr>); prepend the header row to each group
      # so every sub-chunk is self-describing when embedded.
  ```
* Note the dense-side scoring: an Element is ranked by its **best** sub-chunk (max-pool) — see `hybrid_search`.

---

## SECTION 5: DUAL STORAGE ENGINE DESIGN

### In-Memory Analytics + Semantic Vector Search

```
                          +-----------------------------+
                          |     Agent (tool-calling)     |
                          +--------------+--------------+
                                         |
               +-------------------------+-------------------------+
               |                                                   |
               v                                                   v
  +---------------------------+                       +---------------------------+
  |  DuckDB  (facts)          |                       |  Qdrant  (vectors)        |
  |  - embedded, in-process   |                       |  - embedded, in-process   |
  |  - exact keyed lookup     |                       |  - dense search + payload |
  |  - (entity, concept, yr)  |                       |  - one point per sub-chunk|
  +------------+--------------+                       +------------+--------------+
               |                                                   |
               +-------------------------+-------------------------+
                                         |  built at startup from:
                                         v
                          +-----------------------------+
                          |  JSONL + .npy  (source of   |
                          |  truth, baked into image)   |
                          +-----------------------------+
```

### Key Technical Points
* **Dual store by data type:** **DuckDB** answers *exact* keyed lookups over typed fact rows (`entity`, `concept`, `period`); **Qdrant** answers *semantic* search over narrative sub-chunk embeddings. *"DuckDB for truth, Qdrant for recall."*
* **Embedded, in-process:** both run **inside the app process** (no server, no network) — `duckdb.connect()` (in-memory) and `QdrantClient(":memory:")`.
* **Rebuilt-from-source lifecycle:** at startup both are **built from the baked JSONL/`.npy`** and used read-only at query time — a fast analytical cache, fully reproducible. **JSONL remains the source of truth.**

### Source-Code Walkthrough
* **References:** `app/duckdb_store.py`, `app/vector_store.py`.
* `duckdb_store._conn` builds an **in-memory** `facts` table from the baked `facts/*.jsonl` (no file handle, no server); `headline_value` runs the exact, **dimensionless, consolidated** SQL lookup.
* `vector_store.dense_elements` applies the **`fiscal_year` payload filter** before the dense search, then maps sub-chunk hits back to their owning Element.

---

## SECTION 6: HYBRID SEARCH & RANKING MECHANICS

### Rank-Fusion Processing

```
                           +---------------------------+
                           |    agent search string    |
                           +-------------+-------------+
                                         |
                    +--------------------+--------------------+
                    |                                         |
                    v                                         v
         +-----------------------+                 +-----------------------+
         |   BM25  (sparse)      |                 |   Qdrant  (dense)     |
         |   exact keyword match |                 |   conceptual meaning  |
         +-----------+-----------+                 +-----------+-----------+
                     | top 80                                  | top 80
                     +--------------------+--------------------+
                                          v
                           +---------------------------+
                           |  Reciprocal Rank Fusion   |
                           |  1 / (60 + rank), summed  |
                           |  over BOTH rankers        |
                           +-------------+-------------+
                                         v
                           +---------------------------+
                           |  year filter -> parent-   |
                           |  expand (hit + neighbors) |
                           +---------------------------+
```

### Key Technical Points
* **Two rankers, complementary:** dense Qdrant captures meaning/paraphrase; sparse **BM25** nails exact terms (`CET1`, "allowance for credit losses").
* **Reciprocal Rank Fusion (RRF):** combine by **rank**, not score — no normalization needed. Each ranker's top-80 contributes `1/(60 + rank)`:

  `RRF(d) = 1/(60 + rank_BM25(d)) + 1/(60 + rank_dense(d))`

* **Parent-window expansion:** a matched sub-chunk pulls its immediate reading-order neighbors (within the same filing) so the LLM sees full local context. A `fiscal_year` filter scopes by year.

### Source-Code Walkthrough
* **Reference:** `app/retrieval.py` → `hybrid_search`.
* It runs BM25, then a Qdrant dense query (**synchronous**, not async/parallel), fuses by rank in the RRF loop (`1.0 / (60 + rank)`), applies the year filter, and calls `_parent_expand`.

---

## SECTION 7: CONTEXT PACKAGING FOR THE AGENT

### What the model actually receives

```
  +--------------------------------------------------------------------------+
  |                       LLM AGENT CONTEXT (tool outputs)                    |
  +--------------------------------------------------------------------------+
  |  [ narrative ]                                                           |
  |  [FY2024 p.97] "The firm's Common Equity Tier 1 capital ratio was..."     |
  |                                                                          |
  |  [ exact figure ]                                                        |
  |  Total assets (exact, from XBRL): FY2024: $4,002,814 million             |
  +--------------------------------------------------------------------------+
  |  RESULT: grounded, citable generation from a small, provenance-tagged    |
  |          context -- not a raw corpus dump.                               |
  +--------------------------------------------------------------------------+
```

### Key Technical Points
* **Sanitized tool boundary:** the LLM never touches raw DB rows or vector dumps — only **tool-result strings**.
* **Provenance headers:** narrative arrives as `[FY2024 p.97] "<text>"`; figures arrive as exact strings (`Total assets (exact, from XBRL): FY2024: $4,002,814 million`).
* **Grounded output:** because every source is tagged with year + page, answers are auditable and the token window isn't wasted on irrelevant prose.

### Source-Code Walkthrough
* **References:** `app/agent.py` → `_tool_search` (renders `[FY{y} p.{p}] {text[:500]}`), `app/answer.py` (`_facts_block`, the exact-fact strings).

---

## SECTION 8: DEPENDENCY-FREE AGENT IMPLEMENTATION

### Routing + the validator guard

```
                    +------------------------------------+
                    |          user question             |
                    +-----------------+------------------+
                                      v
                        +----------------------------+
                        |  OpenAI tool-calling loop  |
                        |  (temp 0, <= 4 iterations) |
                        +--------------+-------------+
                                       |
              +------------------------+------------------------+
              v                        v                        v
   lookup_financial_fact        search_filings              compute
   (DuckDB, exact)              (Qdrant + BM25)              (10 deterministic ops)
              |                        |                        |
              +------------------------+------------------------+
                                       v
                        +----------------------------+
                        |  VALIDATOR  (non-LLM)      |
                        |  every figure in the answer|
                        |  traces to a tool output?  |
                        +--------------+-------------+
                          ok -> [check]   |   not grounded -> FLAG (warn user)
```

### Key Technical Points
* **Dependency-free orchestration:** a ~40-line native loop over the OpenAI tool-calling API — **no LangGraph/LangChain**. A single agent with three flat tools (no sub-agents, no progressive disclosure).
* **Three atomic tools:** `lookup_financial_fact` (keyed DuckDB-backed lookup); `search_filings` (hybrid Qdrant + BM25); `compute` (a **deterministic Python function** exposing **10** operations — change / %-change / CAGR / average / sum / min / max / ratio / percent-of / difference — **never LLM math**).
* **Programmatic validation (it *flags*, not blocks):** a non-LLM check scans the answer for figures; any number that doesn't trace to a tool output is **flagged as ungrounded** (surfaced as a ⚠️ warning), catching a hallucinated *or* hand-computed value. A Self-RAG reflect→revise pass and a refusal path round it out.

### Source-Code Walkthrough
* **Reference:** `app/agent.py` → `_tool_loop` (≤4 iterations), `_TOOLS` (the 3 specs), `_tool_compute` (10 ops), `_validate` (the regex groundedness check), `_reflect` (Self-RAG).

---

## SECTION 9: CO-EQUAL EVALUATION PIPELINE

### Quality-evaluation matrix

```
+-----------------------------------------------------------------------------------+
|                          SYSTEM EVALUATION SUITE                                  |
+------------------------------------------+----------------------------------------+
| DETERMINISTIC (exact, zero variance)     | LLM-JUDGE (open-ended quality)         |
+------------------------------------------+----------------------------------------+
| - numeric_exact     (figure present)     | RAG triad:                             |
| - retrieval_hit     (relevant passage)   |   - context relevance                  |
| - tool_correct      (right tool routed)  |   - groundedness / faithfulness        |
| - year_scope_ok     (right filing year)  |   - answer relevance                   |
| - validator_pass    (figures grounded)   | Trajectory judge:                      |
|                                          |   - tool appropriateness / efficiency  |
|                                          |   - faithfulness (uses tool outputs)   |
+------------------------------------------+----------------------------------------+
|  MONITORING                                                                       |
|   - Regression gate: FLAG if an aggregate drops > 0.10 vs the committed baseline  |
|     (silent-failure detection; the gate the SDD process enforces on changes).     |
|   - Data drift: FLAG any headline metric moving > 30% year-over-year ("eyeball    |
|     it" -- a real-numbers move, not an error).                                    |
+-----------------------------------------------------------------------------------+
```

### Key Technical Points
* **Two surfaces:** score the **answer** *and* the **trajectory** — a right answer reached by a wrong path is a latent bug.
* **17-item golden set, all 5 fiscal years:** numeric lookups, cross-year/average `compute`, narrative (incl. year-scoped), and explicit **refusal** cases.
* **Monitoring:** **regression** flags a >0.10 aggregate drop vs a committed baseline (silent failure); **data drift** flags a >30% YoY move (a *data* signal for a human, not an error). Auto-triggerable: `python app/evaluate.py`.

### Source-Code Walkthrough
* **Reference:** `app/evaluate.py` → `GOLDEN` (the dataset), `_score_item`, `_judge` + `_judge_trajectory` (the LLM judges), `_regression` + `_data_drift` (monitoring).

---

## SECTION 10: CONTAINERIZED DEPLOYMENT

### Offline build vs lean runtime

```
  [ OFFLINE (build the corpus once) ]            [ RUNTIME IMAGE (lean, shipped) ]
  - Docling layout + TableFormer                 - app code (config + serialize)
  - PyTorch / transformer weights                - embedded DuckDB + Qdrant (built at startup)
  - Arelle XBRL engine                           - baked JSONL fact + element ledgers
  - parsing / segmenting pipelines               - pre-computed .npy embedding matrices
                                                   (NO Docling / Arelle / torch installed)
```

### Key Technical Points
* **Ingestion decoupled from runtime:** Docling, Arelle, torch and the parsing models run **only offline**; they are **absent** from the runtime image.
* **Lean single container:** the image ships the **baked corpus** — `data/derived/ingestion/` (facts + elements JSONL, `.npy` embeddings) — and installs only serving deps (`streamlit openai rank-bm25 numpy pydantic pydantic-settings duckdb qdrant-client`).
* **Fast startup:** no runtime parse or corpus re-embed; cold start is a one-time **~15-second** in-memory build of the stores from the baked artifacts.

### Source-Code Walkthrough
* **Reference:** the root `Dockerfile`.
* Note the `pip install` line (serving deps only — no torch/docling/arelle), and the `COPY data/derived/ingestion /srv/data/derived/ingestion` (the baked corpus — **not** the raw `data/SEC/` PDFs, which `.dockerignore` excludes).

---

## SECTION 11: LIMITATIONS & ROADMAP

### Plan vs. shipped

```
+-----------------------------------------------------------------------------------+
|                        DESIGN PLAN  vs  SHIPPED DEMO                              |
+------------------------------------------+----------------------------------------+
| INITIAL BLUEPRINT (SDD M1-M10)           | SHIPPED DEMO                           |
+------------------------------------------+----------------------------------------+
| - LangGraph orchestration                | - native OpenAI tool-calling loop      |
|   (router -> tools -> validator)         |   (~40 lines, no framework)            |
| - Qdrant server (Docker) + DuckDB        | - embedded, in-process DuckDB + Qdrant |
| - hierarchical parent/child chunking     | - layout-aware sub-chunks + parent-exp |
+------------------------------------------+----------------------------------------+
```

### Key Technical Points
* **Entity scope (§1.3):** answers the **consolidated parent, JPMorgan Chase & Co. (JPM)** only. The subsidiary (*JPMorgan Chase Bank, N.A.*) is **ingested and kept distinct** in the fact store, but the agent's lookup is **scoped to the consolidated entity** — i.e., kept separate and **not exposed**, never cross-contaminated.
* **Metric coverage:** the agent's lookup is wired to **8 headline metrics** of the ~**1,098** XBRL concepts present; exposing arbitrary concepts is the next scaling step.
* **Pragmatic reductions:** to maximize transparency and predictability under a time budget, the planned LangGraph graph became a native tool-loop, and the planned Qdrant-server + DuckDB became **embedded, in-process** stores — at this corpus size the **evaluation proved these substitutions cost no quality**.

### Source-Code Walkthrough
* **References:** `app/duckdb_store.py` (`headline_value` hard-filters `entity='JPMC_CONSOLIDATED'`), `app/answer.py` (`_HEADLINE`, the 8 metrics), `docs/guide/06-decisions-and-lessons.md` + `docs/guide/07-stores.md` (the divergences and why).

---

*Companion artifacts: slide deck `docs/presentation/report.pdf`, full code walkthrough `docs/guide/` (00–07), and the source notes in `docs/presentation/collated-context.md`.*
