# 06 · Decisions & lessons — the why behind the how

The nuances that don't live in any one module: the philosophy, the process, the
trade-offs, and the war stories.

## The through-line: fidelity over fluency

Every significant choice serves one goal — **a financial answer must be exact or
absent, never plausibly wrong.** Pulling the thread through the system:

| Layer | The fidelity mechanism |
|---|---|
| Contracts (01) | `XBRLFact` defined + constructed in *one* place; `Decimal` not `float`; period-blend rejected at construction; entity kept distinct |
| Agent (03) | numbers only from `lookup_financial_fact`; arithmetic only via `compute`; refuse when no tool can answer |
| Validator (03) | deterministic check: every stated number must trace to a tool output |
| Eval (04) | `numeric_exact`, `validator_pass`, `groundedness`, `faithfulness` all measure fidelity directly |

If you present one idea, present this one. Generic RAG optimizes for a fluent answer;
this system optimizes for a *correct* one and treats fluency as secondary.

## Process: Spec-Driven Development, then a deliberate pivot

The **ingestion** foundation (M1) was built under strict **SDD**:

- **`docs/constitution.md`** — the law (e.g. §1.2 the numbers firewall, §1.3 entity/
  period rules, §1.6 imports flow downward). Non-negotiable invariants.
- **`docs/architecture.md`** — the layer map and module boundaries.
- **`docs/roadmap.md`** — milestones M1…M10 as a dependency chain.
- **`reports/`** — a per-task educator report after each step (high→low teaching).

Why front-load this for a data foundation: a fidelity bug in ingestion silently
poisons *every* downstream answer, so the contracts and invariants had to be pinned
down first. Once the foundation was trustworthy, the **demo** half (agent, retrieval,
eval, UI, Docker) was built fast and pragmatically against a fixed **5–6 hour** budget
— the SDD ceremony was intentionally dropped there in favor of shipping a working,
evaluated demo. Knowing *when* to apply rigor and when to move is itself the lesson.

## Key trade-offs (and why)

| Decision | Chosen | Why / cost |
|---|---|---|
| Numbers source | XBRL only | exactness; cost is we answer numerically only for tagged facts |
| Headline metrics | a curated table of **8** | covers the common questions cleanly; extending = add to the table |
| Retrieval fusion | **RRF** of BM25 + dense | scale-free, robust, no training; a learned reranker would cost a model call/latency |
| Local context | **parent-expansion** | CAG's benefit without its 1M-token cost (see 02) |
| Agent model | `gpt-4o-mini`, `temp=0` | cheap + deterministic routing; a larger model would raise cost for marginal gain here |
| Self-correction | **one** reflect→revise pass | catches most gaps; bounded so latency/cost stay predictable |
| Eval judges | LLM-as-judge + deterministic | judges scale to open-ended answers; determinism anchors the bedrock metrics |
| Deployment | **bake once, serve** | lean, reproducible image; cost is the corpus is a fixed artifact (rebuild offline to refresh) |
| Chunking | **structure-based sub-chunks** | the parser's blocks are the chunks; long ones split (tables row-wise w/ header) so nothing is truncated out of the embedding (docs 02, 07) |
| Stores | **DuckDB + Qdrant, embedded** | the designed two-store split, in-process: numbers→SQL truth, narrative→vector recall; no server, single-container kept (doc 07) |

## War stories (the genuinely instructive failures)

- **Docling OOM (`std::bad_alloc`).** A whole-document parse accumulated all-page
  backend state and blew system RAM. Fix: **page-windowing** (16-page windows, released
  each) + lighter models (`layout_v2`, TableFormer FAST). *Lesson:* the parse is
  heavyweight → it belongs offline, parse-once (the whole two-layer split in doc 00).

- **Orphaned processes starving RAM.** On Windows, stopping a task did **not** kill the
  spawned parse/test processes; several `@slow` rebuilds + a parse kept running, eating
  ~4 GB and causing repeated OOM segfaults that looked like new bugs. Fix: kill the
  processes directly (by cmdline match). *Lesson:* on Windows, verify child processes
  are actually dead — a "stopped" task can leave RAM-hungry orphans that masquerade as
  fresh failures.

- **Corpus corruption from those orphans.** The starved processes overwrote FY2021–24
  Element JSONL with partial parses (FY2024 dropped 5,111 → 3,307). Fix: clean re-parse
  on freed RAM. *Lesson:* the numbers were untouched (XBRL is deterministic and separate)
  — the firewall's separation of streams contained the blast radius.

- **The parent-expansion collision (02).** Keying reading-order neighbors on `ordinal`
  worked for one filing but **collided across five** (ordinals restart per filing), so
  multi-year retrieval silently biased to the latest year. *Lesson:* a key that's unique
  *within* a partition isn't unique *across* the union — and adding a feature (the year
  filter) is often what finally exposes a latent bug. It also shows the eval's value:
  `year_scope_accuracy` is exactly the metric that would have caught it.

- **The 800-char embedding truncation.** The dense index embedded only each Element's
  *first 800 chars*, so a 7.2k-char table was ~89% invisible to its own vector. Fix:
  structure-based **sub-chunks** (tables row-wise, header repeated), scored by best
  sub-chunk (docs 02, 07). *Lesson:* a silent retrieval weakness found by **measuring**
  (max table length vs the cap), fixed with **no regression** — the eval gate confirmed it.

## What's deferred (honest edges)

- **Semantic sections.** `item` comes from filing boundaries; finer semantic sectioning
  (e.g. splitting Item 15 / Exhibit 13's MD&A into sub-topics) is logged as follow-up.
- **More headline metrics.** The facts table is 8 metrics; broadening numeric coverage
  is "add rows," not new architecture.
- **A learned reranker.** RRF is right for this scale; a larger corpus would justify a
  cross-encoder reranker after fusion. *(The vector store — **Qdrant** — and the SQL fact
  store — **DuckDB** — are now integrated, embedded; see [07 · The stores](07-stores.md).)*
- **Larger golden set.** 16 items covers every year and every behavior (numeric,
  cross-year, year-scoped narrative, refusal); more items would tighten the statistics.

← Back to the [guide index](README.md) · the [overview](00-overview.md).
