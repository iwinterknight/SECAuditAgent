# Gathered context — JPMorgan 10-K Agentic RAG presentation

Running capture from the deep-dive sessions: one fact + its insight per entry.
Compose into a presentation-ready summary with `/collate`.

---

### [1] PRESENTATION DIRECTIVE — "Domain understanding" cluster
- **Category:** decision
- **Fact:** Entries [2]–[6] (firewall; iXBRL + standards + who-tags/who-audits; audited-vs-untagged tags; Arelle; Docling) form ONE presentation section titled "Domain understanding."
- **Insight:** Showcase domain fluency, but briefly — keep the depth in these notes; on stage cap this whole section at **≤ 2 slides / 4–5 minutes total**.
- **Source:** user directive, this session

### [2] The §1.2 firewall — numbers only from XBRL
- **Category:** decision
- **Fact:** Financial figures are constructed in exactly one place — the XBRL path (`src/ingestion/xbrl.py`); the PDF/Docling path never builds a figure, and `XBRLFact` is defined and constructed in a single module. At answer time a validator re-checks every stated number against the tool outputs.
- **Insight:** Turns "the model can't invent a number" into a *structural* guarantee rather than a hope — the foundation of trust for financial QA.
- **Sayable:** "Numbers come only from XBRL — never the LLM or the parsed PDF — enforced by a single fact-constructor plus a runtime validator."
- **Cluster:** Domain understanding
- **Source:** docs/guide/01-data-foundation.md; app/agent.py `_validate`

### [3] iXBRL — the document, its standards, and who tags vs. audits
- **Category:** xbrl
- **Fact:** A 10-K is filed as **inline eXtensible Business Reporting Language (iXBRL)** — one document that is human-readable HTML with machine-readable tags embedded around each number. Chain of responsibility:
  - **Who composes it:** the *registrant* (the filing company — JPMorgan Chase & Co.), via its financial-reporting team, typically using disclosure-management software / a filing agent (e.g. Workiva, DFIN, Toppan Merrill).
  - **Tagged against which standards:** the data model is **eXtensible Business Reporting Language (XBRL)** from XBRL International; the concept vocabulary is the **United States Generally Accepted Accounting Principles (US GAAP)** Financial Reporting Taxonomy from the **Financial Accounting Standards Board (FASB)**, plus the **Document and Entity Information (DEI)** taxonomy for cover-page fields. Filing inline XBRL is mandated by the **U.S. Securities and Exchange Commission (SEC)** and submitted through **Electronic Data Gathering, Analysis, and Retrieval (EDGAR)**.
  - **Who audits what:** the financial *statements* are audited by an independent registered public accounting firm — for JPMorgan, **PricewaterhouseCoopers (PwC)** — under oversight of the **Public Company Accounting Oversight Board (PCAOB)**. The XBRL *tagging itself* is generally **not** separately audited; EDGAR runs only structural validation.
- **Insight:** The numbers arrive as a standards-governed, machine-readable artifact with a clear chain of responsibility — and the *audited* thing (the statements) is not the same as the *tagging*.
- **Sayable:** "The filer (JPMorgan) tags its own filing in inline XBRL against FASB's US-GAAP taxonomy, mandated by the SEC via EDGAR; PwC audits the statements, but not the tags."
- **Cluster:** Domain understanding
- **Source:** docs/guide/01-data-foundation.md; session Q&A

### [4] Audited statements vs. un-audited XBRL tags
- **Category:** xbrl
- **Fact:** The printed financial statements are audited (external accounting firm, PCAOB oversight); the XBRL tags are the filer's own, generally **un-audited** assertion (EDGAR validates structure only).
- **Insight:** So the XBRL reader trusts tags over parsed prose but *not blindly* — it keeps the most precise of duplicate taggings, flags genuinely contradictory ones, and skips nil/unparseable facts rather than coercing a false zero.
- **Sayable:** "We trust XBRL over prose, but not blindly — the tags aren't independently audited, so we defend against tagging errors (dedupe to most-precise, flag contradictions, skip-not-coerce)."
- **Cluster:** Domain understanding
- **Source:** src/ingestion/xbrl.py:124 (`_dedupe_facts`); :162 (`_build_fact`)

### [5] Arelle — one-liner
- **Category:** xbrl
- **Fact:** Arelle is the open-source reference XBRL engine.
- **Insight:** Used purely as an **offline reader** (resolves transforms / periods / dimensions into typed facts) and deliberately kept out of the runtime image — the container serves pre-extracted facts.
- **Sayable:** "Arelle is the open-source reference XBRL engine; we use it as an offline reader and keep it out of the serving image."
- **Cluster:** Domain understanding
- **Source:** src/ingestion/xbrl.py

### [6] Docling — one-liner
- **Category:** docling
- **Fact:** Docling parses each 10-K PDF with a layout model + TableFormer into reading-order Elements.
- **Insight:** Run with a lean model config and **16-page windowing** so a 300-page filing parses on a few GB of RAM without OOM.
- **Sayable:** "Docling turns the PDF into reading-order text + tables; we window it 16 pages at a time to avoid OOM."
- **Cluster:** Domain understanding
- **Source:** src/ingestion/elements.py

### [7] DEEP-DIVE SECTION — spend the most time here
- **Category:** decision
- **Fact:** Entries [8]–[13] are the core technical section: the chunking strategy, the two embedded stores (DuckDB + Qdrant), how a query fires against both via the agent, the RAG internals (RRF + metadata filtering + parent-expansion), and the exact context handed to the model.
- **Insight:** This is the heart of the "Agentic RAG" story — budget the most slides/time here (~10–12 min), more than the domain-understanding cluster.
- **Cluster:** Build & retrieval internals
- **Source:** this session

### [8] Chunking strategy — structure-based sub-chunks (not fixed-size)
- **Category:** retrieval
- **Fact:** The retrieval unit is the parser's own block (paragraph / heading / whole table) = one `Element`; long Elements are split into bounded ~1,200-char **sub-chunks** for embedding — tables **row-wise with the header repeated** (each piece self-describing), prose in overlapping windows. An Element is scored by its **best** sub-chunk (max-pool). Fixes the old bug where only the first 800 chars embedded (a 7.2k-char table was ~89% invisible to its own vector).
- **Insight:** Respects document structure + clean provenance, and nothing is truncated out of the dense index; parent-expansion (±1 reading-order neighbor, same filing) restores surrounding context at query time. (Hierarchical chunking / table-to-text was the planned M2; this is the shipped equivalent.)
- **Sayable:** "We don't fixed-size chunk — the parser's blocks are the chunks, with long ones split into self-describing sub-chunks so nothing is truncated out of the index."
- **Cluster:** Build & retrieval internals
- **Source:** app/retrieval.py (_subchunks, _parent_expand)

### [9] Two stores — and JSONL is STILL the baked source of truth
- **Category:** deployment
- **Fact:** We did **not** drop JSONL. The offline pipeline writes deterministic **JSONL** (Elements + XBRLFacts) + per-filing embedding **.npy** — the canonical, image-baked artifacts. At serving startup the query engines are **built from them**: **DuckDB** loads facts JSONL into a table; **Qdrant** is loaded from the sub-chunk .npy (+ payload); **BM25** is built from the Elements' text. Both stores are **embedded** (in-process, no server).
- **Insight:** JSONL = portable, diffable, deterministic source of truth (baked into the image); DuckDB/Qdrant = query-time projections rebuilt from it at startup. Layered, not either/or.
- **Sayable:** "JSONL is still the baked source of truth; DuckDB and Qdrant are query engines built from it at startup — embedded, so the single-container deploy is unchanged."
- **Cluster:** Build & retrieval internals
- **Source:** app/duckdb_store.py, app/vector_store.py, src/ingestion/serialize.py

### [10] How a query fires against both stores via the agent
- **Category:** agent
- **Fact:** The agent is an OpenAI tool-calling loop (`tool_choice="auto"`, temp 0, ≤4 steps). Per question it routes: a **number** → `lookup_financial_fact` / `compute` → **DuckDB** (exact SQL); **narrative** → `search_filings` → hybrid retrieval over **Qdrant** + BM25. Multiple tools can fire across steps, then a Self-RAG reflect→revise pass, then a validator checks every figure.
- **Insight:** The two stores are never queried "blindly together" — the agent decides which store each sub-question needs; numbers and narrative stay separated (the firewall) until the final answer.
- **Sayable:** "The agent routes each sub-question — numbers to DuckDB via SQL, narrative to Qdrant via hybrid search — then a validator checks every figure."
- **Cluster:** Build & retrieval internals
- **Source:** app/agent.py (_tool_loop, _TOOLS)

### [11] RAG internals — hybrid retrieval, RRF, metadata filtering, parent-expansion
- **Category:** retrieval
- **Fact:** `search_filings` runs **hybrid** retrieval: (a) **sparse** BM25 over full Element text; (b) **dense** — embed the query, query **Qdrant** for the top ~300 sub-chunks (optionally **payload-filtered by fiscal_year**), de-duplicated to owning Elements. The two ranked lists are fused with **Reciprocal Rank Fusion (RRF)** — each list's **top-80** contribute `1/(60 + rank)`; rank-based, so no score normalization. The fused list is **year-filtered** (post-RRF guard) and **parent-expanded** (±1 reading-order neighbor, same filing). Top-k = 6 hits → ~18 passages after expansion.
- **Insight:** BM25 nails exact terms (CET1, "allowance for credit losses"); dense catches paraphrase; RRF combines them robustly; the payload filter scopes by year; parent-expansion restores context. Item/kind are in the payload → section filtering is one step away.
- **Sayable:** "Hybrid = BM25 + dense-over-Qdrant, fused by Reciprocal Rank Fusion, scoped by a fiscal-year payload filter, then parent-expanded for context."
- **Cluster:** Build & retrieval internals
- **Source:** app/retrieval.py (hybrid_search), app/vector_store.py (dense_elements)

### [12] The exact context handed to the agent
- **Category:** agent
- **Fact:** The model never sees the raw corpus or raw vectors. It sees **tool-result strings** appended as `role:"tool"` messages: narrative = a block of passages each rendered `"[FY{year} p.{page}] {first 500 chars of the Element}"` (the parent-expanded hits, ~18 of them); numbers = exact strings like `"Total assets (exact, from XBRL): FY2024: $4,002,814 million; …"` and computed-change strings. When it composes, its context = system prompt + question + accumulated tool outputs. The validator then confirms every comma-formatted figure traces to a tool output.
- **Insight:** The context is small, targeted, and provenance-tagged — year/page-labelled passages + exact figures, not a giant dump — which is what keeps answers grounded and citable.
- **Sayable:** "The agent's context is the tool outputs — year/page-tagged narrative passages plus exact XBRL figures — so every answer is built only from retrieved, cited evidence."
- **Cluster:** Build & retrieval internals
- **Source:** app/agent.py (_tool_search render + tool messages), app/answer.py

### [13] Verified together + honest framing
- **Category:** evaluation
- **Fact:** Both stores + the revised chunking verified together: eval no-regression (core metrics 1.0, efficiency 0.956); an end-to-end query using both stores (validator grounded); 15 new offline unit tests; and the Docker image building + serving **HTTP 200** with both stores in-container. Honest note: at this scale (~17k vectors / 36k facts) the prior in-memory dict + numpy were functionally equivalent — the stores buy **architectural completeness** (the designed M3), payload-filtered search, and scale-readiness, and **the eval proved the swap cost nothing**.
- **Insight:** Showing the eval/tests/Docker proof + the candid "it cost nothing, here's why we did it" is what makes the architecture choice read as deliberate, not cargo-culted.
- **Sayable:** "We integrated the designed two-store architecture, proved via the eval it costs nothing, and verified it end-to-end through to the running container."
- **Cluster:** Build & retrieval internals
- **Source:** eval/last_report.json, tests/unit/, Dockerfile

### [14] The 8 headline metrics — the agent's numeric vocabulary
- **Category:** data-ingestion
- **Fact:** The agent answers numbers over **8 curated headline metrics** (the `_HEADLINE` table, also the tools' `metric` enum): **4 balance-sheet / `instant`** — Total assets, Total liabilities, Total stockholders' equity, Total deposits; **4 income-statement / `duration`** — Net income, Total net revenue, Net interest income, Diluted EPS. Each maps to one **dimensionless, consolidated `us-gaap` concept**, materialized as **8 × 5 = 40 exact rows** queried from DuckDB at startup.
- **Insight:** They're the "at-a-glance" figures most asked about, and each resolves to a single unambiguous concept (so the lookup returns one exact number, not a dimensional sub-figure). The full filing has **~1,098 concepts / 36,046 facts** — we expose 8; widening coverage is literally "add a row to `_HEADLINE`."
- **What it means for the build:** this is the *scope* of the system's exact-number answers — `lookup_financial_fact` and `compute` operate over these 8 (the other ~1,000 concepts live in DuckDB but aren't yet exposed to the agent).
- **Sayable:** "The agent's numbers are 8 headline metrics — 4 balance-sheet, 4 income-statement — each a single dimensionless us-gaap concept, 40 exact rows from DuckDB; the rest of the ~1,000 tagged concepts are in DuckDB but not yet surfaced."
- **Cluster:** Build & retrieval internals
- **Source:** app/answer.py (`_HEADLINE`)

### [15] The compute tool — 10 deterministic operations (no LLM math)
- **Category:** agent
- **Fact:** One `compute` tool exposes **10 deterministic operations**: over a metric across years — change, percent_change, cagr, average, sum, min, max; between two metrics in a year — ratio, percent_of, difference. **All arithmetic runs in Python** (additive ops exact via `Decimal`; growth/ratios rounded for display); the model only picks the operation + args.
- **Insight:** Replaces the earlier two-op `compute_change`, closing the "what about other calculations?" gap. The **validator was tightened** to also catch decimals / per-share / percentages (not just comma-grouped amounts), so a hand-computed ratio can't slip past — bare integers (years/pages) still ignored. The "no LLM arithmetic" firewall is preserved.
- **Sayable:** "Any arithmetic goes through one compute tool with ten deterministic operations — the model picks the op, Python does the math exactly — never the LLM; and the validator now catches ratios/percentages too."
- **Cluster:** Build & retrieval internals
- **Source:** app/agent.py (`_tool_compute`); tests/unit/test_compute.py

### [16] The RAG evaluation triad — all three legs, LLM-judged
- **Category:** evaluation
- **Fact:** The RAG triad is scored by an LLM judge with the **three canonical legs**: **context_relevance** (is the retrieved context relevant to the query, vs off-topic noise?), **groundedness/faithfulness** (is the answer rooted in that context — no invented/distorted facts?), **answer_relevance** (does it address the query?). Earlier only groundedness + answer_relevance were judged and context relevance was a deterministic *proxy* — now it's a proper judged leg; `retrieval_hit`/`year_scope` stay on as complementary deterministic retrieval checks.
- **Insight:** Completes the canonical triad (TruLens/RAGAS-style). It sits alongside the **trajectory judge** (tool_appropriateness, efficiency, faithfulness — the *agentic* counterpart), the deterministic scorers (numeric_exact, validator, year_scope), and the **monitoring** (regression vs baseline + YoY data-drift).
- **Sayable:** "We score the full RAG triad with an LLM judge — context relevance, groundedness, answer relevance — plus a separate trajectory judge for the agent's tool-use path, on top of deterministic exact-match scorers and regression/drift monitoring."
- **Cluster:** Evaluation
- **Source:** app/evaluate.py (`_judge`, `_judge_trajectory`)
