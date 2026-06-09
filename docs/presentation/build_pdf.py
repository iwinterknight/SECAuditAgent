"""Render the presentation Markdown to print-friendly PDFs (markdown -> HTML -> xhtml2pdf).

  report.md       -> report.pdf        (landscape slide deck: one slide per page)
  speaker-cues.md -> speaker-cues.pdf  (portrait reference card)

Pure-Python (needs: markdown, xhtml2pdf). Regenerate anytime:
    .venv/Scripts/python.exe docs/presentation/build_pdf.py
"""

from __future__ import annotations

from pathlib import Path

import markdown
from xhtml2pdf import pisa

HERE = Path(__file__).resolve().parent

# xhtml2pdf draws with reportlab's Latin-1 base fonts (no emoji/arrow/em-dash glyphs);
# normalize to ASCII so nothing renders as a "tofu" box. Diagrams use plain ASCII.
REPLACE = {
    "🗣": "Say:", "💻": "Code:", "⏱": "Min", "✅": "[check]", "🟢": "[ok]", "🔴": "[!]",
    "🟡": "[~]", "📊": "", "🛠": "", "🔁": "", "📈": "", "💬": "", "📚": "", "📑": "",
    "🗂": "", "🎯": "", "▶️": "", "▶": "", "→": "->", "←": "<-", "↺": "", "∈": " in ",
    "≤": "<=", "≥": ">=", "≈": "~", "×": "x", "—": " - ", "–": "-", "…": "...", "•": "-",
    "’": "'", "‘": "'", "“": '"', "”": '"',
}

# A landscape, one-slide-per-page deck: each H2 starts a new page; diagrams are framed.
REPORT_CSS = """
@page { size: A4 landscape; margin: 1.2cm 1.7cm; }
body { font-family: Helvetica; font-size: 13pt; color: #1b1b1b; line-height: 1.45; }
h1 { font-size: 27pt; color: #0b3d6b; margin: 80pt 0 10pt 0; }
h3 { font-size: 13pt; color: #5a6b7b; font-weight: normal; margin: 3pt 0; }
h2 { font-size: 21pt; color: #0b3d6b; page-break-before: always; margin: 0 0 12pt 0;
     border-bottom: 2pt solid #0b3d6b; padding-bottom: 4pt; }
ul { margin: 12pt 0 0 0; }
li { margin: 6pt 0; font-size: 13.5pt; }
pre { background-color: #eef3f8; border: 1pt solid #c2d0de; padding: 8pt 10pt;
      font-family: Courier; font-size: 10pt; color: #103a5e; }
code { font-family: Courier; color: #0b3d6b; }
table { border-collapse: collapse; width: 100%; margin: 10pt 0; }
th { background-color: #0b3d6b; color: #ffffff; border: 1pt solid #0b3d6b; padding: 5pt; font-size: 12pt; text-align: left; }
td { border: 1pt solid #c8d2dc; padding: 4pt 5pt; font-size: 12pt; }
strong { color: #0b3d6b; }
hr { border: 0; }
"""

# A compact portrait reference card.
CUE_CSS = """
@page { size: A4; margin: 1.5cm; }
body { font-family: Helvetica; font-size: 10.5pt; color: #1a1a1a; line-height: 1.4; }
h1 { font-size: 18pt; color: #0b3d6b; margin: 0 0 2pt 0; }
h2 { font-size: 13pt; color: #0b3d6b; margin: 13pt 0 4pt 0; border-bottom: 1px solid #cdd7e0; }
p { margin: 3pt 0; }
li { margin: 1pt 0; }
code { font-family: Courier; font-size: 9pt; color: #0b3d6b; }
hr { border-top: 1px solid #cdd7e0; }
table { border-collapse: collapse; width: 100%; }
th { background-color: #0b3d6b; color: #ffffff; border: 1px solid #0b3d6b; padding: 4pt; text-align: left; font-size: 9pt; }
td { border: 1px solid #c8d2dc; padding: 3pt 5pt; text-align: left; font-size: 9pt; }
strong { color: #0b3d6b; }
"""

CONFIGS = {"report": REPORT_CSS, "speaker-cues": CUE_CSS}
TEMPLATE = "<html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"


def _normalize(text: str) -> str:
    for bad, good in REPLACE.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "ignore").decode("latin-1")


def convert(stem: str) -> None:
    md_text = _normalize((HERE / f"{stem}.md").read_text(encoding="utf-8"))
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    html = TEMPLATE.format(css=CONFIGS[stem], body=body)
    out = HERE / f"{stem}.pdf"
    with out.open("wb") as fh:
        status = pisa.CreatePDF(html, dest=fh, encoding="utf-8")
    print(f"{out.name}: {out.stat().st_size // 1024} KB, errors={status.err}")


if __name__ == "__main__":
    for stem in CONFIGS:
        convert(stem)
