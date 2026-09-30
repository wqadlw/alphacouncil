"""What we have told the reader, and the identity of a thing (spec 044).

## ⭐ This is not a cache, and the difference is the whole table

ADR-0031 forbade one specific thing:

> 缓存 | ⭐ **不要 —— 有害** | 要

because a cache in this path means **a notification that gets deduplicated away is a
silently dropped reminder**. ⭐ This table deduplicates too — ⭐ and the distinction that
keeps it legal is entirely in :func:`fingerprint`:

| | data cache | this |
|---|---|---|
| asks | 「这个值我们取过没有」 | 「关于**这一件事**,我说过没有」 |
| key | the datum | the **fact**, not its conclusion |
| if wrong | the reader never hears | the reader never hears |

⭐ Both failure modes are the same sentence. ⭐ That is why the column is called what it is
and why nothing here takes a TTL: ⭐ a cache that expires is a reminder that stops, and
「你说过没有」 does not expire — ⭐ the reader cannot un-hear something.

## ⭐ The fingerprint excludes the conclusion, and that is a decision

:func:`fingerprint` covers ``(kind, decision_id, metric, operator, threshold, as_of)`` and
**not** the verdict. So a criterion that crossed and then stopped crossing is still one
fact, and the reader hears about it **once**.

⭐ The alternative — keying on the verdict too — would notify on every flip, ⭐ which is
「异动提醒」 (红线 8) and nagging (红线 11), ⭐ and the cost of it is paid by the reader.

The same reasoning decides that the three 「we don't know」 states **produce no row at
all** — see :func:`alphacouncil.notify.dispatch`.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from alphacouncil.core.time import utc_millis

__all__ = ["SentNotification", "already_sent", "fingerprint", "history", "record"]

_INSERT = """
INSERT INTO notifications_sent (channel, fingerprint, kind, subject, body, sent_at)
VALUES (?, ?, ?, ?, ?, ?)
"""

_SELECT_ONE = "SELECT subject FROM notifications_sent WHERE channel = ? AND fingerprint = ?"

_SELECT_HISTORY = (
    "SELECT channel, kind, subject, body, sent_at FROM notifications_sent "
    "ORDER BY sent_at DESC"
)


@dataclass(frozen=True, slots=True)
class SentNotification:
    """One thing we said, verbatim."""

    channel: str
    kind: str
    subject: str
    body: str
    sent_at: str


def fingerprint(
    *, kind: str, decision_id: str, metric: str, operator: str, threshold: float, as_of: str
) -> str:
    """A stable identity for **one criterion**, and nothing about its current state.

    ⭐ SHA-256 over a NUL-joined tuple. ⭐ The raw fields are deliberately **not** stored:
    「同一件事」 is a definition that may be revised, ⭐ and a history row that becomes
    unreadable when the definition moves is worse than one that cannot be reverse-read.

    ⭐ NUL as the separator is not decoration: ⭐ a criterion whose metric is ``"a b"``
    and one whose metric is ``"a"`` with operator ``"b"`` must not collide, ⭐ and joining
    with a space would let them.
    """
    parts = (kind, decision_id, metric, operator, repr(float(threshold)), as_of)
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def already_sent(connection: sqlite3.Connection, *, channel: str, key: str) -> bool:
    """Whether we have told the reader about this exact thing, on this channel."""
    row = connection.execute(_SELECT_ONE, (channel, key)).fetchone()
    return row is not None


def record(
    connection: sqlite3.Connection,
    *,
    channel: str,
    key: str,
    kind: str,
    subject: str,
    body: str,
    sent_at: str | None = None,
) -> None:
    """Record one delivered notification.

    ⭐ **Call this only after the channel reported success.** A failed delivery is a
    transport fact, ⭐ and recording it would mean a retry never happens — ⭐ plus every
    failure would leave a row nothing is allowed to clean up, because the table is
    append-only and says so with triggers.

    ⭐ The cost, stated plainly: this table cannot answer 「上次那条投递成功了吗」. ⭐ It
    answers the question the product actually asks, which is 「关于这件事我说过没有」.
    """
    connection.execute(
        _INSERT,
        (
            channel,
            key,
            kind,
            subject,
            body,
            sent_at or utc_millis(),
        ),
    )


def history(connection: sqlite3.Connection, *, limit: int = 50) -> list[SentNotification]:
    """What we said, newest first. ⭐ For a human, never on the send path."""
    rows = connection.execute(_SELECT_HISTORY).fetchall()[: max(0, limit)]
    return [
        SentNotification(
            channel=str(row[0]),
            kind=str(row[1]),
            subject=str(row[2]),
            body=str(row[3]),
            sent_at=str(row[4]),
        )
        for row in rows
    ]
