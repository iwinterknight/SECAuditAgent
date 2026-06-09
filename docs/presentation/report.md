# JPMorgan 10-K — Agentic RAG + Evaluation

### Exact financials **and** narrative over five years of filings (FY2021–2025)
### *A financial number is exact or absent — never plausibly wrong.*

## 1 · The problem

```
            ONE 10-K  =  two bodies
     +-------------------------------+
     |  NARRATIVE   prose + tables   |  ->  "what does it say about credit risk?"
     |  XBRL        tagged numbers   |  ->  "net income in 2024?   the change?"
     +-------------------------------+

     Constraint:   a WRONG number is worse than NO number.
```

- Generic "PDF -> chunks -> LLM" RAG **hallucinates figures**. Not acceptable for financials.

## 2 · The big idea

```
   NUMBERS     -->  XBRL only (exact)         --+
   ARITHMETIC  -->  deterministic tool          +-->  an AGENT routes  -->  a VALIDATOR guards
   NARRATIVE   -->  retrieved + cited (FY, p.) --+
```

- **Fidelity over fluency:** the model *orchestrates* — it never sources or computes a number.

## 3 · Architecture

```
  OFFLINE (once)                  BAKED               STARTUP (embedded)        ONLINE
  PDF  -Docling-> Elements --+                         DuckDB  (facts)          question
                            +--> *.jsonl + *.npy  -->  Qdrant  (sub-chunks) -->  AGENT --> answer
  iXBRL-Arelle -> XBRLFacts -+    (source of truth)    BM25    (text)           (+ validator)

                                                                          EVALUATION over a golden set
```

- Heavy work runs **once, offline**; serving only reads -> fast, one lean container.

## 4 · Domain: inline XBRL

```
  JPMorgan --tags--> inline XBRL --against--> FASB US-GAAP taxonomy --filed via--> SEC EDGAR

  PwC audits the STATEMENTS .............. yes
  the XBRL TAGS themselves ............... NOT separately audited
```

- So we **trust XBRL over prose — but not blindly**: keep the most-precise tagging, skip "nil" (never a false 0).

## 5 · Data foundation — the firewall

```
  PDF    -Docling->  Elements   (located text, for retrieval)   --+
                                                                  |   NEVER
  iXBRL  -Arelle ->  XBRLFacts  (Decimal numbers, the figures)  --+   mixed
```

- Figures are **built in ONE module** -> "the model can't invent a number" is *structural*, not hopeful.

## 6 · Chunking — nothing truncated

```
  BEFORE   [ 7,200-char table ]  ->  1 vector (first 800 chars)   ->   ~89% INVISIBLE
  AFTER    [ table ]  ->  row-groups, header repeated  ->  N sub-chunks  ->  ALL embedded
```

- Chunks are the parser's **own blocks** (paragraph / heading / whole table), not fixed windows.

## 7 · Two stores — truth + recall

| Store | Holds | Answers | Its job |
|---|---|---|---|
| **DuckDB** | XBRL facts (typed rows) | *exact* keyed lookup | **truth** |
| **Qdrant** | sub-chunk embeddings | *semantic* search + filters | **recall** |

- Both **embedded** (in-process, no server), built from the baked JSONL/`.npy`. **JSONL stays the source of truth.**

## 8 · Retrieval — hybrid

```
  query --+-- BM25         (exact terms: "CET1")     --+
          |                                            +-- RRF --> year filter --> parent-expand --> passages
          +-- Qdrant dense (meaning / paraphrase)    --+        ( score = 1 / (60 + rank) )
```

- Keyword **+** meaning, fused by **rank** (no score-scaling), scoped by a **year payload filter**.

## 9 · The context the agent sees

```
  [FY2024 p.101]  "...capital governance framework; internal minimum requirements..."   <- Qdrant
  Total assets (exact, from XBRL):  FY2024 = $4,002,814 million ;  FY2021 = $3,743,567   <- DuckDB
```

- Small, **provenance-tagged** (year + page). The model builds the answer **only** from this.

## 10 · The agent — the loop

```
  question -> [ OpenAI tool-calling loop, temp 0, <= 4 steps ]
                 route --> run tool --> read result --> ... --> reflect/revise --> validate --> answer
```

- **Raw OpenAI tool-calling** (a ~40-line loop) — *not* LangGraph. One agent, three flat tools.

## 11 · The agent — fidelity

```
                +-- lookup_financial_fact  -->  DuckDB (exact)
   question --> +-- compute  (10 deterministic ops)  -->  no LLM math
                +-- search_filings  -->  Qdrant + BM25
                          |
                VALIDATOR:  every figure in the answer  in  tool outputs?    ok  /  flag
```

- Self-RAG **reflect -> revise**; **refuses** when no tool can answer.

## 12 · Evaluation — two surfaces, three families

```
   ANSWER      ->  deterministic scorers (exact)   +   RAG triad (LLM-judge)
   TRAJECTORY  ->  trajectory judge (the tool-use path)
   OVER TIME   ->  monitoring:  regression  +  drift
                   ( 17-item golden set, all 5 fiscal years )
```

- A right answer reached by a **wrong path** is a latent bug -> we judge the path too.

## 13 · The RAG triad

```
                    CONTEXT RELEVANCE
                 (is the retrieved context on-topic?)
                    /                      \
          GROUNDEDNESS  ------------------  ANSWER RELEVANCE
       (is the answer rooted in it?)     (does it address the question?)
```

- All three **LLM-judged**, plus a **trajectory judge** (tool appropriateness · efficiency · faithfulness).

## 14 · Monitoring — two watchers

```
   REGRESSION  ->  watches OUR scores    ->  drop > 0.10 vs baseline   =  silent failure   [ act ]
   DRIFT       ->  watches THE NUMBERS   ->  move > 30% year-over-year  =  "eyeball it"     [ info ]
```

- Regression **proved the DuckDB/Qdrant swap cost no quality**. Drift = real moves (net income +31.5% FY22->FY23).

## 15 · Results

```
   RAG triad     context-rel 1.0    groundedness 1.0    answer-rel 1.0
   fidelity      numeric-exact 1.0  validator 1.0       year-scope 1.0
   trajectory    appropriateness .94    efficiency .88    faithfulness .99
   monitoring    regression: none       drift: 3 (all real)
                 17 golden items · gpt-4o-mini · unit tests green
```

- Exact across every year, grounded, right tools — **proven, not asserted**.

## 16 · Deployment

```
   [ lean image:  baked corpus + embeddings   |   NO Docling / Arelle / torch ]
        -> embedded DuckDB + Qdrant build at startup (~15s, once)  ->  serves :8501   [ HTTP 200 ]
```

- **Bake once, serve** — a single container, verified end-to-end.

## 17 · Honest edges

- Stores buy **architectural completeness + scale-readiness** — at this size the eval **proved no quality cost**.
- Same-model judge · **8** headline metrics exposed (of ~1,098) · **consolidated** entity only.
- Next: a stronger/independent judge · arbitrary-concept lookups · a learned reranker.

## 18 · Takeaways

```
   1   Fidelity is STRUCTURAL    numbers from XBRL, one constructor, a validator
   2   Two stores by data type   DuckDB = truth,  Qdrant = recall   (both embedded)
   3   Agentic but TRANSPARENT    a plain tool-calling loop  ->  fully evaluable
   4   Evaluation is CO-EQUAL     RAG triad + trajectory judge + drift/regression
```
