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

from config.settings import Filing, Settings, get_settings


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
