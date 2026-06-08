# AuditAgent — Project Guide

A top-down tour of the system, building block by building block. Read in order for
the full picture, or jump to a block. Each doc teaches the *why* (the domain, the
trade-off) before the *what* (the code), so you can present at any level of detail.

| # | Doc | What it covers |
|---|---|---|
| 00 | [System overview](00-overview.md) | The whole pipeline end to end, the two layers, the fidelity thesis, how to run |
| 01 | [Data foundation](01-data-foundation.md) | 10-K PDFs + inline XBRL → `Element`s + `XBRLFact`s; Docling, Arelle, the §1.2 firewall, the JPM Exhibit-13 finding |
| 02 | [Retrieval](02-retrieval.md) | Hybrid (dense + sparse) RRF, parent-expansion, the year filter, why CAG doesn't fit, RAG techniques for 10-Ks |
| 03 | [The agent](03-agent.md) | The 3-tool agentic loop, router, validator, Self-RAG reflect→revise, refusal, no-LLM-arithmetic |
| 04 | [Evaluation](04-evaluation.md) | Golden set, RAG triad, trajectory LLM-judge, year coverage, drift + regression, auto-trigger |
| 05 | [Deployment](05-deployment.md) | The Streamlit chat UI and the bake-once-reuse Docker image |
| 06 | [Decisions & lessons](06-decisions-and-lessons.md) | The fidelity philosophy, the SDD framework, the memory/OOM saga, trade-offs |

### Where the code lives

```
src/            the ingestion pipeline (parse PDFs + extract XBRL → the corpus)
  config/       the typed contracts (Element, XBRLFact) + settings
  ingestion/    elements.py (PDF), xbrl.py (XBRL), sections.py (Items),
                serialize.py (JSONL), pipeline.py (the join + rebuild)
app/            the demo (reads the pre-built corpus, never re-parses)
  answer.py     load corpus + headline XBRL facts table
  retrieval.py  hybrid retrieval (dense + sparse + parent-expansion + year filter)
  agent.py      the agentic loop (tools, validator, reflect→revise)
  evaluate.py   the evaluation component
  ui.py         the Streamlit chat + evaluation dashboard
docs/           constitution.md (the law), architecture.md (the map),
                roadmap.md (the milestones), guide/ (this guide)
reports/        per-task educator reports from the SDD ingestion build (M1)
data/derived/   the parse-once corpus (Elements + XBRL facts + embeddings) — gitignored
DEMO.md         the quick-start README
```

### The one idea to hold onto

Every **financial number** the system answers with comes from the registrant's
machine-readable **XBRL**, exact to the dollar — never from the language model.
Narrative is retrieved and cited. That separation (doc 01's "§1.2 firewall") is the
whole reason this is trustworthy for financial QA.
