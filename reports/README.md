# reports/ — Educator Reports

This directory holds the **Educator Reports** mandated by the Reporting
Protocol (`docs/constitution.md` §2). After **every** SDD step — CLARIFY,
PLAN, TASKS, IMPLEMENT, EVALUATE — a report is produced *before* advancing to
the next step. Its purpose is the lead's complete, ground-up **360°
understanding** of AuditAgent: each report starts at the architecture /
domain level and drills down to the specific files and what their code does,
and it *teaches the domain* (XBRL, EDGAR, iXBRL, the DuckDB-vs-Qdrant split,
RAG / agent design, framework and package choices) rather than just listing
the diff.

## Layout

One folder per spec, mirroring `specs/<spec-slug>/`:

```
reports/
├── render.py              ← Markdown → PDF renderer (tooling, not app code)
├── requirements.txt       ← renderer deps (markdown, xhtml2pdf)
├── README.md              ← this file
└── <YYYY-MM-DD-slug>/
    ├── 01-clarify.md      ← after /spec
    ├── 02-plan.md         ← after /plan
    ├── 03-tasks.md        ← after /tasks
    ├── 04-implement-T1.md ← after /implement T1 (one per task)
    ├── 04-implement-T2.md
    ├── 05-evaluate.md     ← after /evaluate
    └── *.pdf              ← rendered siblings (gitignored, rebuildable)
```

The `NN-` prefix keeps the reports in SDD order; the `-T<N>` suffix
disambiguates the one-per-task IMPLEMENT reports.

## Source of truth

**Markdown is committed; PDF is not.** The `.md` files are the durable,
reviewable source of truth and are tracked in git. The `.pdf` files are
*rendered* from them, rebuildable, and therefore gitignored (Constitution
§5.2 — derived artifacts are not committed). Read the PDFs locally; edit the
Markdown.

## Rendering

The renderer is pure-Python (no system libraries):

```bash
pip install -r reports/requirements.txt

python reports/render.py                              # render every stale/missing PDF
python reports/render.py reports/<slug>/01-clarify.md # render one report (forced)
python reports/render.py reports/<slug>/              # render a whole spec folder
python reports/render.py --all                        # re-render everything
```

## Authoring

Start from `.claude/skills/sdd-feature-cycle/templates/report-template.md`.
Each report follows the same high→low arc: orientation → domain teaching →
architecture view → stage-specific drill-down (the two-level **Code
Walkthrough** at IMPLEMENT) → decisions & trade-offs → open threads.
