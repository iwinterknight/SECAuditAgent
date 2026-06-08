"""Hybrid retrieval over the 10-K narrative — dense + sparse, fused, with parent
expansion.

Why hybrid for a 10-K: keyword (BM25) nails exact terms ("CET1", "allowance for
credit losses"); dense embeddings catch paraphrase and meaning ("how risky are
the loans?"). We fuse the two ranked lists with **Reciprocal Rank Fusion** (robust,
score-scale-free), then **parent-expand** each hit with its reading-order neighbors
so the model sees the full local context (the useful half of CAG without stuffing
the whole corpus into the prompt).

Embeddings are computed once with OpenAI and cached to a gitignored ``.npy`` next to
the corpus, so startup is instant after the first build.
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
from openai import OpenAI
from rank_bm25 import BM25Okapi

from answer import _tokens
from config.schema import Element
from config.settings import get_settings
from ingestion.serialize import read_jsonl

_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
_RRF_K = 60  # RRF damping; standard default


def _embed_texts(client: OpenAI, texts: list[str]) -> np.ndarray:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 256):  # batch to stay within request limits
        batch = [t[:800] for t in texts[start : start + 256]]
        resp = client.embeddings.create(model=_EMBED_MODEL, input=batch)
        vectors.extend(d.embedding for d in resp.data)
    arr = np.asarray(vectors, dtype=np.float32)
    return arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)


@lru_cache(maxsize=1)
def _index() -> tuple[list[Element], BM25Okapi, np.ndarray]:
    """Load every parsed filing's Elements + embeddings (per-filing cache, so a newly
    parsed year only embeds itself), concatenated into one hybrid index."""
    settings = get_settings()
    derived = settings.derived_dir / "ingestion"
    all_elements: list[Element] = []
    all_embeddings: list[np.ndarray] = []
    client: OpenAI | None = None
    for filing in settings.FILINGS:
        path = derived / "elements" / f"{filing.accession}.jsonl"
        if not path.is_file():
            continue
        elements = [e for e in read_jsonl(path, Element) if len(e.text) > 40]
        cache = derived / "embeddings" / f"{filing.accession}.npy"
        embeddings = np.load(cache) if cache.is_file() else None
        if embeddings is None or embeddings.shape[0] != len(elements):
            client = client or OpenAI()
            embeddings = _embed_texts(client, [e.text for e in elements])
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, embeddings)
        all_elements.extend(elements)
        all_embeddings.append(embeddings)
    matrix = (
        np.vstack(all_embeddings).astype(np.float32)
        if all_embeddings
        else np.zeros((0, 1), dtype=np.float32)
    )
    bm25 = BM25Okapi([_tokens(e.text) for e in all_elements])
    return all_elements, bm25, matrix


def build_index() -> int:
    """Force-build the embedding cache (used by the one-time build step). Returns n."""
    elements, _bm25, embeddings = _index()
    return len(elements)


def _parent_expand(elements: list[Element], indices: list[int]) -> list[Element]:
    """Add each hit's immediate reading-order neighbors (fuller local context)."""
    by_ordinal = {e.ordinal: i for i, e in enumerate(elements)}
    keep: list[int] = []
    seen: set[int] = set()
    for idx in indices:
        ordinal = elements[idx].ordinal
        for neighbor_ordinal in (ordinal - 1, ordinal, ordinal + 1):
            j = by_ordinal.get(neighbor_ordinal)
            if j is not None and j not in seen:
                seen.add(j)
                keep.append(j)
    return [elements[j] for j in keep]


def hybrid_search(query: str, k: int = 8, expand: bool = True) -> list[Element]:
    """Top-k Elements by RRF(dense, sparse), optionally parent-expanded."""
    elements, bm25, embeddings = _index()

    sparse_rank = np.argsort(bm25.get_scores(_tokens(query)))[::-1]

    q = np.asarray(
        OpenAI().embeddings.create(model=_EMBED_MODEL, input=[query]).data[0].embedding,
        dtype=np.float32,
    )
    q /= np.linalg.norm(q) + 1e-9
    dense_rank = np.argsort(embeddings @ q)[::-1]

    rrf: dict[int, float] = {}
    for rank, idx in enumerate(sparse_rank[:50]):
        rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (_RRF_K + rank)
    for rank, idx in enumerate(dense_rank[:50]):
        rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (_RRF_K + rank)

    top = sorted(rrf, key=lambda i: rrf[i], reverse=True)[:k]
    return _parent_expand(elements, top) if expand else [elements[i] for i in top]
