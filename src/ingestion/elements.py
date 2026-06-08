"""The PDF path — the sole place an ``Element`` is constructed (the §1.2 mirror).

Every *narrative* unit the system can retrieve over originates here: the prose,
headings and tables of a 10-K, read out of the filing PDF with Docling. This is
the structural twin of ``ingestion.xbrl``. There the rule is "numbers come only
from XBRL"; here the rule is its mirror — this module never imports or constructs
an :class:`~config.schema.XBRLFact`, and the XBRL path never reads the PDF. A
*number* a table happens to contain is text-for-retrieval, never a figure to
answer with (Constitution §1.2); the figures live in the fact stream.

Three Docling conventions are worth knowing to read the code below:

- **A layout model segments the page, TableFormer recovers cells.** Docling does
  not read the PDF's text stream linearly; a layout model labels each region of
  each rendered page (title, section header, paragraph, list item, table, picture,
  page header/footer…) and emits them in *reading order*, and a separate table
  model reconstructs the row/column grid. ``document.iterate_items()`` walks that
  structure for us — we classify each node and stamp provenance, we do not
  re-derive layout.
- **Body vs furniture.** ``iterate_items()`` yields only the ``BODY`` content
  layer by default, so running headers/footers (the "JPMorgan Chase & Co. / 2024
  Form 10-K" banner repeated on every page) are *furniture* and never reach us.
  We still drop the furniture labels defensively, so a banner that leaks into the
  body never becomes hundreds of near-duplicate Elements that would pollute
  retrieval.
- **Models download once, then run warm.** The first ``convert`` call fetches the
  layout and TableFormer weights from HuggingFace into Docling's cache (one-time,
  network-dependent — hundreds of MB) and loads them into memory; every parse
  after that is offline-warm. Caching the converter (:func:`_get_converter`) pays
  that cost once per process, and that warm cache is what M1's offline-rebuild
  guarantee (T10) will rely on.

What this module deliberately does *not* decide:

- **Entity.** Every Element defaults to the consolidated registrant
  (``Entity.JPMC_CONSOLIDATED``). The bank subsidiary is never inferred from prose
  (§1.3) — only the XBRL path, reading a tagged ``dei:LegalEntityAxis`` member,
  may scope a figure to the subsidiary.
- **10-K Item.** The ``item`` field is left ``"unknown"`` here. Mapping each
  Element to its Item (Item 1, 1A, 7, 7A, 8…) is a sequential-scan concern owned
  by T7; the parser does not guess a section boundary.
"""

import gc
import logging
from functools import lru_cache
from pathlib import Path

import pypdfium2 as pdfium
from docling.datamodel.base_models import InputFormat
from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_V2
from docling.datamodel.pipeline_options import (
    LayoutOptions,
    PdfPipelineOptions,
    TableFormerMode,
)
from docling.datamodel.settings import settings as docling_settings
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.document import (
    DoclingDocument,
    NodeItem,
    TableItem,
    TextItem,
)
from docling_core.types.doc.labels import DocItemLabel

from config.schema import Element, ElementKind, Entity

logger = logging.getLogger(__name__)

# Headings: a document title or a section header become ``ElementKind.HEADING``.
# (Both ``TitleItem`` and ``SectionHeaderItem`` are ``TextItem`` subclasses, so
# the isinstance check in :func:`_classify` catches them; the label tells them
# apart from prose.)
_HEADING_LABELS: frozenset[DocItemLabel] = frozenset(
    {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}
)
# Page furniture: running headers and footers carry no document content. Normally
# excluded by the BODY-only default of ``iterate_items()``; dropped here too so a
# leak can't flood the Element stream with per-page duplicates.
_FURNITURE_LABELS: frozenset[DocItemLabel] = frozenset(
    {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
)

# Parse the PDF in fixed-size page windows rather than all at once. Docling holds
# per-page backend state for every page within a single ``convert`` call, so a
# 300+ page 10-K accumulates memory until the host OOMs (a native
# ``std::bad_alloc``, then a segfault) mid-document. Converting a bounded window at
# a time — and releasing it before the next — caps peak memory at one window's
# working set, independent of how long the filing is. 16 pages sits well inside the
# proven-safe range on a few-GB-free host while keeping the window count (and
# per-window overhead) modest.
_PAGE_WINDOW = 16


@lru_cache(maxsize=1)
def _get_converter() -> DocumentConverter:
    """Build the Docling converter once and reuse it across filings.

    The first ``convert`` downloads the layout and TableFormer model weights into
    Docling's cache (one-time, network-dependent — hundreds of MB) and loads them
    into memory; caching the converter means that cost is paid a single time per
    process. This is also the warm model cache the offline-rebuild guarantee at
    M1's validator stage (T10) will depend on.

    OCR is **off**: JPMorgan's 10-Ks are digital-native text PDFs, so OCR would
    only add minutes and risk transcription noise. Table-structure recovery is
    **on** — tables are where 10-K parsing earns its keep (architecture §10) — but
    via TableFormer's lighter **FAST** model rather than ACCURATE.

    **Memory budget.** This host parses on CPU with only a few GB free, where
    Docling's defaults OOM mid-document — a native ``std::bad_alloc`` while
    rasterizing pages on top of the large resident models. The number of pages
    that survive tracks free RAM, so the fix is to shrink the footprint. Three
    frugal choices keep peak memory bounded so the parse completes regardless of
    host RAM, at a small, deliberate cost in detection accuracy:

    - the lighter ``docling_layout_v2`` region model instead of the large default
      ``heron`` — the biggest resident-RAM saving;
    - TableFormer **FAST** instead of ACCURATE — a smaller table model that still
      recovers cell structure; and
    - **one page in flight per stage** (``page_batch_size``, ``layout_batch_size``
      and ``table_batch_size`` all = 1), so peak memory is a single page's working
      set, freed between pages.

    The trade is accuracy-for-completion, taken knowingly: a parse that finishes
    on this host beats a more precise one that dies at page 26. (``page_batch_size``
    is a process-wide Docling setting, applied here so the sole parser entry point
    owns it.)
    """
    docling_settings.perf.page_batch_size = 1
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.mode = TableFormerMode.FAST
    pipeline_options.layout_options = LayoutOptions(model_spec=DOCLING_LAYOUT_V2)
    pipeline_options.layout_batch_size = 1
    pipeline_options.table_batch_size = 1
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


def _classify(item: NodeItem) -> ElementKind | None:
    """Map a Docling node to an :class:`ElementKind`, or ``None`` to drop it.

    Tables are matched by *type* (``TableItem``) — they carry a cell grid, not a
    ``.text`` body. Everything else of interest is a ``TextItem`` whose ``label``
    separates a heading from prose. Page furniture is dropped (see
    ``_FURNITURE_LABELS``); so is anything that is neither table nor text
    (pictures, charts, key-value regions, groups), which has no faithful text body
    to normalize at M1.
    """
    if isinstance(item, TableItem):
        return ElementKind.TABLE
    if isinstance(item, TextItem):
        if item.label in _FURNITURE_LABELS:
            return None
        if item.label in _HEADING_LABELS:
            return ElementKind.HEADING
        return ElementKind.TEXT
    return None


def _page_of(item: NodeItem) -> int | None:
    """The 1-based source page of a node, or ``None`` if it carries no provenance.

    An Element with no page cannot satisfy the provenance contract (architecture
    §5), so a node Docling could not localize is dropped rather than stamped with
    a guessed page.
    """
    prov = getattr(item, "prov", None)
    if not prov:
        return None
    return prov[0].page_no


def _table_text(item: TableItem, doc: DoclingDocument) -> str:
    """Serialize a table as HTML — a structure-preserving form M2 can summarize.

    HTML keeps the row/column grid intact (unlike a flattened text dump), which is
    what lets downstream chunking (M2) render or summarize the table without
    re-parsing the PDF. We never read a *number* out of this serialization to
    answer with — figures come only from XBRL (§1.2); a table Element is
    prose-for-retrieval, not a fact source. A table that will not serialize
    returns ``""`` and is dropped by the caller, never emitted half-formed (one
    malformed table must not sink the whole filing).
    """
    try:
        return item.export_to_html(doc=doc)
    except Exception:  # noqa: BLE001 - fail soft per table; caller drops empties
        logger.warning(
            "table export_to_html failed on page %s; dropping the table",
            _page_of(item),
        )
        return ""


def _page_count(pdf_path: Path) -> int:
    """Page count of the PDF, read with pypdfium2 — Docling's own rendering engine,
    already in the locked dependency tree, so no new dependency. It is a cheap
    structural read with no model inference, used only to drive the page windows in
    :func:`parse_elements`.
    """
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def _elements_from_document(
    document: DoclingDocument,
    *,
    fiscal_year: int,
    source_filing: str,
    ordinal_start: int,
) -> tuple[list[Element], int]:
    """Turn one parsed (sub)document into Elements, continuing the filing-global
    reading-order ``ordinal`` from ``ordinal_start``.

    Returns the Elements plus the number of nodes skipped (furniture, no-page,
    empty-text). Factoring this out of :func:`parse_elements` lets the same
    per-node logic serve every page window under one shared ordinal sequence, so
    ``ordinal`` (and the ``element_id`` built from it) stays dense and unique
    across window boundaries.
    """
    elements: list[Element] = []
    skipped = 0
    ordinal = ordinal_start
    for item, _level in document.iterate_items():
        kind = _classify(item)
        if kind is None:
            skipped += 1
            continue
        page = _page_of(item)
        if page is None:
            skipped += 1
            continue
        text = (
            _table_text(item, document)
            if kind is ElementKind.TABLE
            else (getattr(item, "text", "") or "")
        )
        if not text.strip():
            skipped += 1
            continue
        elements.append(
            Element(
                element_id=f"{source_filing}:{page}:{ordinal}",
                kind=kind,
                text=text,
                fiscal_year=fiscal_year,
                item="unknown",
                page=page,
                entity=Entity.JPMC_CONSOLIDATED,
                source_filing=source_filing,
                ordinal=ordinal,
            )
        )
        ordinal += 1
    return elements, skipped


def parse_elements(
    pdf_path: Path, *, fiscal_year: int, source_filing: str
) -> list[Element]:
    """Parse one 10-K PDF into a reading-order list of :class:`Element`.

    This is the **sole** producer of ``Element`` in the system — the PDF-side
    mirror of the §1.2 firewall: chunking (M2) consumes Elements and never
    re-reads the PDF. ``fiscal_year`` and ``source_filing`` are the provenance
    stamped onto every Element; ``page`` (absolute, 1-based) and the filing-global
    reading-order ``ordinal`` come from Docling.

    The PDF is parsed in fixed **page windows** (``_PAGE_WINDOW``): a 300+ page
    10-K converted in one shot accumulates per-page backend state until the host
    OOMs mid-document, so each window is converted and released before the next,
    capping peak memory at one window's working set. ``page_range`` reports
    *absolute* page numbers, so the output is identical to a single-shot parse —
    the windowing is an invisible memory optimization, not a change to provenance
    or ordering.

    Every emitted Element carries full provenance — ``fiscal_year``, ``page``,
    ``kind``, ``item`` (left ``"unknown"`` until T7 finds Item boundaries) and
    ``entity`` (always consolidated at M1; §1.3 forbids inferring a subsidiary
    from prose). Nodes that cannot be represented faithfully are **skipped, never
    coerced**: page furniture, pictures/charts, nodes with no page provenance, and
    empty-text nodes. A PDF that yields *zero* Elements raises ``ValueError``
    rather than returning an empty list — a silent empty parse is a fidelity
    failure, not a valid result.
    """
    if not pdf_path.is_file():
        raise ValueError(f"PDF not found: {pdf_path}")

    converter = _get_converter()
    page_count = _page_count(pdf_path)

    elements: list[Element] = []
    skipped = 0
    for start in range(1, page_count + 1, _PAGE_WINDOW):
        end = min(start + _PAGE_WINDOW - 1, page_count)
        document = converter.convert(pdf_path, page_range=(start, end)).document
        window_elements, window_skipped = _elements_from_document(
            document,
            fiscal_year=fiscal_year,
            source_filing=source_filing,
            ordinal_start=len(elements),
        )
        elements.extend(window_elements)
        skipped += window_skipped
        # Release this window's parsed document (and its native backend state)
        # before converting the next, so peak memory stays at one window's worth.
        del document
        gc.collect()
        logger.debug(
            "parsed pages %d-%d: +%d Elements (running total %d)",
            start,
            end,
            len(window_elements),
            len(elements),
        )

    if not elements:
        raise ValueError(
            f"parsed zero Elements from {pdf_path} — expected a populated 10-K; "
            "an empty parse is treated as a fidelity failure, not a valid result"
        )

    logger.info(
        "parsed %d Elements (skipped %d nodes) from %s (FY%d) over %d-page windows",
        len(elements),
        skipped,
        source_filing,
        fiscal_year,
        _PAGE_WINDOW,
    )
    return elements
