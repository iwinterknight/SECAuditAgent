# 04 · Evaluation — proving the system works

> Code: `app/evaluate.py`. Entry point: `run_eval()`; CLI: `python app/evaluate.py`.
> This is the **second main deliverable** (co-equal with the agent), because an
> Agentic RAG you can't measure is one you can't trust or improve.

## What has to be tested (two surfaces, not one)

An agentic RAG has two things that can each be right or wrong independently:

1. **The answer** — is the number exact? is the claim grounded? is it relevant?
2. **The trajectory** — did the agent take the *right path*? (correct tools, no
   waste, faithful use of what the tools returned).

A good answer reached by a lucky wrong path is a latent bug. So we score **both**.

## The golden set — what a "golden item" is

A small, curated list of questions with known-good expectations. Each item declares
its `kind` and what success means:

```python
# numeric — exact figure + which tool should produce it
{"id": "assets_2024", "q": "What were total assets at year-end 2024?",
 "kind": "numeric", "expect_number": "4,002,814", "expect_tool": "lookup_financial_fact"}

# narrative — a topical keyword that must surface, + (optionally) a year to scope to
{"id": "capital_2022", "q": "According to the FY2022 10-K, what does JPMorgan discuss about capital?",
 "kind": "narrative", "expect_keywords": ["capital"], "expect_tool": "search_filings",
 "expect_year": 2022}

# refusal — the right behavior is to decline
{"id": "future_price", "q": "What was the share price on March 1, 2026?", "kind": "refusal"}
```

**Coverage of all 5 years is deliberate** (it's what prompted the latest work): one
exact-figure item per fiscal year (total assets FY2021→FY2025), plus other metrics,
plus cross-year & average `compute` items, plus two **year-scoped** narrative items, plus
refusal — **17 items** spanning every filing.

## Three layers of scoring

### Layer 1 — deterministic scorers (cheap, exact, no LLM)

Run on every item; the bedrock of the eval because they have no judge variance:

- **`numeric_exact`** — does the answer contain the exact XBRL figure?
- **`retrieval_hit`** — did retrieval surface a passage with the expected keyword?
- **`tool_correct`** — was `expect_tool` actually in the tools the agent used?
- **`year_scope_ok`** — for year-scoped items, are the retrieved sources actually from
  `expect_year`? (≥50% must be.) This is what makes "all 5 years" *verified*, not claimed.
- **`validator_pass`** — the agent's own deterministic groundedness check (doc 03) passed.

### Layer 2 — the RAG triad (LLM-as-judge)

The full triad, scored by a judge model reading the question, the retrieved context, and
the answer:

- **`context_relevance`** — is the retrieved CONTEXT relevant to the question (vs off-topic
  noise the model could weave into a hallucination)?
- **`groundedness`** (faithfulness) — is the answer fully rooted in that context (no
  invented, exaggerated, or distorted facts)?
- **`answer_relevance`** — does the answer directly and helpfully address the question?

(`retrieval_hit` + `year_scope_ok` from Layer 1 stay on as complementary *deterministic*
retrieval checks — a keyword/recall signal alongside the judged context relevance.)

### Layer 3 — the trajectory judge (LLM-as-judge over the *path*)

The novel, agent-specific layer. The judge reads the **trace** (`[{tool, args}…]`) and
the tool outputs and scores the *behavior*:

- **`tool_appropriateness`** — were the right tools chosen for this question?
- **`trajectory_efficiency`** — any redundant or wasteful calls?
- **`answer_faithfulness`** — does the final answer use the tool outputs correctly
  (no drift between what a tool returned and what was stated)?

This is what turns the agent from a black box into something you can audit.

## Monitoring — catching the failures that hide

Aggregate scores can stay green while something rots. Two monitors guard against that:

- **Regression / silent failure** — aggregates are compared against a committed
  **baseline** (`eval/baseline.json`); any metric dropping past `REGRESSION_TOL` (0.10)
  is flagged. This catches a prompt/model/retrieval change that quietly degrades
  quality without throwing an error.
- **Data drift** — the headline XBRL series are scanned year-over-year; a move past
  `DRIFT_TOL` (0.30 = 30%) is flagged. This is *data* drift, not model drift: e.g. "Net
  income +31.5% FY22→FY23" surfaces as a flag. It's intentionally **not** an error — a
  real rate-cycle jump *should* be flagged for a human to confirm vs. an ingestion bug.

## Auto-triggerable

```bash
python app/evaluate.py     # writes eval/last_report.json + eval/runs/<timestamp>.json
```

No UI needed — it's a plain CLI, so it drops into cron / CI / a scheduler. The UI's
Evaluation tab (doc 05) renders the same `last_report.json`.

## Latest run — 17 items, all 5 fiscal years

```
numeric_exact 1.0 · retrieval_hit 1.0 · year_scope_accuracy 1.0 · validator 1.0
context_relevance 1.0 · groundedness 1.0 · answer_relevance 1.0   ← the RAG triad
tool_appropriateness 0.94 · trajectory_efficiency 0.88 · answer_faithfulness 0.99
regression: none · data-drift: 3 flagged (real YoY moves)
```

Read these as: figures exact across every year; narrative scoped to the right filing;
every stated number grounded; the agent picks the right tools and uses them faithfully;
efficiency 0.88 reflects the occasional extra call from the reflect→revise pass — a
deliberate quality-for-cost trade, visible because the trajectory is scored.

→ Next: [05 · Deployment](05-deployment.md) — the chat UI and the baked Docker image.
