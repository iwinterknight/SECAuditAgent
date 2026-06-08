# JPMorgan Chase 10-K — Agentic RAG + Evaluation (demo)

An **agentic RAG** chat system that answers questions over JPMorgan Chase's last
five 10-K filings (FY2021–FY2025), plus an **evaluation component** that scores the
system and watches for silent failure and data drift. Built locally; chat UI in
Streamlit; packaged for Docker.

The two deliverables the brief calls out as the *main* components:

1. **Agentic RAG** — a tool-calling agent (not a fixed RAG pipeline).
2. **Evaluation** — golden-set scoring + drift / regression monitoring.

---

## What makes it *agentic* (and accurate on 10-Ks)

A 10-K mixes **narrative** (risk factors, MD&A) with **exact financials**. Those
need different handling, so the agent is given **two tools** and decides — per
query — which to use (the router), calls them in a loop, then a **validator**
checks the figures:

| Tool | Backed by | Used for |
|---|---|---|
| `lookup_financial_fact(metric, year?)` | **exact XBRL facts** (FY2021–2025) | any financial number — figures come from XBRL, **never the model** |
| `search_filings(query)` | **BM25** over 3,610 parsed FY2024 Elements | narrative / "what does the filing say" |

- **Router** — the LLM (OpenAI tool-calling) picks numeric vs. narrative vs. both.
  *"How did total assets change 2021→2025?"* makes the agent call the fact tool
  **five times**, once per year.
- **Validator** — after answering, every headline figure stated is checked against
  an exact XBRL fact; an unmatched number is flagged (guard against hallucination).
- **Refusal path** — for an unanswerable question (e.g. a future share price) the
  agent calls **no tools** and declines rather than inventing.

**Why this fits 10-Ks (RAG technique):** the document's most error-prone content —
the numbers — is taken out of the LLM's hands entirely and served from the
machine-readable **XBRL** the registrant filed, exact to the dollar. Narrative is
retrieved with citations (FY, page). This is the fidelity keystone for financial QA.

---

## The evaluation component

`app/evaluate.py` runs the agent over a **golden set** and scores:

- **numeric_exact** (deterministic) — the answer contains the exact XBRL figure.
- **tool_correct** (agentic) — the agent routed to the expected tool.
- **retrieval_hit** (deterministic) — retrieval surfaced a relevant passage.
- **groundedness / answer_relevance** (LLM-judge) — the RAG triad.

…and adds the *monitoring* the brief asks for:

- **regression / silent-failure** — aggregates are compared to a committed
  **baseline**; a drop beyond a tolerance is flagged (a metric degrading quietly).
- **data drift** — the headline XBRL series is scanned for year-over-year moves
  beyond a tolerance (a concept/data-drift signal to review).

**Latest run:** numeric_exact, tool_accuracy, retrieval_hit, groundedness,
answer_relevance, validator_pass = **1.0**; 0 regressions; 3 drift flags
(e.g. Net income +31.5% FY22→FY23 — a real rate-cycle jump).

**Auto-triggerable** (cron / scheduler):

```bash
python app/evaluate.py          # writes eval/last_report.json + eval/runs/<ts>.json
```

---

## Files

```
app/answer.py     data layer: load the derived corpus, BM25 index, headline XBRL facts
app/agent.py      the agent: tools + OpenAI tool-calling loop + validator
app/evaluate.py   the evaluation component: golden set, scorers, drift, regression, CLI
app/ui.py         Streamlit: Chat tab (agent) + Evaluation dashboard tab
Dockerfile        lean image that BAKES the pre-built corpus (no parser at runtime)
src/              the ingestion pipeline that produced the corpus (M1: parse + XBRL)
data/derived/     the parse-once corpus (Elements + XBRL facts JSONL) — gitignored
```

The heavy ingestion (Docling PDF parse + Arelle XBRL) ran **once** to build
`data/derived/`; the app and the Docker image only **read** it — they never parse a
PDF at runtime.

---

## Run it

**Local:**
```bash
echo "OPENAI_API_KEY=sk-..." > .env          # gitignored
.venv/Scripts/python.exe -m streamlit run app/ui.py
# -> http://localhost:8501   (Chat + Evaluation tabs)
```

**Docker** (start Docker Desktop first):
```bash
docker build -t jpm-10k-demo .
docker run --rm -p 8501:8501 --env-file .env jpm-10k-demo
# -> http://localhost:8501
```

## Try asking
- *What was net income in 2024?* → exact `$58,471M`, via the fact tool
- *How did total assets change from 2021 to 2025?* → 5-year series
- *What does the filing say about credit risk?* → cited (FY2024, p.123)
- *What was the share price on a future date?* → refuses (no fabrication)
