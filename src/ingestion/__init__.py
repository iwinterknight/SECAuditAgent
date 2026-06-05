"""Ingestion: turn each source filing into normalized, provenance-tagged data.

The bottom of the data-flow chain (architecture §4) and the first producer of
the system's typed contracts. Two **independent** producers will live here,
kept deliberately separate so financial numbers originate only from XBRL
(Constitution §1.2 — the structural firewall):

- the **PDF path** — ``ingestion.elements`` → ``Element`` (text/table/heading
  with FY / Item / page provenance), with ``ingestion.sections`` stamping the
  10-K Item afterwards;
- the **XBRL path** — ``ingestion.xbrl`` → ``XBRLFact`` (the *sole* place an
  ``XBRLFact`` is constructed).

Plus ``ingestion.serialize`` (deterministic JSONL) and ``ingestion.pipeline``
(the join + rebuild CLI). This layer imports ``config`` only; these modules
arrive in later M1 tasks (T4, T6, T7, T9, T10). This package is the skeleton.
"""
