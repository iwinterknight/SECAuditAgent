# JPMorgan Chase 10-K — Agentic RAG + Evaluation (demo)

An **agentic RAG** chat system over JPMorgan Chase's last five 10-K filings
(FY2021–FY2025), plus an **evaluation component** that scores the system end-to-end
and watches for silent failure and data drift. Local; Streamlit chat UI; Dockerized.

The brief's two main components:
1. **Agentic RAG** — a multi-tool agent with a self-correcting loop (not a fixed pipeline).
2. **Evaluation** — golden-set scoring of the RAG triad *and* the agent trajectory, plus drift / regression monitoring.

---

## 1. The Agentic RAG

A 10-K mixes **narrative** (risk factors, MD&A) with **exact financials**. Those need
different handling, so the agent gets **three tools** and decides — per query — which
to use (the router), loops over them, **self-critiques and revises** if the answer
isn't grounded (Self-RAG), then a **validator** checks every figure.

| Tool | Backed by | Used for |
|---|---|---|
| `lookup_financial_fact(metric, year?)` | **exact XBRL facts** (FY2021–2025) | any financial number — from XBRL, never the model |
| `compute_change(metric, y1, y2)` | **deterministic math** over XBRL facts | changes / growth / comparisons — exact arithmetic, not LLM math |
| `search_filings(query)` | **hybrid retrieval** (dense + sparse RRF + parent-expansion) over 3,610 FY2024 Elements | "what does the filing say" |

**The loop (`app/agent.py`):**
- **Router** — OpenAI tool-calling picks numeric / narrative / both. *"How did total assets change 2021→2025?"* → 5 fact-tool calls.
- **Self-RAG reflect→revise** — a critic checks the answer is grounded in the tool outputs and complete; if not, the agent gets the critique and another turn (re-search with a sharper query, or look up a missing figure).
- **Validator** — every number stated must appear in a tool output (an exact XBRL fact or a `compute_change` result); an unmatched number is flagged (catches hallucinated *or hand-computed* figures).
- **Refusal path** — an unanswerable question (e.g. a future share price) → no tools called, declines rather than inventing.

**RAG techniques chosen for 10-Ks (and why):**
- **Numbers from XBRL, never the LLM** — the most error-prone content (figures) is served exact from the machine-readable filing; arithmetic goes through a deterministic calc tool. This is the fidelity keystone for financial QA.
- **Hybrid retrieval** — dense embeddings (semantic) fused with BM25 (keyword) via **Reciprocal Rank Fusion**; 10-K queries span both exact terms ("CET1") and paraphrase.
- **Parent-expansion** — each hit is expanded with its reading-order neighbors for fuller local context (the useful half of CAG, without stuffing the whole corpus into the prompt). *(CAG itself doesn't fit — five 10-Ks is ~1M+ tokens.)*
- **Self-RAG / corrective retrieval** — the agent re-queries when retrieval is weak.

---

## 2. The Evaluation component (`app/evaluate.py`)

Runs the agent over a **golden set** and scores both the answer and the *agentic* behavior:

**Answer quality (RAG triad + fidelity), per item:**
- `numeric_exact` (deterministic) — contains the exact XBRL figure.
- `retrieval_hit` (deterministic) — retrieval surfaced a relevant passage.
- `groundedness`, `answer_relevance` (LLM-judge) — the RAG triad.
- `validator_pass` — every figure grounded in a tool output.

**Agent trajectory (LLM-judge over the tool-use path):**
- `tool_appropriateness` — right tools chosen for the question?
- `trajectory_efficiency` — no redundant/wasteful calls?
- `answer_faithfulness` — answer uses the tool outputs correctly (no drift)?

**Monitoring:**
- **regression / silent-failure** — aggregates vs a committed **baseline**; a drop past tolerance is flagged.
- **data drift** — headline XBRL series scanned for year-over-year moves past tolerance.

**Latest run (gpt-4o-mini, 10 items):** numeric_exact, retrieval_hit, groundedness,
validator, tool_accuracy = **1.0**; answer_relevance 0.95; trajectory
appropriateness 0.90 / efficiency 0.88 / faithfulness 0.90; 0 regressions; 3 drift
flags (e.g. Net income +31.5% FY22→FY23 — a real rate-cycle jump).

**Auto-triggerable** (cron / scheduler):
```bash
python app/evaluate.py     # writes eval/last_report.json + eval/runs/<ts>.json
```

---

## Files

```
app/answer.py     data layer: load the derived corpus + headline XBRL facts table
app/retrieval.py  hybrid retrieval — dense + sparse (RRF) + parent-expansion, embedding cache
app/agent.py      the agent: 3 tools + tool-calling loop + Self-RAG reflect/revise + validator
app/evaluate.py   evaluation: golden set, RAG-triad + trajectory scorers, drift, regression, CLI
app/ui.py         Streamlit: Chat tab (agent) + Evaluation dashboard tab
Dockerfile        lean image that BAKES the pre-built corpus + embeddings (no parser at runtime)
src/              the M1 ingestion pipeline that produced the corpus (Docling parse + Arelle XBRL)
data/derived/     parse-once corpus: Elements + XBRL facts + embeddings (gitignored)
```

The heavy ingestion ran **once** to build `data/derived/`; the app and the Docker
image only **read** it — they never parse a PDF at runtime.

---

## Run it

**Local:**
```bash
echo "OPENAI_API_KEY=sk-..." > .env          # gitignored
.venv/Scripts/python.exe -m streamlit run app/ui.py     # -> http://localhost:8501
```

**Docker** (start Docker Desktop first):
```bash
docker build -t jpm-10k-demo .
docker run --rm -p 8501:8501 --env-file .env jpm-10k-demo
```

## Try asking
- *What was net income in 2024, and how does it compare to 2023?* → looks up both + `compute_change`
- *How did total assets change from 2021 to 2025?* → 5-year series
- *What does JPMorgan say about credit risk?* → cited (FY2024, p.123)
- *What was the share price on a future date?* → refuses (no fabrication)
