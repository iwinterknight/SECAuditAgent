"""The XBRL path — the sole place an ``XBRLFact`` is constructed (§1.2 firewall).

Every financial number the system can answer with originates here, read out of a
filing's inline-XBRL package with Arelle. Nothing in this module guesses a figure
from prose: it reads the machine-readable facts the filer tagged, with their own
declared period, unit, sign and scale. That is what makes the "numbers only from
XBRL" firewall (Constitution §1.2) a structural fact rather than a hope — the PDF
path (``ingestion.elements``) never imports or builds an ``XBRLFact``, and this
module never reads the PDF.

Three Arelle conventions are worth knowing to read the code below:

- **Transform is already applied.** Arelle resolves each iXBRL fact's
  ``scale``/``sign``/``format`` and exposes the final number as ``fact.value`` (a
  string). ``us-gaap:InvestmentBankingRevenue`` tagged ``scale="6"`` comes back as
  ``"8910000000"``, not ``"8910"``. So we parse ``Decimal(fact.value)`` directly
  and never re-apply scale — doing so would double-count it.
- **Period dates are stored end-exclusive.** A ``2024-12-31`` instant is stored as
  midnight on ``2025-01-01``; an FY2024 duration as ``2024-01-01 .. 2025-01-01``.
  We subtract a day from the instant and the end date to recover the *reported*
  dates (the start date is inclusive and kept as-is).
- **Entity lives on a dimension, not the context entity id.** Both JPMorgan Chase
  & Co. (consolidated) and JPMorgan Chase Bank, N.A. file under the same CIK; the
  subsidiary's figures are distinguished by an explicit ``dei:LegalEntityAxis``
  member, which we project onto :class:`~config.schema.Entity` (§1.3).
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from arelle import Cntlr

from config.schema import Entity, PeriodType, XBRLFact

logger = logging.getLogger(__name__)

# The consolidation axis whose member separates the bank subsidiary from the
# consolidated registrant. Matched by local name (namespace-prefix agnostic).
_LEGAL_ENTITY_AXIS = "LegalEntityAxis"
# An explicit member of that axis whose local name starts with this (case-folded)
# scopes a fact to the bank subsidiary; anything else stays consolidated (§1.3 —
# never inferred from prose, only from this tagged member).
_BANK_NA_MEMBER_PREFIX = "jpmorganchasebankna"


def extract_facts(accession_dir: Path, *, source_filing: str) -> list[XBRLFact]:
    """Read one filing's iXBRL instance into a list of :class:`XBRLFact`.

    ``accession_dir`` is the folder holding the instance (the single ``*.htm``)
    and its linkbases; ``source_filing`` is the accession tag stamped onto every
    fact's provenance. This is the only function in the system that constructs an
    ``XBRLFact`` (§1.2).

    Facts that cannot be represented faithfully are **skipped, never coerced**:
    nil facts (an absent value is not zero), facts whose value will not parse as a
    Decimal, and facts on a "forever" period (no instant/duration to record). Each
    skip is logged so a silently dropped figure is auditable, not invisible.
    """
    instance_path = _find_instance(accession_dir)
    logger.info("loading iXBRL instance %s", instance_path)

    cntlr = Cntlr.Cntlr(logFileName="logToBuffer")
    model = cntlr.modelManager.load(str(instance_path))
    if model is None:
        raise ValueError(f"Arelle could not load an XBRL model from {instance_path}")

    try:
        facts: list[XBRLFact] = []
        skipped = 0
        for model_fact in model.facts:
            # Only numeric facts become XBRLFacts; iXBRL text (ix:nonNumeric) such
            # as the document type or entity name is not a figure.
            if not model_fact.isNumeric:
                continue
            fact = _build_fact(model_fact, source_filing=source_filing)
            if fact is None:
                skipped += 1
                continue
            facts.append(fact)
        deduped = _dedupe_facts(facts)
        logger.info(
            "extracted %d facts from %s (%d numeric skipped, %d duplicate "
            "taggings collapsed)",
            len(deduped),
            source_filing,
            skipped,
            len(facts) - len(deduped),
        )
        return deduped
    finally:
        # Free the parsed model promptly — the pipeline (T10) loads five in a row.
        model.close()


def _find_instance(accession_dir: Path) -> Path:
    """The single iXBRL instance in ``accession_dir`` (its lone ``*.htm``).

    The accession folder holds exactly one inline-XBRL document plus its linkbase
    siblings (``.xsd``/``*_cal|def|lab|pre.xml``). Anything other than exactly one
    ``.htm`` is a corrupt package — fail closed (§1.5) rather than guess.
    """
    instances = sorted(accession_dir.glob("*.htm"))
    if len(instances) != 1:
        raise ValueError(
            f"expected exactly one .htm iXBRL instance in {accession_dir}, "
            f"found {len(instances)}"
        )
    return instances[0]


def _precision(fact: XBRLFact) -> float:
    """A fact's precision as a sortable number — exact (``decimals=None``) is most.

    Higher ``decimals`` means a finer figure (``-6`` = to the million is more
    precise than ``-8`` = to the hundred-million); an absent ``decimals`` means
    the value is exact, so it sorts above every rounded sibling.
    """
    return float("inf") if fact.decimals is None else float(fact.decimals)


def _dedupe_facts(facts: list[XBRLFact]) -> list[XBRLFact]:
    """Collapse duplicate iXBRL taggings to one canonical fact per ``fact_id``.

    A filer routinely tags the same figure in several places — sometimes at
    different rounding precision (the same Long-Term Debt at the million and at
    the hundred-million). Those share a ``fact_id`` (same concept + context +
    unit), so we keep the **most precise** tagging and drop the coarser echoes.

    If two equally precise taggings disagree on the *numeric* value, that is a
    genuine inconsistent duplicate (an SEC-validation error in the source); it is
    logged loudly rather than silently resolved (§1.2), and one is kept so
    extraction still completes.
    """
    groups: dict[str, list[XBRLFact]] = defaultdict(list)
    for fact in facts:
        groups[fact.fact_id].append(fact)

    canonical: list[XBRLFact] = []
    for fact_id, group in groups.items():
        if len(group) == 1:
            canonical.append(group[0])
            continue
        best = max(group, key=_precision)
        top_precision = _precision(best)
        # `Decimal` compares (and hashes) by numeric value, so 9e9 and 9e9.0 are
        # one element here — only a real disagreement makes this set grow.
        rival_values = {f.value for f in group if _precision(f) == top_precision}
        if len(rival_values) > 1:
            logger.warning(
                "inconsistent duplicate %s: equally-precise values %s; keeping %s",
                fact_id,
                sorted(str(v) for v in rival_values),
                best.value,
            )
        canonical.append(best)
    return canonical


def _build_fact(model_fact, *, source_filing: str) -> XBRLFact | None:
    """Resolve one Arelle numeric fact into an ``XBRLFact``, or ``None`` to skip.

    Returns ``None`` (and logs why) for the three un-representable cases so the
    caller can count the skip; never raises on bad fact data.
    """
    concept = str(model_fact.qname)

    if model_fact.isNil:
        # xsi:nil — the filer asserts "no value here", which is not the number 0.
        logger.debug("skipping nil fact %s (context %s)", concept, model_fact.contextID)
        return None

    value = _resolve_value(model_fact, concept=concept)
    if value is None:
        return None

    period = _resolve_period(model_fact.context, concept=concept)
    if period is None:
        return None
    period_type, period_instant, period_start, period_end = period

    entity, dimensions = _resolve_entity_and_dimensions(model_fact.context)
    unit = _resolve_unit(model_fact)

    return XBRLFact(
        fact_id=f"{source_filing}:{concept}:{model_fact.contextID}:{unit}",
        entity=entity,
        concept=concept,
        period_type=period_type,
        period_instant=period_instant,
        period_start=period_start,
        period_end=period_end,
        value=value,
        unit=unit,
        decimals=_resolve_decimals(model_fact),
        dimensions=dimensions,
        source_filing=source_filing,
    )


def _resolve_value(model_fact, *, concept: str) -> Decimal | None:
    """Parse the already-transformed fact value as an exact ``Decimal``.

    Arelle has applied scale and sign, so ``fact.value`` is the final number as a
    string; we never re-scale. A value that will not parse (e.g. an empty string
    on a malformed fact) is skipped, never silently turned into 0 (§1.2).
    """
    try:
        return Decimal(model_fact.value)
    except (InvalidOperation, TypeError, ValueError):
        logger.warning(
            "skipping un-transformable fact %s (context %s): value %r",
            concept,
            model_fact.contextID,
            model_fact.value,
        )
        return None


def _resolve_period(
    context, *, concept: str
) -> tuple[PeriodType, date | None, date | None, date | None] | None:
    """Project an Arelle context's period onto (type, instant, start, end).

    Recovers the *reported* dates from Arelle's end-exclusive storage: an instant
    and a duration's end date are shifted back one day; the start date is already
    inclusive. A forever-period fact has no instant/duration to record and is
    skipped.
    """
    if context.isInstantPeriod:
        instant = (context.instantDatetime - timedelta(days=1)).date()
        return PeriodType.INSTANT, instant, None, None
    if context.isStartEndPeriod:
        start = context.startDatetime.date()
        end = (context.endDatetime - timedelta(days=1)).date()
        return PeriodType.DURATION, None, start, end
    logger.warning(
        "skipping fact %s on unsupported (forever) period, context %s",
        concept,
        context.id,
    )
    return None


def _resolve_entity_and_dimensions(context) -> tuple[Entity, dict[str, str]]:
    """Split a context's axes into the legal entity and the remaining dimensions.

    The ``dei:LegalEntityAxis`` member is projected onto :class:`Entity` (§1.3)
    and *not* echoed into ``dimensions``; every other axis is kept losslessly as
    ``{axis-qname: member-qname}`` so a dimensional fact's full scope survives.
    """
    entity = Entity.JPMC_CONSOLIDATED
    dimensions: dict[str, str] = {}
    for dim_qname, dim_value in context.qnameDims.items():
        if dim_qname.localName == _LEGAL_ENTITY_AXIS:
            if (
                dim_value.isExplicit
                and dim_value.memberQname is not None
                and dim_value.memberQname.localName.lower().startswith(
                    _BANK_NA_MEMBER_PREFIX
                )
            ):
                entity = Entity.JPMORGAN_CHASE_BANK_NA
            continue
        if dim_value.isExplicit:
            dimensions[str(dim_qname)] = str(dim_value.memberQname)
        elif dim_value.typedMember is not None:
            dimensions[str(dim_qname)] = dim_value.typedMember.stringValue
    return entity, dimensions


def _resolve_unit(model_fact) -> str:
    """Build a readable unit string from the fact's measure(s).

    ``([iso4217:USD], [])`` → ``"USD"``; ``([iso4217:USD], [xbrli:shares])`` →
    ``"USD/shares"``; ``([xbrli:pure], [])`` → ``"pure"``. Multiplied measures
    (rare) join with ``*``.
    """
    numerators, denominators = model_fact.unit.measures
    numerator = "*".join(measure.localName for measure in numerators)
    if denominators:
        denominator = "*".join(measure.localName for measure in denominators)
        return f"{numerator}/{denominator}"
    return numerator


def _resolve_decimals(model_fact) -> int | None:
    """The XBRL ``decimals`` precision as an int, or ``None`` for ``INF``/absent.

    ``decimals="-6"`` (rounded to millions) → ``-6``; ``decimals="INF"`` (exact)
    and an absent attribute both → ``None``.
    """
    decimals = model_fact.decimals
    if decimals is None or decimals == "INF":
        return None
    return int(decimals)
