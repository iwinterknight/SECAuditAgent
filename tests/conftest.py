"""Shared pytest fixtures for the AuditAgent test suite.

Intentionally minimal at T1. Crucially it does **not** manipulate ``sys.path``
to make ``config`` / ``ingestion`` importable — that would mask a broken
package install. The packaging test must prove the *editable install* resolves
the imports, so the only way ``import config`` works here is a real install
(``uv pip install -e .``).

Later tasks add corpus fixtures here: accession→path fixtures derived from
``config.settings`` (T3), and session-scoped parsed/extracted fixtures so the
expensive parse runs once (T4, T6).
"""

import pytest

from config.schema import Element, XBRLFact
from config.settings import Filing, Settings, get_settings
from ingestion.elements import parse_elements
from ingestion.xbrl import extract_facts

# The FY2022 filing — its FY2022 figures are reported a second time, restated, as
# comparatives in the FY2024 filing. Paired with the FY2024 facts to prove the
# extractor keeps both (no cross-filing dedup); named here so the accession lives
# in one place.
_FY2022_ACCESSION = "0000019617-23-000231"


@pytest.fixture(scope="session")
def settings() -> Settings:
    """The one ``Settings`` object — the single source of every corpus path.

    Tests resolve paths through this fixture (never by hardcoding a string), so
    if the corpus layout moves there is exactly one place to change.
    """
    return get_settings()


@pytest.fixture(scope="session")
def sample_filing(settings: Settings) -> Filing:
    """One canonical filing (FY2024) for the parse-once fixtures T4/T6 add.

    Picking it by accession (not by list index) keeps the choice readable and
    routes through the same ``filing_for`` lookup the pipeline uses.
    """
    return settings.filing_for("0000019617-25-000270")


@pytest.fixture(scope="session")
def parsed_elements(settings: Settings, sample_filing: Filing) -> list[Element]:
    """The FY2024 10-K PDF parsed once into ``Element``s — the shared corpus for
    the provenance tests. Docling downloads its layout/table models on first use
    (one-time, network-dependent — hundreds of MB) and a full 10-K parse is
    multi-minute, so this runs a single time per session and every Element-shape
    test reads this list. It is the PDF-side twin of :func:`xbrl_facts`.
    """
    return parse_elements(
        settings.pdf_path(sample_filing),
        fiscal_year=sample_filing.fiscal_year,
        source_filing=sample_filing.accession,
    )


@pytest.fixture(scope="session")
def xbrl_facts(settings: Settings, sample_filing: Filing) -> list[XBRLFact]:
    """The FY2024 filing parsed once into ``XBRLFact``s — the shared corpus for
    the extraction tests. Parsing an iXBRL instance is multi-second, so it runs a
    single time per session and every fact-shape test reads this list.
    """
    accession_dir = settings.xbrl_dir / sample_filing.accession
    return extract_facts(accession_dir, source_filing=sample_filing.accession)


@pytest.fixture(scope="session")
def fy2022_facts(settings: Settings) -> list[XBRLFact]:
    """The FY2022 filing parsed once — paired with :func:`xbrl_facts` (FY2024) so
    the restatement test can show a prior-year figure survives from *both*
    filings, distinguished only by ``source_filing``.
    """
    accession_dir = settings.xbrl_dir / _FY2022_ACCESSION
    return extract_facts(accession_dir, source_filing=_FY2022_ACCESSION)


@pytest.fixture(scope="session")
def nil_numeric_concepts(settings: Settings, sample_filing: Filing) -> set[str]:
    """The concepts the FY2024 instance tags as *nil* numeric facts, read straight
    from Arelle.

    This is the independent ground truth ``extract_facts`` must skip: sourcing the
    nil set directly from the model (not from the extractor's own output) keeps the
    nil test from grading the extractor against itself.
    """
    from arelle import Cntlr

    instance = settings.xbrl_instance_path(sample_filing)
    cntlr = Cntlr.Cntlr(logFileName="logToBuffer")
    model = cntlr.modelManager.load(str(instance))
    try:
        return {str(fact.qname) for fact in model.facts if fact.isNumeric and fact.isNil}
    finally:
        model.close()
