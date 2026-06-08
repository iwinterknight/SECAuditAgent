"""The Item-boundary pass — stamp each Element with the 10-K Item it falls under.

A 10-K is organized into numbered **Items** grouped under four **Parts**:

- Part I — Item 1 Business, 1A Risk Factors, 1B/1C, 2 Properties, 3 Legal
  Proceedings, 4 Mine Safety;
- Part II — Item 5 Market for Stock, 6 (reserved), **7 MD&A**, 7A Quantitative &
  Qualitative Market-Risk Disclosures, **8 Financial Statements**, 9/9A/9B/9C;
- Part III — Items 10-14; Part IV — Item 15 Exhibits, 16.

Knowing an Element's Item is what lets a downstream answer say "per Item 7 (MD&A)"
or scope a retrieval to the financial statements (Item 8). Neither the PDF parser
(``ingestion.elements``) nor the XBRL path recovers Items — it is a separate,
deterministic **post-parse pass** over the already-parsed Element stream, kept
here so the parser stays about *layout* and this stays about *document section*.

The rules (deliberately conservative — architecture §10, plan Risks):

- **Forward-fill from headings only.** We scan **heading** Elements in reading
  order; a recognized "Item N" heading sets the current Item, and every Element
  after it inherits that Item until the next Item heading. We look only at
  headings, never prose — so a passing mention of "Item 7" inside a paragraph, or
  the "Form 10-K Index" *table* of contents, cannot move the boundary (the TOC is
  a ``TABLE``, not a ``HEADING``).
- **Fail to ``unknown``, never to a stale label.** If a heading clearly *is* an
  Item boundary (it begins with the word "Item") but its number will not parse
  (garbled by layout/OCR), we set the Item to ``unknown`` and log — we do **not**
  carry the previous Item forward across a boundary we couldn't read. Silently
  mis-attributing one Item's content to its neighbour is the failure this pass
  exists to prevent.
- **No number handling.** This pass touches section *structure*, never figures;
  it constructs no ``XBRLFact`` and reads no value (the §1.2 firewall is upstream,
  but the discipline holds here too).
"""

import logging
import re

from config.schema import Element, ElementKind

logger = logging.getLogger(__name__)

# The label stamped when no Item is in effect, or when a boundary can't be read.
UNKNOWN_ITEM = "unknown"

# A heading is an *Item-boundary candidate* if it begins with the standalone word
# "Item" (the ``\b`` keeps "Itemized" / "Items" from matching). Candidate
# detection is separate from number parsing on purpose: a candidate we cannot
# parse becomes ``unknown`` (a boundary happened; we refuse to name it) rather
# than silently inheriting the previous Item.
_ITEM_CANDIDATE = re.compile(r"^\s*item\b", re.IGNORECASE)
# A *recognized* Item header: "Item" + a 1-2 digit number with an optional single
# letter suffix (1A, 7A, 9B). The suffix is normalized to upper case in the label.
_ITEM_HEADER = re.compile(r"^\s*item\s+(\d{1,2}[A-Za-z]?)\b", re.IGNORECASE)


def _item_label(heading_text: str) -> str | None:
    """Classify a heading as an Item boundary.

    Returns:
    - ``"Item 7"`` / ``"Item 1A"`` — a recognized Item header (suffix upper-cased);
    - :data:`UNKNOWN_ITEM` — a candidate (starts with "Item") whose number won't
      parse, i.e. a boundary we can see but can't name;
    - ``None`` — not an Item heading at all (an ordinary sub-heading); the caller
      keeps the current Item.
    """
    if _ITEM_CANDIDATE.match(heading_text) is None:
        return None
    match = _ITEM_HEADER.match(heading_text)
    if match is None:
        return UNKNOWN_ITEM
    return f"Item {match.group(1).upper()}"


def assign_items(elements: list[Element]) -> list[Element]:
    """Stamp each Element with the 10-K Item it falls under — a pure forward-fill.

    Pure and deterministic: it does not mutate its input (each Element is returned
    as a copy with ``item`` set) and depends only on the Elements' reading order
    and heading text. Elements before the first recognized Item heading — the
    cover page, the index — are ``unknown``; a garbled Item heading resets the
    current Item to ``unknown`` (and logs) so its section is never mis-attributed
    to the previous Item.
    """
    result: list[Element] = []
    current_item = UNKNOWN_ITEM
    for element in elements:
        if element.kind is ElementKind.HEADING:
            label = _item_label(element.text)
            if label is not None:
                if label == UNKNOWN_ITEM:
                    logger.warning(
                        "unparseable Item heading; section -> unknown: %r (%s)",
                        element.text[:80],
                        element.element_id,
                    )
                current_item = label
        result.append(element.model_copy(update={"item": current_item}))
    return result
