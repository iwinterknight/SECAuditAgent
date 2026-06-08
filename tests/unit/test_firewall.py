"""T8 — the §1.2 firewall ("numbers come only from XBRL"), made executable.

The Constitution's load-bearing fidelity rule is that every financial *number* the
system answers with originates in the XBRL path, never in the PDF/narrative path.
The plan makes this true *by construction* and checkable by a structural test
rather than reviewer vigilance: it is about **type ownership, not digit absence**
(plan §"firewall"). An ``Element``'s table ``text`` legitimately contains digits
-- it is the rendered table -- so a digit grep would be both wrong and useless.
What the PDF path must never do is *reference or construct the ``XBRLFact`` type*.

So this test asserts two structural facts with the **AST**, not text matching
(text matching would false-fail on the docstrings of ``elements.py`` /
``sections.py``, which explain the firewall by *naming* ``XBRLFact``; a string in
a docstring is an ``ast.Constant``, never a code reference):

1. **The PDF path references ``XBRLFact`` nowhere.** No ``Name``, attribute, or
   import alias equal to ``XBRLFact`` appears in ``ingestion.elements`` or
   ``ingestion.sections``.
2. **``XBRLFact`` has exactly one definition site** -- ``config.schema``. A single
   ``class XBRLFact`` across the whole source tree is what makes "constructed only
   in the XBRL path" meaningful: a second definition would be a second firewall.

(The XBRL path -- ``ingestion.xbrl`` -- *is* allowed to reference and construct
``XBRLFact``; it is the sole legitimate producer, so it is deliberately not
constrained here.)
"""

import ast
from pathlib import Path

import config.schema

# The PDF/narrative path: the two modules that turn a 10-K PDF into Elements.
# Neither may touch the fact type.
_PDF_PATH_MODULES = ("elements.py", "sections.py")
_FACT_TYPE = "XBRLFact"


def _code_references(source: Path, name: str) -> list[int]:
    """Line numbers where ``name`` is used as a *code* identifier — a bare name, an
    attribute access (``x.name``), or an import alias. Docstrings, comments and
    string literals are ``ast.Constant`` nodes and are intentionally **not**
    matched, so prose that merely mentions the name does not count.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            hits.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == name:
            hits.append(node.lineno)
        elif isinstance(node, ast.alias) and name in (node.name, node.asname):
            hits.append(node.lineno)
    return sorted(hits)


def _classdef_files(root: Path, class_name: str) -> list[Path]:
    """Every ``.py`` file under ``root`` that defines a class named ``class_name``."""
    found: list[Path] = []
    for py in sorted(root.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        if any(
            isinstance(node, ast.ClassDef) and node.name == class_name
            for node in ast.walk(tree)
        ):
            found.append(py.resolve())
    return found


def test_element_path_never_constructs_xbrlfact() -> None:
    """The §1.2 firewall as structure: the PDF path never references the XBRLFact
    type, and XBRLFact is defined in exactly one place (``config.schema``).
    """
    schema_src = Path(config.schema.__file__).resolve()
    src_root = schema_src.parent.parent  # .../src  (config/ and ingestion/ live here)
    ingestion_dir = src_root / "ingestion"

    # (1) The PDF path references the XBRLFact *type* nowhere (AST, not text:
    #     docstrings naming "XBRLFact" and Element digits do not count).
    for module in _PDF_PATH_MODULES:
        source = ingestion_dir / module
        assert source.is_file(), f"expected the PDF-path module {source} to exist"
        hits = _code_references(source, _FACT_TYPE)
        assert hits == [], (
            f"{module} references {_FACT_TYPE} at line(s) {hits}; the PDF path must "
            f"never touch the fact type (Constitution §1.2)"
        )

    # (2) XBRLFact has exactly one definition site, and it is config/schema.py.
    definers = _classdef_files(src_root, _FACT_TYPE)
    assert definers == [schema_src], (
        f"{_FACT_TYPE} is defined in {[str(p) for p in definers]}; "
        f"expected exactly one site: {schema_src}"
    )
