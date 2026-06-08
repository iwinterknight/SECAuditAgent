"""The ingestion pipeline — the one place the PDF<->accession<->FY join is resolved.

Everything upstream is a pure producer that knows nothing about *which* filings
exist: ``parse_elements`` takes a PDF path, ``extract_facts`` takes an accession
dir, ``assign_items`` takes Elements, ``write_jsonl`` takes rows and a path. This
module is the orchestrator that ties them to the corpus — it reads
``Settings.FILINGS`` (the sole PDF<->accession<->fiscal-year join) and, per filing,
runs both lanes into the gitignored derived corpus:

    PDF  -> parse_elements -> assign_items -> write_jsonl  (elements/{accession}.jsonl)
    iXBRL -> extract_facts                 -> write_jsonl  (facts/{accession}.jsonl)

Three contract points (plan + Constitution):

- **The join lives only here.** No other module re-derives a fiscal year from a
  filename or guesses an accession; they receive provenance as arguments. This is
  the single place ``Settings.FILINGS`` is consumed for ingestion.
- **An unknown accession is a hard error**, validated *before* any parsing, so a
  typo fails loud immediately rather than silently producing an empty corpus that
  looks like success (§1.5 fail-closed).
- **Source is read-only; output is rebuildable.** The pipeline writes only under
  the gitignored ``data/derived/`` and never mutates ``data/SEC/`` (§1.8). Because
  serialization is byte-identical (T9), a second ``run()`` over unchanged source
  reproduces the corpus exactly — which is what makes the derived bundle a
  trustworthy *bake-once-reuse* deployment artifact (verify by diffing bytes).

CLI: ``python -m ingestion.pipeline [accession ...]`` — no args rebuilds all five
filings; an explicit list rebuilds that subset.
"""

import logging
import sys
from pathlib import Path

from config.settings import Filing, Settings, get_settings
from ingestion.elements import parse_elements
from ingestion.sections import assign_items
from ingestion.serialize import write_jsonl
from ingestion.xbrl import extract_facts

logger = logging.getLogger(__name__)


def _elements_path(settings: Settings, accession: str) -> Path:
    """Derived JSONL path for a filing's Element stream (gitignored)."""
    return settings.derived_dir / "ingestion" / "elements" / f"{accession}.jsonl"


def _facts_path(settings: Settings, accession: str) -> Path:
    """Derived JSONL path for a filing's XBRLFact stream (gitignored)."""
    return settings.derived_dir / "ingestion" / "facts" / f"{accession}.jsonl"


def _rebuild_filing(filing: Filing, settings: Settings) -> None:
    """Rebuild one filing's two derived streams from its read-only source artifacts.

    The narrative lane parses the PDF into Elements and stamps the 10-K Item; the
    numeric lane reads the iXBRL instance into XBRLFacts. Each stream is written to
    its own gitignored JSONL (``write_jsonl`` creates parent dirs and sorts
    deterministically). The two lanes share no number — the §1.2 firewall.
    """
    elements = assign_items(
        parse_elements(
            settings.pdf_path(filing),
            fiscal_year=filing.fiscal_year,
            source_filing=filing.accession,
        )
    )
    write_jsonl(elements, _elements_path(settings, filing.accession))

    facts = extract_facts(
        settings.xbrl_dir / filing.accession,
        source_filing=filing.accession,
    )
    write_jsonl(facts, _facts_path(settings, filing.accession))

    logger.info(
        "rebuilt %s (FY%d): %d Elements, %d XBRLFacts",
        filing.accession,
        filing.fiscal_year,
        len(elements),
        len(facts),
    )


def run(accessions: list[str] | None = None) -> None:
    """Rebuild the derived corpus for ``accessions`` — or all five filings if None.

    Resolves (and thereby validates) every accession against ``Settings.FILINGS``
    *up front*: an unknown accession raises before any expensive parsing, so a typo
    can never masquerade as a successful-but-empty run. Writes only under the
    gitignored ``data/derived/``.
    """
    settings = get_settings()
    filings = (
        list(settings.FILINGS)
        if accessions is None
        else [settings.filing_for(accession) for accession in accessions]
    )
    logger.info("ingestion pipeline: rebuilding %d filing(s)", len(filings))
    for filing in filings:
        _rebuild_filing(filing, settings)
    logger.info("ingestion pipeline: done (%d filing(s))", len(filings))


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: ``python -m ingestion.pipeline [accession ...]``.

    No arguments rebuilds all five filings; an explicit accession list rebuilds
    that subset. Configures logging at the boundary so the per-filing progress is
    visible.
    """
    from config.logging import configure_logging

    configure_logging()
    args = list(sys.argv[1:]) if argv is None else list(argv)
    run(args or None)


if __name__ == "__main__":
    main()
