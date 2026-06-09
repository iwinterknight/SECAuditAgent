"""DuckDB-backed XBRL fact store — the numeric half of the M3 store design.

Why DuckDB and not the vector store for numbers: a financial figure is a *keyed,
exact* lookup (entity + concept + period), which is a relational/SQL problem — vector
search is approximate by design and wrong for "the one true filed figure." DuckDB is an
embedded, in-process OLAP engine (no server), so it fits the lean single-container
deploy: it loads the baked ``facts/*.jsonl`` into an in-memory table once and answers
exact SQL lookups.

**Fidelity carries over from the §1.2 firewall.** ``value`` stays a string end to end
(read as ``VARCHAR``, returned as ``Decimal``) — never a binary float. And the
headline lookup replicates ``answer._headline_fact`` exactly: the single
**consolidated, dimensionless** fact whose period matches — so a *dimensional*
breakdown (``us-gaap:Assets`` by segment) can never be mistaken for the top-line total.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

import duckdb

from config.schema import PeriodType
from config.settings import get_settings


@lru_cache(maxsize=1)
def _conn() -> duckdb.DuckDBPyConnection:
    """Build the in-process fact store once: load every filing's ``facts/*.jsonl`` into
    one table, stamping ``fiscal_year`` from the authoritative accession→FY map (the
    same single-source join the pipeline uses; never re-derived from a date)."""
    settings = get_settings()
    facts_glob = (
        (settings.derived_dir / "ingestion" / "facts").as_posix() + "/*.jsonl"
    )
    conn = duckdb.connect()  # in-memory; rebuilt per process from the baked JSONL
    conn.execute("CREATE TABLE acc_fy(source_filing VARCHAR, fiscal_year INTEGER)")
    conn.executemany(
        "INSERT INTO acc_fy VALUES (?, ?)",
        list(settings.accession_to_fy.items()),
    )
    # union_by_name tolerates any per-file column variance; value stays VARCHAR so the
    # exact filed digits survive (cast to DECIMAL only when doing math, in the calc tool).
    conn.execute(
        f"""
        CREATE TABLE facts AS
        SELECT f.*, m.fiscal_year
        FROM read_json_auto('{facts_glob}', union_by_name=true) f
        LEFT JOIN acc_fy m USING (source_filing)
        """
    )
    return conn


def headline_value(
    concept: str, period_type: PeriodType, fiscal_year: int
) -> tuple[Decimal, str] | None:
    """The single consolidated, dimensionless fact for a concept in a fiscal year —
    the SQL twin of ``answer._headline_fact``. Returns ``(Decimal value, unit)`` or None.

    Ordered by ``fact_id`` so the choice is deterministic and matches the JSONL-order
    pick of the original (the streams are written sorted by ``fact_id``)."""
    conn = _conn()
    base = (
        "SELECT value, unit FROM facts "
        "WHERE concept = ? AND entity = 'JPMC_CONSOLIDATED' "
        "AND (dimensions IS NULL OR cardinality(dimensions) = 0) "
        "AND period_type = ? "
    )
    if period_type is PeriodType.INSTANT:
        sql = base + "AND period_instant = make_date(?, 12, 31) ORDER BY fact_id LIMIT 1"
        row = conn.execute(sql, [concept, "instant", fiscal_year]).fetchone()
    else:
        sql = (
            base + "AND period_start = make_date(?, 1, 1) "
            "AND period_end = make_date(?, 12, 31) ORDER BY fact_id LIMIT 1"
        )
        row = conn.execute(
            sql, [concept, "duration", fiscal_year, fiscal_year]
        ).fetchone()
    if row is None:
        return None
    return (Decimal(row[0]), row[1])
