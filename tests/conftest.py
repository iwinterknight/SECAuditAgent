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
