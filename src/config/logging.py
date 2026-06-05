"""The logging skeleton — one place to configure handlers; ``getLogger`` everywhere.

Constitution §3: runtime output goes through the standard library ``logging``
module, never ``print``. Each module gets its own logger with
``logger = logging.getLogger(__name__)`` so log lines are attributable to the
module that emitted them, and the *level* is read from ``config.settings`` (§1.7)
rather than hardcoded — so one setting controls verbosity across the stack.

``configure_logging`` is the single entry point an application boundary (a CLI
``main``, a test session, the API on startup) calls once to install a root
handler. Library/business modules never call it; they only ``getLogger`` and
log, inheriting whatever the boundary configured.
"""

import logging

from config.settings import get_settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Install a root log handler at the configured level (idempotent).

    ``level`` overrides for a one-off (e.g. a verbose CLI run); when omitted the
    level comes from ``Settings.log_level`` so configuration stays in one place.
    ``logging.basicConfig`` is a no-op once handlers exist, so calling this more
    than once is safe.
    """
    resolved = (level or get_settings().log_level).upper()
    logging.basicConfig(level=resolved, format=_LOG_FORMAT)
