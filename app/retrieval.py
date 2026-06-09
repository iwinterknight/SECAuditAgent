"""Hybrid retrieval over the 10-K narrative — dense + sparse, fused, with parent
expansion and sub-chunk embedding.

Why hybrid for a 10-K: keyword (BM25) nails exact terms ("CET1", "allowance for
credit losses"); dense embeddings catch paraphrase and meaning ("how risky are the
loans?"). We fuse the two ranked lists with **Reciprocal Rank Fusion** (robust,
score-scale-free), then **parent-expand** each hit with its reading-order neighbors
so the model sees the full local context (the useful half of CAG without stuffing the
whole corpus into the prompt).

**Sub-chunk embedding (why this isn't a flat one-vector-per-Element index).** An
Element can be long — a multi-row table serializes to thousands of characters — and
forcing all of it into a single embedding vector both *truncates* (the tail is lost)
and *dilutes* (one vector straddling many topics). So for the **dense** side we split
each long Element into bounded, overlapping **sub-chunks** (tables split row-wise,
repeating the header row so each piece is self-describing), embed every sub-chunk, and
score an Element by its **best** sub-chunk (max-pool). Retrieval, citations and
parent-expansion still operate at the **Element** level — sub-chunks are purely a
dense-index detail. BM25 keeps reading the full Element text (it has no truncation
problem). This is the classic *small-to-big* pattern: precise small pieces for
matching, the parent Element for context.

Embeddings are computed once with OpenAI and cached to a gitignored ``.npy`` next to
the corpus, so startup is instant after the first build.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

import numpy as np
from openai import OpenAI
from rank_bm25 import BM25Okapi

from answer import _tokens
from config.schema import Element, ElementKind
from config.settings import get_settings
from ingestion.serialize import read_jsonl

_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
_RRF_K = 60  # RRF damping; standard default

# Sub-chunk sizing. ~1200 chars ≈ 300 tokens: small enough that a sub-chunk embeds as
# a focused vector (good retrieval precision), large enough to keep a paragraph or a
# few table rows intact. Overlap keeps a sentence straddling a boundary findable from
# either side. Most Elements (median ~140 chars) are a single sub-chunk; only the long
# tail (big tables, long prose) splits.
_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 200
_EMBED_CHAR_CAP = 4000  # defensive cap; sub-chunks are already bounded well below this

_ROW_RE = re.compile(r"<tr\b.*?</tr>", re.DOTALL | re.IGNORECASE)


def _window_subchunks(text: str) -> list[str]:
    """Split long prose into overlapping char windows, breaking on whitespace so a
    word is never cut mid-token."""
    chunks: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + _CHUNK_CHARS, n)
        if end < n:  # back up to the last space in the tail so we cut cleanly
            space = text.rfind(" ", start + _CHUNK_CHARS - _CHUNK_OVERLAP, end)
            if space > start:
                end = space
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - _CHUNK_OVERLAP, start + 1)
    return chunks or [text[:_EMBED_CHAR_CAP]]


def _table_subchunks(html: str) -> list[str]:
    """Split a serialized table row-wise, **repeating the header row** on each group so
    every sub-chunk is self-describing (a row group without its header is meaningless,
    and that meaninglessness is exactly what a single truncated table vector suffered)."""
    rows = _ROW_RE.findall(html)
    if len(rows) <= 1:
        return [html[:_EMBED_CHAR_CAP]]
    header, body = rows[0], rows[1:]
    groups: list[str] = []
    current: list[str] = []
    current_len = len(header)
    for row in body:
        if current and current_len + len(row) > _CHUNK_CHARS:
            groups.append(f"<table>{header}{''.join(current)}</table>")
            current, current_len = [], len(header)
        current.append(row)
        current_len += len(row)
    if current:
        groups.append(f"<table>{header}{''.join(current)}</table>")
    return groups or [html[:_EMBED_CHAR_CAP]]


def _subchunks(element: Element) -> list[str]:
    """One or more dense sub-chunks for an Element: the whole text when it's short,
    else split (row-wise for tables, windowed for prose) so nothing is truncated away."""
    text = element.text
    if len(text) <= _CHUNK_CHARS:
        return [text]
    if element.kind is ElementKind.TABLE:
        return _table_subchunks(text)
    return _window_subchunks(text)


def _embed_texts(client: OpenAI, texts: list[str]) -> np.ndarray:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 256):  # batch to stay within request limits
        batch = [t[:_EMBED_CHAR_CAP] for t in texts[start : start + 256]]
        resp = client.embeddings.create(model=_EMBED_MODEL, input=batch)
        vectors.extend(d.embedding for d in resp.data)
    arr = np.asarray(vectors, dtype=np.float32)
    return arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)


@lru_cache(maxsize=1)
def _index() -> tuple[list[Element], BM25Okapi, np.ndarray, np.ndarray]:
    """Load every parsed filing's Elements + per-**sub-chunk** embeddings (per-filing
    cache, so a newly parsed year only embeds itself), concatenated into one hybrid
    index.

    Returns ``(elements, bm25_over_full_element_text, sub_chunk_matrix, owner)`` where
    ``owner[j]`` is the index (into ``elements``) of the Element that sub-chunk ``j``
    belongs to — so a sub-chunk hit maps back to its Element for scoring + citation."""
    settings = get_settings()
    derived = settings.derived_dir / "ingestion"
    all_elements: list[Element] = []
    chunk_owner: list[int] = []
    all_embeddings: list[np.ndarray] = []
    client: OpenAI | None = None
    for filing in settings.FILINGS:
        path = derived / "elements" / f"{filing.accession}.jsonl"
        if not path.is_file():
            continue
        elements = [e for e in read_jsonl(path, Element) if len(e.text) > 40]
        # Expand each Element into its dense sub-chunks (deterministic), tracking the
        # owning Element so a sub-chunk hit maps back for scoring + parent-expansion.
        chunk_texts: list[str] = []
        owner_local: list[int] = []
        for local_idx, element in enumerate(elements):
            for sub in _subchunks(element):
                chunk_texts.append(sub)
                owner_local.append(local_idx)
        cache = derived / "embeddings" / f"{filing.accession}.npy"
        embeddings = np.load(cache) if cache.is_file() else None
        if embeddings is None or embeddings.shape[0] != len(chunk_texts):
            client = client or OpenAI()
            embeddings = _embed_texts(client, chunk_texts)
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, embeddings)
        base = len(all_elements)
        all_elements.extend(elements)
        chunk_owner.extend(base + li for li in owner_local)
        all_embeddings.append(embeddings)
    matrix = (
        np.vstack(all_embeddings).astype(np.float32)
        if all_embeddings
        else np.zeros((0, 1), dtype=np.float32)
    )
    bm25 = BM25Okapi([_tokens(e.text) for e in all_elements])
    return all_elements, bm25, matrix, np.asarray(chunk_owner, dtype=np.int64)


def build_index() -> int:
    """Force-build the embedding cache (used by the one-time build step). Returns n."""
    elements, _bm25, _matrix, _owner = _index()
    return len(elements)


def _parent_expand(elements: list[Element], indices: list[int]) -> list[Element]:
    """Add each hit's reading-order neighbors for fuller local context.

    The combined index lists each filing's Elements contiguously in ordinal order, so a
    hit's reading-order neighbors are simply the adjacent *list positions* — but only
    within the same filing (``source_filing``), never crossing a year boundary (ordinals
    repeat per filing, so keying on ordinal would mis-join across years)."""
    n = len(elements)
    keep: list[int] = []
    seen: set[int] = set()
    for idx in indices:
        for j in (idx - 1, idx, idx + 1):
            if (
                0 <= j < n
                and j not in seen
                and elements[j].source_filing == elements[idx].source_filing
            ):
                seen.add(j)
                keep.append(j)
    return [elements[j] for j in keep]


def hybrid_search(
    query: str, k: int = 8, expand: bool = True, fiscal_year: int | None = None
) -> list[Element]:
    """Top-k Elements by RRF(dense, sparse), optionally scoped to one fiscal year and
    parent-expanded. The dense side scores each Element by its best sub-chunk, so a long
    Element is found by whichever of its parts matches — no part is truncated out."""
    elements, bm25, chunk_matrix, chunk_owner = _index()

    sparse_rank = np.argsort(bm25.get_scores(_tokens(query)))[::-1]

    q = np.asarray(
        OpenAI().embeddings.create(model=_EMBED_MODEL, input=[query]).data[0].embedding,
        dtype=np.float32,
    )
    q /= np.linalg.norm(q) + 1e-9
    # Max-pool sub-chunk similarities up to their owning Element: an Element's dense
    # score is its single best-matching sub-chunk.
    chunk_scores = chunk_matrix @ q
    elem_scores = np.full(len(elements), -np.inf, dtype=np.float32)
    if chunk_owner.size:
        np.maximum.at(elem_scores, chunk_owner, chunk_scores)
    dense_rank = np.argsort(elem_scores)[::-1]

    rrf: dict[int, float] = {}
    for rank, idx in enumerate(sparse_rank[:80]):
        rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (_RRF_K + rank)
    for rank, idx in enumerate(dense_rank[:80]):
        rrf[int(idx)] = rrf.get(int(idx), 0.0) + 1.0 / (_RRF_K + rank)

    ranked = sorted(rrf, key=lambda i: rrf[i], reverse=True)
    if fiscal_year is not None:  # year-scoped retrieval (a metadata filter)
        ranked = [i for i in ranked if elements[i].fiscal_year == fiscal_year]
    top = ranked[:k]
    return _parent_expand(elements, top) if expand else [elements[i] for i in top]
