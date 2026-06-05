"""The single settings object — corpus paths and the authoritative filing table.

Constitution §1.7: configuration flows through exactly one ``config.settings``
object; business code never calls ``os.getenv`` and never hardcodes an absolute
path. Everything that needs to know "where is the corpus" or "which filings
exist" asks here.

The load-bearing piece is ``FILINGS`` — the one place the
**PDF ↔ accession ↔ fiscal-year** join is written down. A JPM 10-K PDF is named
by its period-end date (``jpm-20241231.pdf``) while its ``source_filing`` tag and
every derived path are keyed by the SEC **accession** (``0000019617-25-000270``).
Those two namings must never be allowed to disagree, so they are tied together in
a single ordered table; the filename date is never independently re-parsed for a
fiscal year anywhere else (a §1.5-style single-source-of-truth discipline applied
to provenance). ``ingestion.pipeline`` (M1/T10) reads this table and nothing
re-derives the join.
"""

from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# settings.py lives at <root>/src/config/settings.py, so the project root is two
# parents up from the package dir. Computed from __file__ rather than hardcoded
# so a fresh clone anywhere on disk resolves correctly (Constitution §3).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Filing(BaseModel):
    """One filing's identity and its two on-disk source artifacts.

    ``accession`` is the SEC accession-number folder and the canonical
    ``source_filing`` key; ``fiscal_year`` is the FY the filing reports on; and
    the two filenames locate the rendered PDF (the Element source) and the
    inline-XBRL instance (the XBRLFact source) under the corpus roots below.
    """

    accession: str
    fiscal_year: int
    pdf_filename: str  # under corpus_pdf_dir, named by period-end date
    xbrl_instance: str  # the iXBRL .htm under xbrl_dir/<accession>/


class Settings(BaseSettings):
    """Process-wide configuration: corpus roots, the derived-output root, and
    the filing manifest.

    Path roots are derived from ``project_root`` (overridable via
    ``AUDITAGENT_PROJECT_ROOT`` for a relocated checkout) so no absolute path is
    baked into the code. ``FILINGS`` is a ``ClassVar`` — the corpus is fixed in
    the repo, so the manifest is code, not environment-tunable config.
    """

    model_config = SettingsConfigDict(
        env_prefix="AUDITAGENT_",
        env_file=".env",
        extra="ignore",
    )

    project_root: Path = _PROJECT_ROOT
    log_level: str = "INFO"

    # The authoritative PDF↔accession↔FY join, ordered by fiscal year. The sole
    # definition of which filings exist and how their artifacts are named.
    FILINGS: ClassVar[tuple[Filing, ...]] = (
        Filing(
            accession="0000019617-22-000272",
            fiscal_year=2021,
            pdf_filename="jpm-20211231.pdf",
            xbrl_instance="jpm-20211231.htm",
        ),
        Filing(
            accession="0000019617-23-000231",
            fiscal_year=2022,
            pdf_filename="jpm-20221231.pdf",
            xbrl_instance="jpm-20221231.htm",
        ),
        Filing(
            accession="0000019617-24-000225",
            fiscal_year=2023,
            pdf_filename="jpm-20231231.pdf",
            xbrl_instance="jpm-20231231.htm",
        ),
        Filing(
            accession="0000019617-25-000270",
            fiscal_year=2024,
            pdf_filename="jpm-20241231.pdf",
            xbrl_instance="jpm-20241231.htm",
        ),
        Filing(
            accession="0001628280-26-008131",
            fiscal_year=2025,
            pdf_filename="jpm-20251231.pdf",
            xbrl_instance="jpm-20251231.htm",
        ),
    )

    @property
    def corpus_pdf_dir(self) -> Path:
        """Where the read-only source 10-K PDFs live (the Element source)."""
        return self.project_root / "data" / "SEC" / "10-K Filings" / "yearly"

    @property
    def xbrl_dir(self) -> Path:
        """Root of the vendored iXBRL packages, one accession folder each."""
        return self.project_root / "data" / "SEC" / "10-K Filings" / "xbrl"

    @property
    def derived_dir(self) -> Path:
        """Gitignored root for rebuildable derived output (§1.8); never source."""
        return self.project_root / "data" / "derived"

    @property
    def accession_to_fy(self) -> dict[str, int]:
        """The accession→fiscal-year map, derived from ``FILINGS`` (one source)."""
        return {f.accession: f.fiscal_year for f in self.FILINGS}

    def filing_for(self, accession: str) -> Filing:
        """The ``Filing`` for an accession, or a hard error on an unknown one.

        Failing loud here is deliberate: a mistyped accession must not silently
        look like "no filings" downstream (the §1.5 fail-closed posture).
        """
        for filing in self.FILINGS:
            if filing.accession == accession:
                return filing
        raise KeyError(f"unknown accession: {accession!r}")

    def pdf_path(self, filing: Filing) -> Path:
        """Absolute path to a filing's source PDF under the corpus root."""
        return self.corpus_pdf_dir / filing.pdf_filename

    def xbrl_instance_path(self, filing: Filing) -> Path:
        """Absolute path to a filing's iXBRL instance under its accession dir."""
        return self.xbrl_dir / filing.accession / filing.xbrl_instance


@lru_cache
def get_settings() -> Settings:
    """The one ``Settings`` instance for the process (§1.7).

    ``lru_cache`` makes this a singleton: every caller shares the same object,
    so configuration is read once and can't drift between modules.
    """
    return Settings()
