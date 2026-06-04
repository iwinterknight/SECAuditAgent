# AuditAgent

An **Agentic RAG** system + **evaluation** harness that answers questions
about **JPMorgan Chase & Co.** 10-K filings (FY2021–FY2025) with high
financial accuracy.

> Status: **M0 — scaffolding.** No application code yet. The framework,
> principles, and module roadmap are being laid down first, Spec-Driven.

## What it does (target)

Ask a financial question about the filings — a lookup ("CET1 ratio in
2024?"), a comparison ("change in net charge-offs 2024→2025"), a trend, a
risk-narrative question, or a multi-hop synthesis — and get a **cited,
grounded** answer. Numbers come from machine-readable XBRL facts, not from
an LLM reading a table. A validator gate checks grounding, entity, and
numeric correctness before the answer is returned. A decoupled evaluation
harness continuously scores quality and flags drift and silent failures.

## How it's built

- **Ingestion** — layout/table-aware PDF parsing + EDGAR XBRL facts.
- **Chunking** — hierarchical parent/child chunks, table-to-text
  summaries, financial metadata (section, metric, entity, period).
- **Index** — Qdrant (vectors) + DuckDB (XBRL facts).
- **Retrieval** — hybrid (dense + sparse + metadata filter) + rerank +
  parent expansion.
- **Agent** — LangGraph: router → {vector tool, numeric/calc tool} →
  validator/critic.
- **Evaluation** — RAG triad + agent-loop metrics + drift detection,
  auto-scheduled.

The ratified stack and the full module map are in
[`docs/architecture.md`](docs/architecture.md).

## Working on this project

This project uses Spec-Driven Development. Start with
[`AGENTS.md`](AGENTS.md), then [`docs/constitution.md`](docs/constitution.md)
and [`docs/roadmap.md`](docs/roadmap.md). Every change flows
CLARIFY → PLAN → TASKS → IMPLEMENT → EVALUATE.

## Data

Raw 10-K PDFs live under `data/SEC/10-K Filings/yearly/` and are versioned
with **Git LFS**. Install Git LFS before cloning:

```
git lfs install
git clone <repo-url>
```

## Local setup

Documented per module as code lands (see `docs/roadmap.md`). Nothing to run
yet.
