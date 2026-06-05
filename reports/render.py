"""Render AuditAgent Educator Reports from Markdown to PDF.

Tooling, **not** application code: this lives outside ``src/`` and is no part
of the agent runtime. It converts the committed Markdown reports under
``reports/<spec-slug>/`` into sibling PDFs for the lead to peruse. Markdown is
the source of truth; the PDFs are rebuildable and gitignored (Constitution
§2 Reporting Protocol, §5.2).

Usage
-----
    python reports/render.py                       # render every report whose PDF is missing or stale
    python reports/render.py reports/<slug>/01-clarify.md   # render one file (forced)
    python reports/render.py reports/<slug>/                # render a folder (forced)
    python reports/render.py --all                          # re-render everything

Dependencies (doc-tooling only, deliberately isolated from app packaging,
which M1 owns):
    pip install -r reports/requirements.txt
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger("reports.render")

REPORTS_DIR = Path(__file__).resolve().parent

# Markdown files under reports/ that are not themselves reports.
_NON_REPORT_NAMES = {"README.md"}

# Print styling. xhtml2pdf supports a subset of CSS 2.1; keep it modest.
_CSS = """
@page { size: a4 portrait; margin: 2cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt;
       line-height: 1.4; color: #1a1a1a; }
h1 { font-size: 18pt; border-bottom: 2pt solid #333; padding-bottom: 4pt; }
h2 { font-size: 14pt; margin-top: 16pt; border-bottom: 1pt solid #bbb;
     padding-bottom: 2pt; }
h3 { font-size: 12pt; margin-top: 12pt; }
code, pre { font-family: Courier, monospace; font-size: 9pt;
            background-color: #f4f4f4; }
pre { padding: 6pt; border: 1pt solid #ddd; }
blockquote { color: #555; border-left: 3pt solid #ccc; margin-left: 0;
             padding-left: 10pt; }
table { border-collapse: collapse; }
th, td { border: 1pt solid #999; padding: 4pt 6pt; font-size: 9pt;
         text-align: left; }
th { background-color: #eeeeee; }
a { color: #1a4f8b; text-decoration: none; }
"""


def _require_deps() -> None:
    """Fail early and helpfully if the doc-tooling deps are not installed."""
    try:
        import markdown  # noqa: F401
        from xhtml2pdf import pisa  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing report-tooling dependency. Install with:\n"
            "    pip install -r reports/requirements.txt\n"
            f"(import error: {exc})"
        )


def _md_to_html(md_text: str, title: str) -> str:
    import markdown

    body = markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "toc", "tables", "fenced_code"],
    )
    return (
        "<html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style><title>{title}</title></head>"
        f"<body>{body}</body></html>"
    )


def _html_to_pdf(html: str, out_path: Path) -> None:
    from xhtml2pdf import pisa

    with out_path.open("wb") as fh:
        result = pisa.CreatePDF(src=html, dest=fh, encoding="utf-8")
    if result.err:
        raise RuntimeError(
            f"xhtml2pdf reported {result.err} error(s) rendering {out_path}"
        )


def render_one(md_path: Path) -> Path:
    """Render a single report Markdown file to a sibling PDF; return its path."""
    pdf_path = md_path.with_suffix(".pdf")
    html = _md_to_html(md_path.read_text(encoding="utf-8"), md_path.stem)
    _html_to_pdf(html, pdf_path)
    logger.info("rendered %s -> %s", md_path, pdf_path.name)
    return pdf_path


def _is_stale(md_path: Path) -> bool:
    pdf_path = md_path.with_suffix(".pdf")
    if not pdf_path.exists():
        return True
    return md_path.stat().st_mtime > pdf_path.stat().st_mtime


def _iter_reports(target: Path) -> Iterator[Path]:
    if target.is_file():
        yield target
        return
    for md in sorted(target.rglob("*.md")):
        if md.name in _NON_REPORT_NAMES:
            continue
        yield md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render AuditAgent Educator Reports (Markdown -> PDF)."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="report .md files or folders; default: all reports under reports/",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="render every report even if its PDF is already up to date",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    _require_deps()

    targets: list[Path] = args.paths or [REPORTS_DIR]
    # An explicit path means "render this now"; the default sweep only
    # (re)renders stale outputs unless --all is given.
    force = bool(args.paths) or args.all

    md_files: list[Path] = []
    for target in targets:
        md_files.extend(_iter_reports(target))

    if not md_files:
        logger.info("no report Markdown found under %s",
                    ", ".join(str(t) for t in targets))
        return 0

    rendered = 0
    for md in md_files:
        if force or _is_stale(md):
            render_one(md)
            rendered += 1
        else:
            logger.info("up to date: %s", md)

    logger.info("done: %d report(s) rendered", rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
