# 07 · The stores — DuckDB (facts) + Qdrant (vectors), integrated

> Code: `app/duckdb_store.py`, `app/vector_store.py`. **This supersedes the earlier
> "designed M3, not built" framing in docs 06–08-era notes:** both stores are now wired
> into the serving path — *embedded*, so the lean single-container deploy is unchanged.

## The two-store split (why two)

The two question types need different machinery — the project's original rule was *"Qdrant
is for recall, DuckDB is for truth."*

| | **DuckDB** | **Qdrant** |
|---|---|---|
| Kind | embedded OLAP **SQL** engine | embedded **vector** database |
| Holds | XBRL facts as typed rows | sub-chunk embeddings + payload |
| Answers | *exact* keyed lookup (entity+concept+period) | *fuzzy* dense nearest-neighbor + filters |
| Serves | `lookup_financial_fact`, `compute` | `search_filings` (dense side) |

Numbers must be **exact** (a keyed/relational problem → SQL); narrative is **meaning-based**
(approximate recall → vectors). Keeping them in separate stores is the §1.2 firewall made
physical.

## DuckDB — the facts store (`app/duckdb_store.py`)

- **Embedded, in-process** (`duckdb.connect()` in-memory), built once per process: it loads
  the baked `facts/*.jsonl` into a table and stamps `fiscal_year` from the authoritative
  accession→FY map (never re-derived from a date).
- **The lookup replicates `answer._headline_fact` exactly** — the single **consolidated,
  dimensionless** fact whose period matches:
  ```sql
  SELECT value, unit FROM facts
  WHERE concept=? AND entity='JPMC_CONSOLIDATED'
    AND cardinality(dimensions)=0          -- not a segment/dimensional breakdown
    AND period_type=? AND <period dates match>
  ORDER BY fact_id LIMIT 1
  ```
  The `cardinality(dimensions)=0` guard is load-bearing: `us-gaap:Assets` is *also* tagged
  by segment, so without it you'd return an $857B sub-figure instead of the $3.74T total.
- **Fidelity preserved:** `value` is read as `VARCHAR` and returned as `Decimal` — never a
  binary float (doc 01's `Decimal` rule, end to end).
- **Verified:** the DuckDB-built headline table is **identical to the old in-memory table —
  40/40 entries, 0 diffs.**

`answer.load_corpus` now builds the headline table from this store; the table's shape and
every downstream consumer (agent tools, validator, UI) are unchanged.

## Qdrant — the vector store (`app/vector_store.py`)

- **Embedded, in-memory** (`QdrantClient(":memory:")`), built once per process from the
  baked sub-chunk `.npy` embeddings (doc 02). One point per **sub-chunk**: the vector plus a
  payload — `owner` (the Element index), `fiscal_year`, `page`, `item`, `kind`,
  `source_filing`.
- **`hybrid_search`'s dense side** now queries Qdrant for the top sub-chunks, de-duplicates
  to their owning Element (best match first), and feeds that into the **same** RRF fusion
  with BM25, the same year guard, the same parent-expansion. Only the dense scorer changed
  (numpy max-pool → Qdrant).
- **Payload-filtered search is live:** `fiscal_year` is pushed down as a Qdrant filter (so
  year-scoped queries are scoped at the source). `item` / `kind` are in the payload too —
  the **section filter** is now one `FieldCondition` away.
- **Verified:** year filter returns only the requested year; eval with both stores live
  shows **no regression** (core metrics 1.0, efficiency 0.956).

## Embedded, on purpose (deployment unchanged)

Both run **in-process, no server** — so the bake-once-reuse, single-container deploy holds:
the baked artifacts (`facts/*.jsonl`, sub-chunk `.npy`) are the source; the stores are built
from them at container startup (DuckDB ~instant, Qdrant ~15s for 18k vectors). The Dockerfile
just adds `duckdb qdrant-client`. A Qdrant *server* would break single-container — not used.

## Honest scale note

At this corpus size (36k facts, ~18k sub-chunk vectors) the previous in-memory dict + numpy
exact-cosine were **functionally equivalent** — and numpy's exact cosine is actually a hair
*more* accurate than Qdrant's ANN. The wins from integrating the stores are: **(1)** the demo
*is* the designed M3 architecture, **(2)** SQL over all 36k facts + payload-filtered search
(year live, section ready), and **(3)** scale-readiness. It's architectural completeness, not
an answer-quality jump — and the eval proves the swap cost nothing.

## End-to-end (both stores in one answer)

> *"How did total assets change from 2021 to 2025, and what does the filing say about capital
> strength?"* → `compute` (**DuckDB**: +$681,333M, 18.2%, exact 3,743,567 → 4,424,900)
> + `search_filings` (**Qdrant**: capital-governance narrative, cited FY2021–2025). Validator:
> every figure grounded. The firewall, the two stores, and the agent — working together.

← Back to the [guide index](README.md).
