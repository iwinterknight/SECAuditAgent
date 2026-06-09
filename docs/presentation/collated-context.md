# Collated context — JPMorgan 10-K Agentic RAG + Evaluation
*Report source material, synthesized from the deep-dive notes (`gathered-context.md` [1]–[20]).
Each section: the crucial points → the insight → the code → a sayable line.*

## One-line thesis
An **agentic RAG** over JPMorgan Chase & Co.'s last five 10-Ks (FY2021–2025) that answers **exact
financials and narrative**, built so a financial number is **exact or absent — never plausibly
wrong**, paired with a **co-equal evaluation** harness that proves it.

## Executive summary
A 10-K carries two bodies — narrative prose and a parallel machine-readable **XBRL** package of
every figure. The system handles each with the right tool: **numbers come only from XBRL** (exact,
`Decimal`, via DuckDB) and **arithmetic only from a deterministic tool** — never the LLM; **narrative
is retrieved** (hybrid) and cited. An **agent** routes each question between those tools, **self-
corrects**, and a **validator** checks every stated figure is grounded. The second deliverable, an
**evaluation harness**, scores the **RAG triad** and the **agent trajectory** over a golden set and
watches for **silent failure (regression)** and **data drift**. It ships as a single lean Docker
container with embedded stores; the latest eval is at ceiling on the core metrics with no regression.

---

## 1 · The problem & thesis
- A 10-K = **narrative** (prose/tables) + **XBRL** (tagged numbers); two question types.
- Hard constraint: **fidelity** — a wrong number is worse than no answer. Generic PDF→chunks→LLM RAG
  hallucinates figures.
- **Thesis:** numbers → XBRL only; arithmetic → deterministic tool; narrative → retrieved + cited;
  an **agent** routes; a **validator** guards. *Fidelity over fluency.*
- **Sayable:** "The bar isn't 'sounds right' — it's 'the filed number, exactly.'"

## 2 · Domain: inline XBRL
- A 10-K is filed as **inline XBRL (iXBRL)** — one HTML doc that's human-readable *and* machine-tagged.
- **Who tags:** the registrant (JPMorgan) via filing software, against **FASB's US-GAAP** taxonomy
  (+ **DEI**), mandated by the **SEC** and submitted through **EDGAR**.
- **Who audits what:** **PwC** audits the *statements* (under **PCAOB**); the **XBRL tags themselves
  are generally NOT separately audited** — the filer's own assertion.
- So: **trust XBRL over parsed prose, but not blindly** — keep the most-precise of duplicate
  taggings, flag contradictions, skip "nil" (never coerce a false zero).
- **Code:** `src/ingestion/xbrl.py` (`_dedupe_facts`, `_build_fact`). **Sayable:** "The filer tags it
  against FASB's taxonomy via EDGAR; PwC audits the statements, not the tags."

## 3 · Data foundation & the firewall (§1.2)
- **Two streams, never mixed:** narrative `Element`s from the PDF; numeric `XBRLFact`s from iXBRL.
- **Docling** (layout model + TableFormer) parses the PDF into reading-order text/tables, run lean +
  **16-page windowing** to avoid OOM on a 300-page filing.
- **Arelle** (reference XBRL engine, used offline only) yields each figure as an exact **`Decimal`**
  (never float), with period (instant vs duration) and entity.
- `XBRLFact` is **constructed in exactly one module** → "the model can't invent a number" is
  *structural*, not hopeful.
- **Code:** `src/ingestion/elements.py`, `src/ingestion/xbrl.py`, `src/config/schema.py`.
  **Sayable:** "Numbers are built in one place, as Decimals — that single-constructor rule is the
  basis of trust."

## 4 · Chunking — structure-based sub-chunks
- Retrieval unit = the parser's **own block** (paragraph / heading / whole table), **not** fixed-size
  windows.
- Long blocks split into bounded **sub-chunks** for embedding — tables **row-wise, header repeated**
  so each piece is self-describing.
- Fixed a real bug: a 7.2k-char table was **~89% invisible** to its one truncated vector; now every
  part is embedded (verified: largest table → 7 sub-chunks).
- **Code:** `app/retrieval.py` (`_subchunks`, `_table_subchunks`, `_parent_expand`). **Sayable:** "We
  don't fixed-size chunk — the parser's blocks are the chunks, with long tables split so nothing
  falls out of the index."

## 5 · The two stores — truth + recall
- **DuckDB** (embedded SQL) holds the **facts** → exact keyed lookup (entity + concept + period). *For
  truth.* **Qdrant** (embedded vector DB) holds **sub-chunk embeddings** → semantic search + filters.
  *For recall.*
- **Both embedded / in-process** (no server), rebuilt from the baked JSONL/`.npy` at startup → stays a
  single lean container.
- **JSONL is still the source of truth**; the stores are query engines built *from* it — not a
  replacement. DuckDB is ACID-capable but used read-only/in-memory, so it's a fast analytical cache.
- **Code:** `app/duckdb_store.py`, `app/vector_store.py`. **Sayable:** "Qdrant for recall, DuckDB for
  truth — both embedded, both built from the JSONL at startup."

## 6 · Retrieval — hybrid + RRF + filters + parent-expansion
- **Hybrid:** BM25 (exact terms like "CET1") **+** Qdrant dense (paraphrase/meaning).
- Fused by **Reciprocal Rank Fusion** (`1/(60+rank)`, top-80 each) — rank-based, no score-scaling.
- **Metadata filtering:** `fiscal_year` is a Qdrant **payload filter** (year-scoped queries);
  `item`/`kind` are stored, so section filtering is one step away.
- **Parent-expansion:** each hit + its reading-order neighbors (same filing) for context.
- **Code:** `app/retrieval.py` (`hybrid_search`), `app/vector_store.py` (`dense_elements`).
  **Sayable:** "Keyword + meaning, fused by rank, scoped by a year filter, expanded for context."

## 7 · The context delivered to the agent
- The model never sees the raw corpus or vectors — only **tool-result strings**: narrative as
  `[FY2024 p.97] <≤500 chars>` (~18 passages); numbers as exact strings (`Total assets … FY2024:
  $4,002,814 million`).
- Small, targeted, **provenance-tagged** (year + page) → grounded, citable answers built **only** from
  retrieved evidence.
- **Code:** `app/agent.py` (`_tool_search`), `app/answer.py`. **Sayable:** "Its context is the tool
  outputs — year/page-tagged passages and exact figures — not a giant dump."

## 8 · The agent — framework, loop, tools, control
- **Raw OpenAI tool-calling** — a hand-written ~40-line loop, **no LangGraph/LangChain**. Routes via
  `tool_choice="auto"` (temp 0, ≤4 steps). **Single agent, 3 flat tools — no sub-agents, no
  progressive disclosure** (right for a 3-tool domain; trajectory stays inspectable → evaluable).
- **Tools:** `lookup_financial_fact` (DuckDB, exact); `compute` (**10 deterministic ops** —
  change/percent_change/cagr/average/sum/min/max + ratio/percent_of/difference, **no LLM math**);
  `search_filings` (Qdrant + BM25).
- **Validator** (deterministic): every figure in the answer must trace to a tool output — catches a
  hallucinated *or* hand-computed number. **Self-RAG** reflect→revise; **refusal** when no tool fits.
- **Code:** `app/agent.py` (`_tool_loop`, `_TOOLS`, `_tool_compute`, `_validate`, `_reflect`).
  **Sayable:** "The model orchestrates but never sources or computes a number — tools do, and the
  validator checks every one."

## 9 · Evaluation — two surfaces, three families
- **Two surfaces:** the **answer** *and* the **trajectory** (a right answer via a wrong path is a
  latent bug). Over a **17-item golden set** (all 5 FYs; numeric/narrative/refusal).
- **Family 1 — deterministic** (exact, zero variance): numeric_exact, retrieval_hit, tool_correct,
  year_scope_ok, validator_pass.
- **Family 2 — LLM-judge:** the **RAG triad** — **context relevance** (retrieved context on-topic?),
  **groundedness/faithfulness** (answer rooted in it?), **answer relevance** (addresses the query?) —
  **plus a trajectory judge** (tool appropriateness, efficiency, faithfulness).
- **Family 3 — monitoring:** **regression** (each aggregate vs a committed baseline; a drop >0.10 =
  silent failure) and **data drift** (a headline metric moving >30% YoY = "eyeball it," not an error).
- **Auto-triggerable** (`python app/evaluate.py`). **Code:** `app/evaluate.py` (`GOLDEN`,
  `_score_item`, `_judge`, `_judge_trajectory`, `_regression`, `_data_drift`).
- **Sayable:** "We score the answer and the path it took — deterministic exact-match, the RAG triad,
  a trajectory judge, and regression/drift monitoring."

## 10 · Deployment
- **One lean container:** no Docling/Arelle/torch at runtime — it carries *data*, not machinery.
- The baked corpus + the two **embedded** stores build at **startup** (~15 s, once; no re-parse, no
  re-embed). Verified: image builds, serves **HTTP 200**, both stores work in-container.
- **Code:** `Dockerfile`. **Sayable:** "Bake once, serve — a single container, verified end-to-end."

## 11 · Scope & honest edges
- **Entity (§1.3):** answers the **consolidated registrant, JPMorgan Chase & Co. (JPM)** only; the
  subsidiary **JPMorgan Chase Bank, N.A.** is ingested and kept **distinct** (never silently mixed) but
  **not exposed** — §1.3 honored by *separation*.
- **8 headline metrics** exposed to the agent (of ~1,098 tagged concepts); arbitrary-concept lookup is
  a clean future extension.
- **Same-model judge** (gpt-4o-mini judges itself) and a **small golden set** (17 → directional) are
  stated caveats; deterministic scorers anchor the suite.
- **Plan vs shipped:** the SDD docs describe a fuller M1–M10 plan; the demo shipped M1 + a focused
  serving layer with deliberate divergences (raw tool-calling not LangGraph; embedded stores not a
  Qdrant Docker server; sub-chunks not full hierarchical chunking).

---

## Key insights (the headline points)
1. **Fidelity is structural**, not hoped-for — numbers built in one XBRL constructor, served exactly
   from DuckDB, every figure checked by a validator.
2. **Two stores split by data type** — DuckDB for exact *truth*, Qdrant for semantic *recall* — both
   embedded, both built from the JSONL source of truth.
3. **Agentic but transparent** — a plain OpenAI tool-calling loop (no framework), so the trajectory is
   inspectable and therefore **evaluable**.
4. **Evaluation is co-equal** — two surfaces, the full RAG triad + a trajectory judge, and
   silent-failure/data-drift monitoring; the regression gate proved the store swap cost no quality.

## Anticipated Q&A
- **Why not LangChain/LangGraph?** Transparency + a 3-tool domain; the loop is ~40 readable lines and
  the trajectory is directly scorable.
- **Why DuckDB/Qdrant if in-memory was equivalent?** They're the designed architecture + scale-
  readiness + payload-filtered search; the eval proved the swap cost no quality.
- **How do you stop number hallucination?** Numbers built only in the XBRL path; no LLM arithmetic
  (the `compute` tool); a validator that flags any ungrounded figure.
- **Are you still using JSONL?** Yes — JSONL is the baked source of truth; the stores are built from it.
- **Same-model-judge bias?** Acknowledged; a stronger/independent judge is the next step. Deterministic
  scorers anchor the suite regardless.
- **What if a calculation isn't supported?** `compute` has 10 ops; beyond that the agent looks up raw
  values or refuses, and the validator catches a hand-computed number.
- **Do you answer for the bank subsidiary too?** No — consolidated registrant only; the subsidiary is
  kept distinct but not exposed (§1.3).

## Suggested report outline
1. **Problem & approach** (§1) — the fidelity bar; the firewall thesis.
2. **Data foundation** (§2–3) — iXBRL, Docling/Arelle, the §1.2 firewall, `Decimal`.
3. **Retrieval** (§4–7) — sub-chunking, the two stores, hybrid + RRF + filters, the agent's context.
4. **The agent** (§8) — framework, loop, the 3 tools, the validator, Self-RAG.
5. **Evaluation** (§9) — two surfaces, three families, the RAG triad, the trajectory judge, monitoring.
6. **Deployment & results** (§10) — embedded single-container, verified; the latest metrics.
7. **Scope, limitations & next** (§11) — consolidated-only, caveats, plan-vs-shipped, roadmap.

*Full code walkthrough: `docs/guide/` (00–07). Fact-by-fact notes: `gathered-context.md`. Slide deck +
speaker cue-card: `report.pdf` / `speaker-cues.pdf`.*
