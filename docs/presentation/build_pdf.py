"""Render the presentation Markdown to print-friendly PDFs (markdown -> HTML -> xhtml2pdf).

Pure-Python (no native deps); regenerate anytime with:
    .venv/Scripts/python.exe docs/presentation/build_pdf.py
"""

from __future__ import annotations

from pathlib import Path

import markdown
from xhtml2pdf import pisa

HERE = Path(__file__).resolve().parent

# xhtml2pdf draws with reportlab's Latin-1 base fonts, which lack emojis/arrows/em-dashes;
# normalize them to ASCII so nothing renders as a "tofu" box on the page.
REPLACE = {
    "🗣": "Say:", "💻": "Code:", "⏱": "Min", "✅": "[check]", "🟢": "[ok]", "🔴": "[!]",
    "🟡": "[~]", "📊": "", "🛠": "", "🔁": "", "📈": "", "💬": "", "📚": "", "📑": "",
    "🗂": "", "🎯": "", "▶️": "", "▶": "", "→": "->", "←": "<-", "↺": "", "≤": "<=",
    "≥": ">=", "≈": "~", "×": "x", "—": " - ", "–": "-", "…": "...", "•": "-",
    "’": "'", "‘": "'", "“": '"', "”": '"',
}

CSS = """
@page { size: A4; margin: 1.5cm; }
body { font-family: Helvetica; font-size: 10.5pt; color: #1a1a1a; line-height: 1.4; }
h1 { font-size: 18pt; color: #0b3d6b; margin: 0 0 2pt 0; }
h2 { font-size: 13pt; color: #0b3d6b; margin: 13pt 0 4pt 0; border-bottom: 1px solid #cdd7e0; }
h3 { font-size: 11pt; color: #555555; margin: 7pt 0 3pt 0; }
p { margin: 3pt 0; }
li { margin: 1pt 0; }
code { font-family: Courier; font-size: 9pt; color: #0b3d6b; }
hr { border-top: 1px solid #cdd7e0; }
table { border-collapse: collapse; width: 100%; }
th { background-color: #0b3d6b; color: #ffffff; border: 1px solid #0b3d6b; padding: 4pt; text-align: left; font-size: 9pt; }
td { border: 1px solid #c8d2dc; padding: 3pt 5pt; text-align: left; font-size: 9pt; }
strong { color: #0b3d6b; }
"""

TEMPLATE = "<html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"


def _normalize(text: str) -> str:
    for bad, good in REPLACE.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "ignore").decode("latin-1")


def convert(stem: str) -> None:
    md_text = _normalize((HERE / f"{stem}.md").read_text(encoding="utf-8"))
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    html = TEMPLATE.format(css=CSS, body=body)
    out = HERE / f"{stem}.pdf"
    with out.open("wb") as fh:
        status = pisa.CreatePDF(html, dest=fh, encoding="utf-8")
    print(f"{out.name}: {out.stat().st_size // 1024} KB, errors={status.err}")


if __name__ == "__main__":
    for stem in ("report", "speaker-cues"):
        convert(stem)
