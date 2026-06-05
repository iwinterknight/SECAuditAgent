"""Shared cross-layer contracts, settings, and logging for AuditAgent.

This is the lowest layer (Constitution §1.6 — imports flow downward only;
``config`` imports nothing above it). It will hold:

- ``config.schema``   — the typed contracts ``Element`` and ``XBRLFact`` (+ the
  ``ElementKind`` / ``PeriodType`` / ``Entity`` enums). Defined here, and only
  here, so every layer above imports them from one place (architecture §5).
- ``config.settings`` — one ``pydantic-settings`` object (corpus paths, the
  ``FILINGS`` accession↔fiscal-year map, the gitignored derived root).
- ``config.logging``  — the logging skeleton (no ``print``).

These modules arrive in later M1 tasks (T2, T3); this package is the skeleton.
"""
