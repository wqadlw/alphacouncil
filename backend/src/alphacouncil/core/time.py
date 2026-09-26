"""Timestamps in the one format the schema accepts.

Every time column in ``storage/migrations/0001_initial.up.sql`` carries

    CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', <column>) = <column>)

which is a round-trip test rather than a shape test: SQLite renders the value
back and the row is rejected unless it comes out identical. That accepts exactly
one spelling of a moment — UTC, ``T`` separator, three fractional digits, ``Z``
— and rejects ``+00:00``, a missing ``Z``, six fractional digits, and every
locally-offset form.

Having one function produce that spelling is the point. The alternative is a
``strftime`` call at each write site, and the first one that forgets the ``Z``
fails at the moment a user is trying to save their reasoning — the worst
possible time to discover a formatting disagreement.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["MILLIS_FORMAT", "utc_millis"]

#: For ``strftime``. Python has no millisecond directive, so ``%f`` (six
#: microseconds) is rendered and the last three digits are dropped.
MILLIS_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def utc_millis(moment: datetime | None = None) -> str:
    """Render ``moment`` in the schema's canonical form.

    Args:
        moment: The instant to render. Defaults to now. A naive datetime is read
            as UTC — the alternative is reading it as local time, which shifts
            the record by the machine's offset and leaves no trace afterwards.

    Returns:
        e.g. ``2026-09-26T19:30:00.123Z``.
    """
    resolved = moment if moment is not None else datetime.now(UTC)
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=UTC)
    return resolved.astimezone(UTC).strftime(MILLIS_FORMAT)[:-3] + "Z"
