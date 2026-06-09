"""Qdrant-backed vector store — the narrative half of the M3 store design.

**Embedded** Qdrant (in-memory, no server), built once per process from the baked
sub-chunk embeddings — so it preserves the lean single-container deploy (no sidecar to
run). One point per **sub-chunk**: the vector plus a payload carrying the owning Element
index and its metadata (``fiscal_year``, ``page``, ``item``, ``kind``,
``source_filing``), which makes payload-filtered search (by year, by 10-K Item, …)
available. A sub-chunk hit maps back to its owning Element (best score wins), so the rest
of retrieval — RRF fusion with BM25, the year filter, parent-expansion — stays at the
Element level, exactly as before.

Why a vector DB at all (vs. the raw numpy matrix): it's the designed query-time store —
it owns the vectors + payload + metadata-filtered ANN, and scales past what a single
in-process matrix comfortably holds. At this corpus size the numpy path was equivalent;
Qdrant is the architecture this was always meant to run on.
"""

from __future__ import annotations

import numpy as np
from qdrant_client import QdrantClient, models

_COLLECTION = "chunks"
_UPSERT_BATCH = 1000


def build(vectors: np.ndarray, payloads: list[dict]) -> QdrantClient:
    """Create an in-memory collection and upsert one point per sub-chunk vector+payload.

    Vectors are already L2-normalized, so cosine distance == dot product. ``id`` is the
    sub-chunk's row index; ``payload['owner']`` is the index of its owning Element."""
    client = QdrantClient(":memory:")
    dim = int(vectors.shape[1])
    client.create_collection(
        _COLLECTION,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
    )
    points = [
        models.PointStruct(id=i, vector=vectors[i].tolist(), payload=payloads[i])
        for i in range(len(payloads))
    ]
    for start in range(0, len(points), _UPSERT_BATCH):
        client.upsert(_COLLECTION, points=points[start : start + _UPSERT_BATCH])
    return client


def dense_elements(
    client: QdrantClient,
    query_vec: np.ndarray,
    limit: int = 300,
    fiscal_year: int | None = None,
) -> list[int]:
    """Dense search → ordered, de-duplicated **owning Element** indices (best sub-chunk
    first). ``fiscal_year`` applies a Qdrant **payload filter** so the dense candidates
    are year-scoped at the source when requested."""
    query_filter = None
    if fiscal_year is not None:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="fiscal_year", match=models.MatchValue(value=fiscal_year)
                )
            ]
        )
    hits = client.query_points(
        _COLLECTION, query=query_vec.tolist(), limit=limit, query_filter=query_filter
    ).points
    ranked: list[int] = []
    seen: set[int] = set()
    for hit in hits:
        owner = int(hit.payload["owner"])
        if owner not in seen:
            seen.add(owner)
            ranked.append(owner)
    return ranked
