# Gathered context — JPMorgan 10-K Agentic RAG presentation

Running capture from the deep-dive sessions: one fact + its insight per entry.
Compose into a presentation-ready summary with `/collate`.

---

### [1] PRESENTATION DIRECTIVE — "Domain understanding" cluster
- **Category:** decision
- **Fact:** Entries [2]–[6] (firewall; iXBRL + standards + who-tags/who-audits; audited-vs-untagged tags; Arelle; Docling) form ONE presentation section titled "Domain understanding."
- **Insight:** Showcase domain fluency, but briefly — keep the depth in these notes; on stage cap this whole section at **≤ 2 slides / 4–5 minutes total**.
- **Source:** user directive, this session

### [2] The §1.2 firewall — numbers only from XBRL
- **Category:** decision
- **Fact:** Financial figures are constructed in exactly one place — the XBRL path (`src/ingestion/xbrl.py`); the PDF/Docling path never builds a figure, and `XBRLFact` is defined and constructed in a single module. At answer time a validator re-checks every stated number against the tool outputs.
- **Insight:** Turns "the model can't invent a number" into a *structural* guarantee rather than a hope — the foundation of trust for financial QA.
- **Sayable:** "Numbers come only from XBRL — never the LLM or the parsed PDF — enforced by a single fact-constructor plus a runtime validator."
- **Cluster:** Domain understanding
- **Source:** docs/guide/01-data-foundation.md; app/agent.py `_validate`

### [3] iXBRL — the document, its standards, and who tags vs. audits
- **Category:** xbrl
- **Fact:** A 10-K is filed as **inline eXtensible Business Reporting Language (iXBRL)** — one document that is human-readable HTML with machine-readable tags embedded around each number. Chain of responsibility:
  - **Who composes it:** the *registrant* (the filing company — JPMorgan Chase & Co.), via its financial-reporting team, typically using disclosure-management software / a filing agent (e.g. Workiva, DFIN, Toppan Merrill).
  - **Tagged against which standards:** the data model is **eXtensible Business Reporting Language (XBRL)** from XBRL International; the concept vocabulary is the **United States Generally Accepted Accounting Principles (US GAAP)** Financial Reporting Taxonomy from the **Financial Accounting Standards Board (FASB)**, plus the **Document and Entity Information (DEI)** taxonomy for cover-page fields. Filing inline XBRL is mandated by the **U.S. Securities and Exchange Commission (SEC)** and submitted through **Electronic Data Gathering, Analysis, and Retrieval (EDGAR)**.
  - **Who audits what:** the financial *statements* are audited by an independent registered public accounting firm — for JPMorgan, **PricewaterhouseCoopers (PwC)** — under oversight of the **Public Company Accounting Oversight Board (PCAOB)**. The XBRL *tagging itself* is generally **not** separately audited; EDGAR runs only structural validation.
- **Insight:** The numbers arrive as a standards-governed, machine-readable artifact with a clear chain of responsibility — and the *audited* thing (the statements) is not the same as the *tagging*.
- **Sayable:** "The filer (JPMorgan) tags its own filing in inline XBRL against FASB's US-GAAP taxonomy, mandated by the SEC via EDGAR; PwC audits the statements, but not the tags."
- **Cluster:** Domain understanding
- **Source:** docs/guide/01-data-foundation.md; session Q&A

### [4] Audited statements vs. un-audited XBRL tags
- **Category:** xbrl
- **Fact:** The printed financial statements are audited (external accounting firm, PCAOB oversight); the XBRL tags are the filer's own, generally **un-audited** assertion (EDGAR validates structure only).
- **Insight:** So the XBRL reader trusts tags over parsed prose but *not blindly* — it keeps the most precise of duplicate taggings, flags genuinely contradictory ones, and skips nil/unparseable facts rather than coercing a false zero.
- **Sayable:** "We trust XBRL over prose, but not blindly — the tags aren't independently audited, so we defend against tagging errors (dedupe to most-precise, flag contradictions, skip-not-coerce)."
- **Cluster:** Domain understanding
- **Source:** src/ingestion/xbrl.py:124 (`_dedupe_facts`); :162 (`_build_fact`)

### [5] Arelle — one-liner
- **Category:** xbrl
- **Fact:** Arelle is the open-source reference XBRL engine.
- **Insight:** Used purely as an **offline reader** (resolves transforms / periods / dimensions into typed facts) and deliberately kept out of the runtime image — the container serves pre-extracted facts.
- **Sayable:** "Arelle is the open-source reference XBRL engine; we use it as an offline reader and keep it out of the serving image."
- **Cluster:** Domain understanding
- **Source:** src/ingestion/xbrl.py

### [6] Docling — one-liner
- **Category:** docling
- **Fact:** Docling parses each 10-K PDF with a layout model + TableFormer into reading-order Elements.
- **Insight:** Run with a lean model config and **16-page windowing** so a 300-page filing parses on a few GB of RAM without OOM.
- **Sayable:** "Docling turns the PDF into reading-order text + tables; we window it 16 pages at a time to avoid OOM."
- **Cluster:** Domain understanding
- **Source:** src/ingestion/elements.py
