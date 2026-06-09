"""Qdrant vector store (app/vector_store.py) — build + dense search + payload filter.
Offline: synthetic vectors, no embeddings or network.
"""

import pytest

np = pytest.importorskip("numpy")
vector_store = pytest.importorskip("vector_store")


def _normed(rows: list[list[float]]):
    arr = np.asarray(rows, dtype=np.float32)
    return arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)


def test_dense_elements_orders_by_similarity_and_maps_to_owner():
    vectors = _normed([[1, 0, 0, 0], [0, 1, 0, 0], [0.9, 0.1, 0, 0]])
    payloads = [
        {"owner": 10, "fiscal_year": 2024},
        {"owner": 20, "fiscal_year": 2022},
        {"owner": 30, "fiscal_year": 2024},
    ]
    client = vector_store.build(vectors, payloads)
    owners = vector_store.dense_elements(client, _normed([[1, 0, 0, 0]])[0], limit=10)
    assert owners[0] in (10, 30)  # the two vectors near [1,0,0,0] rank first
    assert set(owners) == {10, 20, 30}


def test_owner_is_deduplicated_and_kept_at_best_rank():
    # two sub-chunks share owner 1; it must appear once, at its best position
    vectors = _normed([[1, 0], [0, 1], [0.95, 0.05]])
    payloads = [
        {"owner": 1, "fiscal_year": 2024},
        {"owner": 2, "fiscal_year": 2024},
        {"owner": 1, "fiscal_year": 2024},
    ]
    client = vector_store.build(vectors, payloads)
    owners = vector_store.dense_elements(client, _normed([[1, 0]])[0], limit=10)
    assert owners.count(1) == 1
    assert owners[0] == 1


def test_payload_filter_scopes_to_fiscal_year():
    vectors = _normed([[1, 0], [0.99, 0.01]])
    payloads = [{"owner": 1, "fiscal_year": 2024}, {"owner": 2, "fiscal_year": 2022}]
    client = vector_store.build(vectors, payloads)
    owners = vector_store.dense_elements(
        client, _normed([[1, 0]])[0], limit=10, fiscal_year=2022
    )
    assert owners == [2]  # only the FY2022 point survives the payload filter
