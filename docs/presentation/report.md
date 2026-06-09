# JPMorgan Chase 10-K — Agentic RAG + Evaluation
### Data-science panel walkthrough · ~40 minutes · 18 slides

*An agent that answers questions over JPMorgan's last five 10-K filings (FY2021–2025) — exact
financials and narrative — built so a number is **exact or absent, never plausibly wrong.***

---

## Talk flow (≈40 min)

| # | Slide | Min | Section |
|---|---|---|---|
| 1 | Title & thesis | 1 | Intro |
| 2 | The problem | 2 | Intro |
| 3 | Architecture at a glance | 2 | Intro |
| 4 | Domain: inline XBRL | 3 | Domain |
| 5 | Data foundation (Docling + Arelle) | 3 | Data |
| 6 | Chunking strategy | 2 | Retrieval |
| 7 | The two stores (DuckDB + Qdrant) | 3 | Retrieval |
| 8 | Retrieval: hybrid + RRF + filters | 3 | Retrieval |
| 9 | The context handed to the agent | 2 | Retrieval |
| 10 | The agent: loop & framework | 3 | Agent |
| 11 | The agent: fidelity & control | 3 | Agent |
| 12 | Evaluation: what we score | 3 | Eval |
| 13 | The RAG triad + trajectory judge | 3 | Eval |
| 14 | Monitoring: regression + drift | 2 | Eval |
| 15 | Results | 2 | Eval |
| 16 | Deployment | 1 | Ops |
| 17 | Limitations & next | 1 | Close |
| 18 | Key takeaways | 1 | Close |

---

## Slide 1 — Title & thesis  ·  1 min
- **Agentic RAG over JPMorgan's 5 years of 10-Ks**, plus a co-equal **evaluation** component.
- One idea to hold onto: **numbers come only from XBRL (exact), never the model; narrative is retrieved and cited; an agent routes; a validator guards.**
- 🗣 *"Two deliverables — the agent and its evaluation — and one principle: fidelity over fluency."*

## Slide 2 — The problem  ·  2 min
- A 10-K = ~300 pages of prose **plus** a parallel machine-readable **XBRL** package of every figure.
- Two question types: **narrative** ("what does it say about credit risk?") and **exact financials** ("net income in 2024, and the change?").
- The hard constraint is **fidelity**: a wrong number is worse than no answer. Generic "PDF → chunks → LLM" RAG fails exactly here — models misread/round/hallucinate figures.
- 🗣 *"The bar isn't 'sounds right' — it's 'is the filed number, exactly.'"*

## Slide 3 — Architecture at a glance  ·  2 min
- **Offline (once):** parse PDFs → `Element`s, parse iXBRL → `XBRLFact`s → deterministic **JSONL** (the baked source of truth).
- **At startup:** that JSONL builds the **embedded stores** — DuckDB (facts) + Qdrant (vectors) + BM25.
- **Online:** an **agent** routes a question to tools (numbers → DuckDB; narrative → Qdrant+BM25), self-corrects, and a **validator** checks every figure.
- **Evaluation** runs the agent over a golden set (RAG triad + trajectory + monitoring).
- 🗣 *"Heavy work happens once, offline; serving only reads — that's why it's fast and ships in one lean container."*

## Slide 4 — Domain: inline XBRL  ·  3 min
- A 10-K is filed as **inline XBRL (iXBRL)** — one HTML doc that's human-readable *and* machine-tagged.
- **Who tags it:** the registrant (JPMorgan), via filing software — against **FASB's US-GAAP** taxonomy (+ DEI), mandated by the **SEC** via **EDGAR**.
- **Who audits what:** **PwC** audits the *statements* (under PCAOB); the **XBRL tags are the filer's own, generally un-audited** assertion.
- So we **trust XBRL over parsed prose, but not blindly** — we keep the most-precise of duplicate taggings, flag contradictions, and skip "nil" rather than coerce a false zero.
- 🗣 *"The number is exact because the company tagged it for the SEC — but the tagging isn't separately audited, so we still defend against it."*

## Slide 5 — Data foundation: Docling + Arelle  ·  3 min
- **Two streams, never mixed** (the §1.2 *firewall*): narrative `Element`s from the PDF; numeric `XBRLFact`s from iXBRL.
- **Docling** (layout model + TableFormer) parses the PDF into reading-order text/tables — run lean + **16-page windowing** to avoid OOM on a 300-page filing.
- **Arelle** (reference XBRL engine) reads the facts — exact value as `Decimal` (never float), period (instant vs duration), entity (consolidated vs subsidiary).
- `XBRLFact` is **constructed in exactly one place** → "the model can't invent a number" is *structural*, not hopeful.
- 🗣 *"Numbers are built in one module, as Decimals — that single-constructor rule is the whole basis of trust."*

## Slide 6 — Chunking strategy  ·  2 min
- The retrieval unit is the **parser's own block** (paragraph / heading / whole table), not fixed-size windows.
- Long blocks are split into **sub-chunks** for embedding — tables **row-wise, repeating the header** so each piece is self-describing.
- This fixed a real bug: a 7.2k-char table was **~89% invisible** to its single truncated vector; now every part is embedded.
- 🗣 *"We don't fixed-size chunk — we respect document structure, and split long tables so nothing falls out of the index."*

## Slide 7 — The two stores: DuckDB + Qdrant  ·  3 min
- **DuckDB** (embedded SQL) holds the **facts** → exact keyed lookups (`entity + concept + period`). *"For truth."*
- **Qdrant** (embedded vector DB) holds the **sub-chunk embeddings** + payload → semantic search with filters. *"For recall."*
- **Both embedded (in-process, no server)** — built at startup from the baked JSONL/`.npy`, so the single-container deploy is unchanged.
- **JSONL is still the source of truth**; the stores are query engines built *from* it — not a replacement.
- 🗣 *"Qdrant for recall, DuckDB for truth — both embedded, both built from the JSONL at startup."*

## Slide 8 — Retrieval: hybrid + RRF + filters  ·  3 min
- **Hybrid**: BM25 (exact terms like "CET1") **+** dense vectors (paraphrase/meaning) — each method catches what the other misses.
- Fused with **Reciprocal Rank Fusion** (`1/(60+rank)`, top-80 each) — rank-based, so no score-scale normalization needed.
- **Metadata filtering**: `fiscal_year` is a Qdrant **payload filter** (year-scoped questions); `item`/`kind` are ready for section filtering.
- **Parent-expansion**: each hit + its reading-order neighbors (within the same filing) for context.
- 🗣 *"Keyword + meaning, fused by rank, scoped by a year filter, expanded for context — classic hybrid RAG, done deliberately."*

## Slide 9 — The context handed to the agent  ·  2 min
- The model never sees the raw corpus or vectors — only **tool-result strings**:
  - narrative → `[FY2024 p.97] <≤500 chars>` × ~18 passages;
  - numbers → exact strings like `Total assets … FY2024: $4,002,814 million`.
- Small, targeted, **provenance-tagged** (year + page) → grounded, citable answers.
- 🗣 *"Its context is the tool outputs — year/page-tagged passages and exact figures — not a giant dump."*

## Slide 10 — The agent: loop & framework  ·  3 min
- **Raw OpenAI tool-calling** — a hand-written loop, **no LangGraph/LangChain**.
- The model **routes** (`tool_choice="auto"`, temp 0, ≤4 steps): picks tools, reads results, answers.
- **Single agent, 3 flat tools** — no sub-agents, no progressive disclosure (right for a 3-tool, focused domain).
- Transparent: the **trajectory is a plain list** → which is what makes it *evaluable*.
- 🗣 *"It's a ~40-line tool-calling loop, not a framework — one agent, three tools, fully inspectable."*

## Slide 11 — The agent: fidelity & control  ·  3 min
- **3 tools:** `lookup_financial_fact` (DuckDB), `compute` (**10 deterministic ops** — change/%/CAGR/avg/sum/min/max/ratio/percent-of/difference, **no LLM math**), `search_filings` (Qdrant+BM25).
- **Validator** (deterministic): every figure in the answer must trace to a tool output — catches a hallucinated *or* hand-computed number.
- **Self-RAG**: a reflect→revise critic pass; **refusal** when no tool can answer.
- 🗣 *"The model orchestrates but never sources or computes a number — tools do, and the validator checks every one."*

## Slide 12 — Evaluation: what we score  ·  3 min
- We score **two surfaces**: the **answer** *and* the **trajectory** (a right answer via a wrong path is a latent bug).
- Over a **17-item golden set** (all 5 FYs; numeric / narrative / refusal).
- **Three families:** (1) **deterministic** (numeric-exact, retrieval-hit, tool-correct, year-scope, validator — zero variance, the bedrock); (2) **LLM-judge** (next slide); (3) **monitoring** (slide 14).
- 🗣 *"We grade the answer and the path it took, with exact deterministic scorers as the bedrock and judges on top."*

## Slide 13 — The RAG triad + trajectory judge  ·  3 min
- **RAG triad** (LLM-judged): **context relevance** (is the retrieved context on-topic?), **groundedness/faithfulness** (is the answer rooted in it?), **answer relevance** (does it address the question?).
- **Trajectory judge** (the agentic counterpart): **tool appropriateness**, **efficiency**, **faithfulness** — over the actual tool-use path.
- 🗣 *"The full triad — context relevance, groundedness, answer relevance — plus a second judge that grades how the agent worked, not just what it said."*

## Slide 14 — Monitoring: regression + drift  ·  2 min
- **Regression (silent failure):** compare each metric to a committed **baseline**; a drop **>0.10** is flagged. *This is the gate that proved the DuckDB/Qdrant swap cost no quality.*
- **Data drift:** flag any headline metric moving **>30% year-over-year** — a "human, eyeball this" signal about the *real numbers* (e.g. Net income +31.5% FY22→FY23), **not** an error.
- 🗣 *"One watches our system's scores; the other watches the company's numbers — silent-failure vs data drift."*

## Slide 15 — Results  ·  2 min
- Latest run (17 items, gpt-4o-mini): **numeric-exact, retrieval-hit, year-scope, validator, the full triad — all 1.0**; tool-appropriateness 0.94; trajectory-efficiency 0.88; faithfulness 0.99.
- **No regression**; 3 data-drift flags (all real YoY moves).
- 12 unit tests on the compute tool + offline tests on chunking/stores/parent-expansion — all green.
- 🗣 *"Exact across every year, grounded, and the agent picks the right tools — proven, not asserted."*

## Slide 16 — Deployment  ·  1 min
- **One lean container**: no Docling/Arelle/torch at runtime — it carries *data*, not machinery.
- The baked corpus + the two **embedded** stores build at startup; **verified**: image builds, serves **HTTP 200**, both stores work in-container.
- 🗣 *"Bake once, serve — a single container, verified end-to-end."*

## Slide 17 — Limitations & next  ·  1 min
- **Honest scope:** at 17k vectors / 36k facts, the stores buy *architectural completeness* + scale-readiness, not a quality jump — and the eval proved it cost nothing.
- **Same-model judge** (gpt-4o-mini judges itself); **8 headline metrics** exposed (of ~1,098); **section filter** ready but not wired.
- **Next:** a stronger/independent judge; expose arbitrary-concept DuckDB lookups; a learned reranker; larger golden set.
- 🗣 *"I know exactly where the edges are — here they are, and here's what I'd do next."*

## Slide 18 — Key takeaways  ·  1 min
1. **Fidelity is structural** — numbers from XBRL only, built in one place, checked by a validator.
2. **Two stores by data type** — DuckDB for exact truth, Qdrant for semantic recall, both embedded.
3. **Agentic, but transparent** — a plain tool-calling loop, fully observable, therefore **evaluable**.
4. **Evaluation is co-equal** — two surfaces, the RAG triad + trajectory judge, and silent-failure/drift monitoring.
- 🗣 *"Fidelity over fluency, proven by an evaluation that's as much the deliverable as the agent."*

---

*Backup / appendix: gathered fact-by-fact notes in `gathered-context.md`; full code walkthrough in `docs/guide/` (00–07).*
