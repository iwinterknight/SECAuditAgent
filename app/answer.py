"""Minimal RAG answer engine over the JPMorgan Chase 10-K derived corpus.

Narrative: BM25 keyword retrieval over the FY2024 Elements (parsed 10-K text,
tables, headings). Numbers: an authoritative *headline-facts table* served from a
**DuckDB** store over the exact XBRL facts (FY2021-FY2025) — the figures JPMorgan
actually filed. An OpenAI model synthesizes a grounded, cited answer, and is
instructed to quote financial figures verbatim from the XBRL table (the fidelity
rule: numbers never come from the model).
"""

from __future__ import annotations

import os
from functools import lru_cache

from openai import OpenAI
from rank_bm25 import BM25Okapi

import duckdb_store
from config.schema import Element, PeriodType
from config.settings import get_settings
from ingestion.serialize import read_jsonl


def _load_dotenv() -> None:
    """Load ``KEY=VALUE`` lines from a repo-root ``.env`` into the environment
    (no dependency), so ``OPENAI_API_KEY`` can live in a gitignored ``.env`` and be
    passed to Docker via ``--env-file``."""
    env_path = get_settings().project_root / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# We parsed the FY2024 PDF for narrative; the XBRL numbers span all five filings.
_NARRATIVE_ACCESSION = "0000019617-25-000270"  # FY2024
_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Headline metrics quoted in the demo. The exact values come from these XBRL
# facts (served by DuckDB), never from the model. (concept, human label, period shape.)
_HEADLINE = [
    ("us-gaap:Assets", "Total assets", PeriodType.INSTANT),
    ("us-gaap:Liabilities", "Total liabilities", PeriodType.INSTANT),
    ("us-gaap:StockholdersEquity", "Total stockholders' equity", PeriodType.INSTANT),
    ("us-gaap:Deposits", "Total deposits", PeriodType.INSTANT),
    ("us-gaap:NetIncomeLoss", "Net income", PeriodType.DURATION),
    ("us-gaap:Revenues", "Total net revenue", PeriodType.DURATION),
    ("us-gaap:InterestIncomeExpenseNet", "Net interest income", PeriodType.DURATION),
    ("us-gaap:EarningsPerShareDiluted", "Diluted EPS", PeriodType.DURATION),
]

_SYSTEM = """You are a financial-analysis assistant for JPMorgan Chase & Co.'s 10-K filings.

Rules:
- Use ONLY the provided context: narrative excerpts (from the FY2024 10-K) and the \
authoritative XBRL financial-facts table (FY2021-FY2025).
- For ANY financial figure, use the EXACT value from the XBRL facts table. These are \
the numbers JPMorgan filed; never estimate, re-round, or compute your own.
- The narrative excerpts are from the FY2024 10-K only; note that if asked about \
another year's narrative.
- Cite narrative claims as (FY2024, p.<page>).
- If the context does not contain the answer, say you don't have it — do not invent.
- Be concise and concrete."""


def _tokens(text: str) -> list[str]:
    return text.lower().split()


@lru_cache(maxsize=1)
def load_corpus() -> tuple[list[Element], BM25Okapi, dict]:
    """Load Elements + BM25 index + the headline-facts table (built once).

    Narrative Elements come from the parsed PDF JSONL; the headline numbers are served
    by the **DuckDB** fact store (``duckdb_store.headline_value`` — the consolidated,
    dimensionless fact per concept/year), so the numeric path runs through SQL truth."""
    settings = get_settings()
    derived = settings.derived_dir / "ingestion"

    elements: list[Element] = []
    for filing in settings.FILINGS:  # every parsed filing's narrative (FY2021-2025)
        path = derived / "elements" / f"{filing.accession}.jsonl"
        if path.is_file():
            elements.extend(e for e in read_jsonl(path, Element) if len(e.text) > 40)
    bm25 = BM25Okapi([_tokens(e.text) for e in elements])

    table: dict[tuple[str, int], tuple] = {}  # (label, fy) -> (value, unit)
    for filing in settings.FILINGS:
        for concept, label, period_type in _HEADLINE:
            value_unit = duckdb_store.headline_value(
                concept, period_type, filing.fiscal_year
            )
            if value_unit is not None:
                table[(label, filing.fiscal_year)] = value_unit
    return elements, bm25, table


def _facts_block(table: dict) -> str:
    years = sorted({fy for (_, fy) in table})
    lines = ["XBRL financial facts (USD in millions unless noted; exact as filed):"]
    for _concept, label, _pt in _HEADLINE:
        cells = []
        for fy in years:
            value_unit = table.get((label, fy))
            if not value_unit:
                continue
            value, unit = value_unit
            if unit == "USD":
                cells.append(f"FY{fy}={int(value) // 1_000_000:,}")
            else:
                cells.append(f"FY{fy}={value} {unit}")
        if cells:
            lines.append(f"- {label}: " + "; ".join(cells))
    return "\n".join(lines)


def answer(question: str, k: int = 8) -> tuple[str, list[Element]]:
    """Answer a question; returns (answer_text, the cited narrative Elements)."""
    elements, bm25, table = load_corpus()
    scores = bm25.get_scores(_tokens(question))
    ranked = sorted(range(len(elements)), key=lambda i: scores[i], reverse=True)[:k]
    hits = [elements[i] for i in ranked]

    narrative = "\n\n".join(
        f"[FY2024 p.{e.page} | {e.kind.value}] {e.text[:700]}" for e in hits
    )
    user = (
        f"CONTEXT — XBRL FACTS:\n{_facts_block(table)}\n\n"
        f"CONTEXT — NARRATIVE EXCERPTS (FY2024 10-K):\n{narrative}\n\n"
        f"QUESTION: {question}"
    )
    client = OpenAI()
    response = client.chat.completions.create(
        model=_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content, hits
