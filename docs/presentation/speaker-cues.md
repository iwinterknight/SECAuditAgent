# Speaker cue-card — JPMorgan 10-K Agentic RAG

**How to use:** glance the **Say** line, say it in your own words, then open the **Code** file if a panelist
wants to see it. One line per slide — that's it.

| # | Min | Say (one line) | Code: open this file |
|---|---|---|---|
| 1 | 1 | Two deliverables — agent + evaluation — one principle: **fidelity over fluency**. | — |
| 2 | 2 | A wrong number is worse than none; generic "PDF→chunks→LLM" RAG fails on figures. | — |
| 3 | 2 | Offline parse → **JSONL** → embedded stores → agent → eval. Heavy work runs once. | `docs/guide/00-overview.md` (diagram) · `src/ingestion/pipeline.py` |
| 4 | 3 | Filer tags it in iXBRL (FASB/SEC/EDGAR); **PwC audits the statements, not the tags** — so we defend. | `src/ingestion/xbrl.py` → `_dedupe_facts`, `_build_fact` |
| 5 | 3 | Two streams, **firewall**: Docling→Elements (16-page windows), Arelle→facts (**Decimal**). | `src/ingestion/elements.py` → `parse_elements` · `src/config/schema.py` |
| 6 | 2 | **Structure-based sub-chunks**; tables split row-wise w/ header — fixed the ~89% table truncation. | `app/retrieval.py` → `_subchunks`, `_table_subchunks` |
| 7 | 3 | **DuckDB = truth, Qdrant = recall**, both embedded, built from the JSONL at startup. | `app/duckdb_store.py` · `app/vector_store.py` |
| 8 | 3 | Hybrid **BM25 + dense**, fused by **RRF**, **year payload-filter**, then **parent-expand**. | `app/retrieval.py` → `hybrid_search`, `_parent_expand` |
| 9 | 2 | The agent only sees **tool outputs**: `[FY p.]` passages + exact figures — not the raw corpus. | `app/agent.py` → `_tool_search` |
| 10 | 3 | **Raw OpenAI tool-calling**, hand-written loop, **no LangGraph**; one agent, 3 flat tools. | `app/agent.py` → `_tool_loop`, `_TOOLS` |
| 11 | 3 | Numbers only from tools; `compute` = **10 deterministic ops**; **validator** checks every figure. | `app/agent.py` → `_tool_compute`, `_validate`, `_reflect` |
| 12 | 3 | We score **two surfaces** (answer + trajectory), 17-item golden set, **3 families**. | `app/evaluate.py` → `GOLDEN`, `_score_item` |
| 13 | 3 | The **RAG triad** (context-rel, groundedness, answer-rel) **+** a **trajectory judge**. | `app/evaluate.py` → `_judge`, `_judge_trajectory` |
| 14 | 2 | **Regression** vs baseline = silent failure; **drift** >30% YoY = "eyeball it", not an error. | `app/evaluate.py` → `_regression`, `_data_drift` |
| 15 | 2 | Core metrics **all 1.0**, **no regression**, tests green. | `eval/last_report.json` · `tests/unit/` |
| 16 | 1 | **One lean container**, embedded stores, **verified HTTP 200** in-container. | `Dockerfile` |
| 17 | 1 | Stores = completeness + scale-readiness (eval proved no cost); same-model judge; 8 of ~1,098 metrics. | `docs/guide/06-decisions-and-lessons.md` |
| 18 | 1 | Fidelity structural · two stores · transparent agent · **evaluation co-equal**. | — |

---

## If asked — quick answers

- **Why not LangChain / LangGraph?** Transparency + a 3-tool domain; the whole loop is ~40 readable lines and the trajectory is directly inspectable/scorable. → `app/agent.py`
- **Why DuckDB/Qdrant if in-memory was equivalent?** They're the *designed* architecture + scale-readiness + payload-filtered search; the **eval proved the swap cost no quality**. → `docs/guide/07-stores.md`
- **How do you stop number hallucination?** Three layers: numbers built **only** in the XBRL path; **no LLM arithmetic** (the `compute` tool); a **validator** that flags any ungrounded figure. → `app/agent.py:_validate`
- **Are you still using JSONL?** Yes — JSONL is the **baked source of truth**; DuckDB/Qdrant are query engines built *from* it at startup.
- **Same-model-judge bias?** Acknowledged caveat (gpt-4o-mini judges itself); next step is a stronger/independent judge. Deterministic scorers anchor the suite regardless.
- **What if a calculation isn't supported?** `compute` has 10 ops; beyond that the agent looks up raw values or refuses, and the validator catches a hand-computed number. → `app/agent.py:_tool_compute`

## Optional live demo (≈2 min)
1. *"How did total assets change from 2021 to 2025, and what does the filing say about capital?"* → show the **trace** (compute + search), the **sources** (FY/page), the **validator ✅**.
2. *"What was the share price on a future date?"* → the agent **refuses** (no tool can answer).
3. Switch to the **Evaluation** tab → the triad + trajectory metrics, the regression/drift lines.
