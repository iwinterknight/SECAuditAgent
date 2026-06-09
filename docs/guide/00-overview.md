# 00 · System overview

## The problem

Answer questions over a company's **10-K filings** (here, JPMorgan Chase, FY2021–
2025) — both the **narrative** ("what does the firm say about credit risk?") and
the **exact financials** ("what was net income in 2024, and how did it change?").

A 10-K is ~300 pages of dense prose, tables, and footnotes, *plus* a parallel
machine-readable **XBRL** package of every figure the registrant tagged. The hard
constraint for financial QA is **fidelity**: a wrong number is worse than no
answer. A generic "PDF → chunks → LLM" RAG fails exactly here — language models
misread and hallucinate figures.

## The thesis

Split the two kinds of content and handle each with the right tool:

- **Numbers** come *only* from **XBRL** (exact, machine-readable, what the company
  filed) — never from the LLM. Arithmetic goes through a deterministic calc tool.
- **Narrative** is retrieved from the parsed text with citations (fiscal year, page).
- An **agent** routes each question to the right tool(s), and a **validator**
  checks that every figure in the answer is grounded in a tool result.

This is the spine of the whole system. Everything else serves it.

## End to end

```
            OFFLINE — build the corpus ONCE                 ONLINE — serve queries
  ┌───────────────────────────────────────────┐   ┌──────────────────────────────────┐
  │  10-K PDF  ── Docling ──▶ Elements ──┐     │   │  question                        │
  │            (layout+tables)           │     │   │     │                            │
  │  iXBRL     ── Arelle  ──▶ XBRLFacts ─┤     │   │     ▼                            │
  │            (exact figures)           │     │   │  AGENT (OpenAI tool-calling)     │
  │                                      ▼     │   │   router → tools → validator     │
  │              serialize → data/derived/*.jsonl  │   ├─ lookup_financial_fact (XBRL)│
  │              (deterministic JSONL, gitignored) │   ├─ compute_change   (calc)     │
  └───────────────────────────────────────────┘   │   ├─ search_filings   (hybrid)   │
                         │ (baked into the Docker image) │   reflect → revise (Self-RAG)│
                         └───────────────────────────▶   │     │                        │
                                                         │     ▼                        │
                                                         │  cited, validated answer     │
                                                         └──────────────────────────────┘
                                                  EVALUATION runs the agent over a golden
                                                  set (triad + trajectory + drift/regression).
```

> **Where the stores fit:** at serving time the baked `*.jsonl` + `*.npy` are loaded
> **in-process** into the two embedded stores the tools query — **DuckDB** for the exact
> XBRL facts, **Qdrant** for the sub-chunk vectors (alongside BM25) — so the JSONL stays
> the source of truth and there's still no server. See [07 · The stores](07-stores.md).

## Two layers (why it's structured this way)

- **Offline ingestion (parse once).** Parsing a 300-page PDF with ML layout/table
  models is slow (~12–25 min/filing on CPU). So it runs **once**; the output —
  normalized `Element`s and exact `XBRLFact`s as JSONL — is the *corpus*. See
  [01 · Data foundation](01-data-foundation.md).
- **Online serving (read only).** The app and the Docker image **only read** the
  pre-built corpus. They never parse a PDF at request time. The corpus is baked
  into the image (doc 05) — that's the "bake-once-reuse" deployment model.

This split is also why the demo is fast and the Docker image is lean (no Docling,
Arelle, or torch at runtime).

## The building blocks

| Block | Module | One-liner |
|---|---|---|
| Ingestion | `src/ingestion/*` | PDFs + XBRL → the corpus (doc 01) |
| Retrieval | `app/retrieval.py` | hybrid **Qdrant** dense + BM25 sparse, RRF, parent-expansion, year filter (docs 02, 07) |
| Stores | `app/duckdb_store.py`, `app/vector_store.py` | **DuckDB** (facts) + **Qdrant** (sub-chunk vectors), embedded, built from the baked JSONL/`.npy` at startup (doc 07) |
| Agent | `app/agent.py` | 3-tool loop + validator + self-correction (doc 03) |
| Evaluation | `app/evaluate.py` | golden set, triad, trajectory, drift/regression (doc 04) |
| UI / Docker | `app/ui.py`, `Dockerfile` | Streamlit chat + dashboard, baked image (doc 05) |

## How to run

```bash
# 1. key (gitignored)
echo "OPENAI_API_KEY=sk-..." > .env

# 2. local — the chat + evaluation UI
.venv/Scripts/python.exe -m streamlit run app/ui.py     # http://localhost:8501

# 3. the evaluation suite (CLI, cron-able)
.venv/Scripts/python.exe app/evaluate.py

# 4. Docker (bakes the corpus)
docker build -t jpm-10k-demo . && docker run --rm -p 8501:8501 --env-file .env jpm-10k-demo
```

> The corpus (`data/derived/`) must exist before serving. It's produced by the
> ingestion pipeline (`python -m ingestion.pipeline`) — see doc 01. For the demo
> it's already built and baked into the Docker image.

## A note on process

The **ingestion** half was built under a strict **Spec-Driven Development** (SDD)
framework — a constitution (`docs/constitution.md`), an architecture map
(`docs/architecture.md`), and per-task educator reports (`reports/`). The **demo**
half (agent, eval, UI, Docker) was built fast on top of that foundation. Doc 06
explains the framework and why it was front-loaded.
