# 02 · Retrieval — finding the right narrative

> Code: `app/retrieval.py`. Turns the Element stream (doc 01) into the passages the
> agent's `search_filings` tool reads. Numbers do **not** come through here — they
> come from XBRL (doc 03). This block serves *narrative* questions.

## Why not just embed everything and call it RAG?

10-K narrative has two kinds of query that pull in opposite directions:

- **Exact terms** — "CET1 ratio", "allowance for credit losses", "Item 1A". A reader
  wants the passage with *that token*. This is what **keyword/lexical** search (BM25)
  is best at; embeddings often paraphrase it away.
- **Meaning** — "how risky are the loans?" maps to text about credit quality,
  charge-offs, reserves that share no keywords. This is what **dense embeddings** are
  for; BM25 misses it entirely.

A single method loses one of these. So we run **both** and fuse them — *hybrid
retrieval*.

## The pipeline (one function, `hybrid_search`)

```
query
 ├─ BM25 over tokens         → sparse_rank  (lexical)
 ├─ OpenAI embedding · dot   → dense_rank   (semantic)
 ├─ Reciprocal Rank Fusion   → one ranked list
 ├─ (optional) year filter   → keep one fiscal_year
 └─ parent-expansion         → add reading-order neighbors  → passages
```

### 1. Two rankers

- **Sparse** — `BM25Okapi` (the `rank_bm25` library) over whitespace-normalized
  tokens of every Element. Classic TF-IDF-family lexical scoring.
- **Dense** — each Element is first split into bounded **sub-chunks** (a long table or
  paragraph would otherwise be truncated into one diluted vector); every sub-chunk is
  embedded with OpenAI `text-embedding-3-small` (L2-normalized) and indexed in **Qdrant**
  (the vector store — doc 07); an Element is scored by its **best**-matching sub-chunk.
  Tables split row-wise with the header repeated so
  each piece is self-describing; prose splits into overlapping windows. The query is
  embedded the same way — similarity is a dot product. *(Sub-chunks are a dense-index
  detail; ranking, citations, the year filter and parent-expansion all stay at the
  Element level. BM25 still reads the full Element text.)*

### 2. Reciprocal Rank Fusion (RRF) — how we combine them

We can't add a BM25 score (unbounded) to a cosine score ([-1, 1]) directly — different
scales. RRF sidesteps that by using **rank, not score**: an item at rank *r* in a list
contributes `1 / (k + r)`, summed across both lists.

```python
for rank, idx in enumerate(sparse_rank[:80]):
    rrf[idx] += 1 / (_RRF_K + rank)      # _RRF_K = 60, the standard default
for rank, idx in enumerate(dense_rank[:80]):
    rrf[idx] += 1 / (_RRF_K + rank)
ranked = sorted(rrf, key=rrf.get, reverse=True)
```

Properties that make RRF a good default: it's **scale-free** (only ranks matter),
**robust** (one ranker being wildly off can't dominate), and **parameter-light** (just
`k`, which damps how much top ranks outweigh deep ones). An item both rankers like
rises to the top; an item only one likes still gets a fair shot.

### 3. Year scoping (a metadata filter)

`hybrid_search(query, fiscal_year=2022)` keeps only Elements whose `fiscal_year` is
2022 *after* ranking. This is what lets the agent answer "per the **FY2022** 10-K…"
and is checked by the eval's `year_scope_accuracy` metric (doc 04). Omit it and the
search spans all five filings.

### 4. Parent-expansion (the cheap win)

A single retrieved Element can be a sentence fragment. We add each hit's **reading-
order neighbors** so the model sees the surrounding context:

```python
for j in (idx - 1, idx, idx + 1):       # the hit and its neighbors
    if elements[j].source_filing == elements[idx].source_filing:
        keep.append(j)                   # … but never cross a filing boundary
```

This captures the *useful* half of "Cache-Augmented Generation" — local context around
a hit — without CAG's cost of stuffing whole documents into the prompt.

> **A real bug lived here.** The first version keyed neighbors on `ordinal` via a
> `{ordinal: index}` map. But `ordinal` is *per-filing* (each filing restarts at 0),
> so in the combined 5-year index the map **collided** — every ordinal resolved to the
> last filing (FY2025). Result: year-scoped search for 2022 returned 2023–2025, and
> even unfiltered search collapsed to the latest years. The fix (above) expands by
> **list position within the same `source_filing`** — correct because `_index()` lays
> each filing's Elements out contiguously in ordinal order. Adding the year filter is
> what surfaced the bug; see doc 04 / doc 06.

## Caching — embed once, start instantly

`_index()` is `lru_cache`-d and loads embeddings from a **per-filing `.npy`** next to
the corpus. A filing is only re-embedded if its cache is missing or its Element count
changed — so adding a year embeds just that year, and restarts are instant. The whole
index (Elements + BM25 + the vstacked embedding matrix) is built once per process.

## Why not CAG (Cache-Augmented Generation) here?

CAG skips retrieval by putting the *entire* corpus in the prompt (KV-cache). Tempting,
but five 10-Ks are ~1M+ tokens — past context limits, slow, and expensive per call,
with worse needle-in-haystack accuracy than targeted retrieval. Parent-expansion gives
us CAG's local-context benefit at a fraction of the cost. (We weighed this explicitly;
doc 06 records the decision.)

→ Next: [03 · The agent](03-agent.md) — who decides *when* to search vs look up a fact.
