"""T3 acceptance — the FILINGS table is the single, on-disk-true source of the
PDF↔accession↔fiscal-year join.

The named acceptance check (``test_filings_table_resolves``) proves two things at
once: the table's ``accession → fiscal_year`` mapping is exactly the five known
filings, and every row points at source artifacts that actually exist on disk
under the *settings-rooted* paths. That second half is what makes the table
trustworthy as the join's single source of truth (settings §1.7, plan §73-80) —
a row naming a file that isn't there would be a latent provenance bug.

Two companions pin the contracts this task introduces around that table: the
``get_settings`` singleton (§1.7, "one settings object") and the derived
``accession_to_fy`` map staying consistent with ``FILINGS``.
"""

from config.settings import Settings, get_settings

# The ground truth, written here independently of the table under test so the
# test can't "agree with itself" — five distinct accessions, one per fiscal year.
EXPECTED_FY: dict[str, int] = {
    "0000019617-22-000272": 2021,
    "0000019617-23-000231": 2022,
    "0000019617-24-000225": 2023,
    "0000019617-25-000270": 2024,
    "0001628280-26-008131": 2025,
}


def test_filings_table_resolves(settings: Settings) -> None:
    # exactly the five known filings — no more, no fewer
    assert len(settings.FILINGS) == len(EXPECTED_FY)

    seen: set[str] = set()
    for filing in settings.FILINGS:
        # accession → fiscal_year is the expected mapping
        assert filing.accession in EXPECTED_FY, (
            f"unexpected accession {filing.accession!r}"
        )
        assert filing.fiscal_year == EXPECTED_FY[filing.accession], (
            f"{filing.accession} should be FY{EXPECTED_FY[filing.accession]}, "
            f"got FY{filing.fiscal_year}"
        )
        seen.add(filing.accession)

        # each row's source artifacts exist on disk under settings-rooted paths
        assert settings.pdf_path(filing).exists(), (
            f"missing source PDF for {filing.accession}: {settings.pdf_path(filing)}"
        )
        assert settings.xbrl_instance_path(filing).exists(), (
            f"missing iXBRL instance for {filing.accession}: "
            f"{settings.xbrl_instance_path(filing)}"
        )

    # all five distinct accessions were present (no duplicate masking a gap)
    assert seen == set(EXPECTED_FY)


def test_get_settings_is_cached_singleton() -> None:
    # §1.7 "one settings object": every caller shares the same instance
    assert get_settings() is get_settings()


def test_accession_to_fy_consistent_with_filings(settings: Settings) -> None:
    # the derived map must agree with the table it is derived from
    assert settings.accession_to_fy == {
        f.accession: f.fiscal_year for f in settings.FILINGS
    }
