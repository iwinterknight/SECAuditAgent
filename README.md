# AuditAgent — JPMorgan 10-K Agentic RAG + Evaluation

An **Agentic RAG** system **and** a co-equal **evaluation** harness that answer questions over
**JPMorgan Chase & Co.'s** last five 10-K filings (FY2021–FY2025) — both exact financials and
narrative — built so a financial number is **exact or absent, never plausibly wrong**.

> **Status: built & runnable.** A working demo: agentic RAG (3 tools, hybrid retrieval,
> self-correction, a validator) + an evaluation suite (RAG triad + agent-trajectory judge +
> regression/drift monitoring) + a Streamlit chat UI + a verified Docker image, on top of the
> **M1 ingestion** foundation (a parse-once corpus of all 5 filings).

## The two deliverables

1. **Agentic RAG** — an OpenAI tool-calling agent that routes each question to the right tool,
   self-corrects (Self-RAG reflect→revise), and is checked by a deterministic validator.
2. **Evaluation** — a golden-set harness scoring the **RAG triad** (context relevance,
   groundedness, answer relevance) **and** the **agent trajectory** (tool appropriateness,
   efficiency, faithfulness), plus **silent-failure (regression)** and **data-drift** monitoring.
   Auto-triggerable (`python app/evaluate.py`).

## What it answers

- **Numbers** come only from the registrant's machine-readable **XBRL** (exact, `Decimal`) — via a
  DuckDB lookup + a deterministic `compute` tool (10 ops) — **never from the LLM**.
- **Narrative** is retrieved (hybrid) and cited as `(FY<year>, p.<page>)`.
- **Scope:** the **consolidated registrant, JPMorgan Chase & Co. (JPM)** — *not* the subsidiary
  JPMorgan Chase Bank, N.A., whose facts are ingested and kept distinct (§1.3) but not exposed. **8
  headline metrics** are wired to the agent (of ~1,098 tagged concepts).

## Architecture (as shipped)

```
OFFLINE (once)                BAKED ARTIFACTS                  AT STARTUP  →  ONLINE
──────────────                ───────────────                  ──────────────────────
PDF   → Docling → Elements ─┐                                  question
iXBRL → Arelle  → XBRLFacts ┴─ serialize → *.jsonl + *.npy ──▶ built in-process into:
                              (the deterministic source         DuckDB · Qdrant · BM25   (embedded)
                               of truth, baked into the image)         │
   AGENT (OpenAI tool-calling, temp 0):                                ▼
     • lookup_financial_fact / compute  → DuckDB  (exact facts, SQL)
     • search_filings → hybrid: Qdrant (sub-chunk vectors) + BM25 → RRF → year filter → parent-expand
     • Self-RAG reflect→revise → validator (every figure traces to a tool output) → cited answer
   EVALUATION: golden set → RAG triad + trajectory judge + regression-vs-baseline + YoY data-drift
```

- **Ingestion (offline, `src/ingestion/`):** Docling (layout + TableFormer, 16-page windowing) +
  Arelle (exact XBRL) → two typed streams as deterministic **JSONL** — the **§1.2 firewall** (figures
  are constructed in one place, never read from prose).
- **Stores (embedded, `app/duckdb_store.py` · `app/vector_store.py`):** **DuckDB** for exact facts
  ("for truth"), **Qdrant** for sub-chunk vectors ("for recall") — both **in-process** (no server),
  rebuilt from the baked JSONL/`.npy` at startup, so it stays one lean container.
- **Retrieval (`app/retrieval.py`):** hybrid **BM25 + Qdrant dense** over structure-based
  **sub-chunks** (tables row-split with repeated headers), fused by **RRF**, with a **fiscal-year
  payload filter** and **parent-expansion**.
- **Agent (`app/agent.py`):** raw **OpenAI tool-calling** — a hand-written loop, **not LangGraph** —
  3 tools, `temperature=0`, a Self-RAG critic pass, and a deterministic **validator**.
- **Evaluation (`app/evaluate.py`):** deterministic scorers (numeric-exact, retrieval-hit,
  year-scope, validator) + the LLM-judged triad + a trajectory judge + regression + drift.

## Run it

Prereqs: a repo-root **`.env`** with `OPENAI_API_KEY=sk-...`, and the baked corpus at
`data/derived/ingestion/` (shipped with the repo).

```bash
# the chat UI + evaluation dashboard  → http://localhost:8501
.venv/Scripts/python.exe -m streamlit run app/ui.py

# the evaluation suite (CLI, cron-able)
.venv/Scripts/python.exe app/evaluate.py

# Docker — lean image; the embedded stores build from the baked corpus at startup
docker build -t jpm-10k-demo . && docker run --rm -p 8501:8501 --env-file .env jpm-10k-demo

# (rarely) rebuild the parse-once corpus from the source PDFs + iXBRL
.venv/Scripts/python.exe -m ingestion.pipeline
```

Tests: `.venv/Scripts/python.exe -m pytest -q` (offline unit tests for chunking, the stores, the
compute tool, parent-expansion, and the M1 contracts).

## Documentation map

- **[`DEMO.md`](DEMO.md)** — quick-start overview of the demo.
- **[`docs/guide/`](docs/guide/README.md)** — the deep, building-block walkthrough (00 overview →
  07 stores), high→low, every claim pointing at the code.
- **[`docs/presentation/`](docs/presentation/)** — a ~40-min panel **report** + a **speaker
  cue-card** (Markdown + PDF), plus the gathered fact-by-fact notes.
- **Design & process (Spec-Driven Development):** [`docs/constitution.md`](docs/constitution.md)
  (the law — fidelity principles), [`docs/architecture.md`](docs/architecture.md) (the target-state
  map), [`docs/roadmap.md`](docs/roadmap.md) (the M0–M10 plan), [`AGENTS.md`](AGENTS.md) (the SDD
  workflow + project memory).

> **Plan vs. shipped.** The SDD design docs describe a fuller **M1–M10** plan. The demo, built to a
> tight time budget, shipped **M1 ingestion** + a focused serving layer, with three deliberate
> divergences from the original plan: **raw OpenAI tool-calling** (not LangGraph), **embedded**
> DuckDB/Qdrant (not a Qdrant Docker server), and structure-based **sub-chunks** (not full
> hierarchical chunking). The rationale is in `docs/guide/06` and `docs/guide/07`.

## Data

Raw 10-K PDFs live under `data/SEC/10-K Filings/yearly/` and the iXBRL packages under
`.../xbrl/<accession>/`, versioned with **Git LFS** (install `git lfs` before cloning). The
parse-once corpus + embeddings under `data/derived/` are gitignored but **baked into the Docker
image**.
