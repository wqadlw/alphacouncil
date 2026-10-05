"""Repository for knowledge cards, their instrument associations and lifecycle events.

K1 (spec 012) owns card creation and the source-check upgrade; K2 (spec 013)
adds the lifecycle layer. Two rules shape the code here:

* **Every state or origin change appends an event.** ``origin`` and ``status``
  are mutable, which collides with the append-only discipline; an
  ``card_events`` row is the durable proof that the change happened, when, and
  why. The ``cards`` UPDATE and the event INSERT run in one transaction.
* **The current state lives on ``cards``; the history lives in
  ``card_events``.** We do not derive the current state from the event stream
  (a deleted or reordered event would silently move it), mirroring the
  decisions/reviews separation in ADR-0014.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.card import (
    CardAlreadyVerifiedError,
    CardConvergeReasonRequiredError,
    CardDraft,
    CardEventType,
    CardNotActiveError,
    CardNotFoundError,
    CardOrigin,
    CardStatus,
    ClaimType,
)
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage.db import require_open_transaction
from alphacouncil.storage.repositories import instruments

__all__ = [
    "CardEventRow",
    "CardRow",
    "converge",
    "create",
    "get_by_id",
    "list_all",
    "list_events",
    "list_for_symbol",
    "query",
    "verify",
]

_INSERT_CARD = (
    "INSERT INTO cards "
    "(id, content, claim_type, source_url, source_title, captured_at, as_of, "
    "origin, priority, status, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_INSERT_CARD_SYMBOL = (
    "INSERT OR IGNORE INTO card_symbols (card_id, market, code, created_at) "
    "VALUES (?, ?, ?, ?)"
)

_INSERT_EVENT = (
    "INSERT INTO card_events (id, card_id, event_type, reason, created_at) "
    "VALUES (?, ?, ?, ?, ?)"
)

_SELECT_BY_ID = (
    "SELECT id, content, claim_type, source_url, source_title, captured_at, "
    "as_of, origin, priority, status, created_at FROM cards WHERE id = ?"
)

_SELECT_SYMBOLS_FOR_CARD = (
    "SELECT market, code FROM card_symbols WHERE card_id = ? "
    "ORDER BY market ASC, code ASC"
)

_SELECT_EVENTS_FOR_CARD = (
    "SELECT id, card_id, event_type, reason, created_at FROM card_events "
    "WHERE card_id = ? ORDER BY created_at ASC"
)

_SELECT_FOR_SYMBOL = (
    "SELECT c.id, c.content, c.claim_type, c.source_url, c.source_title, "
    "c.captured_at, c.as_of, c.origin, c.priority, c.status, c.created_at "
    "FROM cards c "
    "JOIN card_symbols cs ON c.id = cs.card_id "
    "WHERE cs.market = ? AND cs.code = ? "
    "ORDER BY c.created_at DESC"
)

_UPDATE_ORIGIN = "UPDATE cards SET origin = ? WHERE id = ?"
_UPDATE_STATUS = "UPDATE cards SET status = ? WHERE id = ?"


@dataclass(frozen=True, slots=True)
class CardEventRow:
    """One append-only lifecycle event for a card (K2)."""

    id: str
    card_id: str
    event_type: CardEventType
    reason: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class CardRow:
    """One row of ``cards`` with its symbols and lifecycle events."""

    id: str
    content: str
    claim_type: ClaimType
    source_url: str
    source_title: str
    captured_at: str
    origin: CardOrigin
    priority: int
    status: CardStatus
    created_at: str
    as_of: date | None = None
    symbols: tuple[Symbol, ...] = ()
    events: tuple[CardEventRow, ...] = ()


def _stamp_to_dt(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)


def _event_id_for(now_dt: datetime) -> str:
    return f"event_{int(now_dt.timestamp() * 1000)}"


#: How far past the requested millisecond we will look for a free id.
#:
#: 1000 is one second, and the number is `notes.py`'s and `lesson.py`'s — ⭐ the scheme is
#: now three repositories old and a fourth copy of the constant is a fourth place for the
#: limit to drift. Beyond a second two writes are not "the same moment" any more, and
#: minting a card whose id lies about when it was written would break the
#: `GLOB('card_[0-9]*', id)` → timestamp reading the whole scheme rests on.
_ID_COLLISION_LIMIT = 1_000


def _generate_card_id(
    connection: sqlite3.Connection,
    now_dt: datetime | None = None,
) -> str:
    """A card id that is not already taken.

    ⭐ **This walks forward. It used to be the bare `f"card_{millis}"`, and that was a
    deferral whose reason has since expired** (spec 057).

    The deferral is on record — `.ai/logs/changes/2026-09-27-k1-cards.md`, 边界记录: two
    cards in the same millisecond collide on UNIQUE; a manual UI action cannot trigger it
    but a scripted call can; not fixed, because it was consistent with the existing
    repositories; recorded here pending a product decision between a sequence suffix and
    accepting a 500.

    ⭐ **Paraphrased rather than quoted, and that is a judgement rather than an accident.**
    The project's stated rule for the `RUF001`/`RUF002` exemptions is 「rewriting a
    quotation to satisfy a linter is worse than the warning」 — ⭐ which holds for text that
    *is* the constraint. ⭐ This docstring only *refers* to the changelog, so paraphrasing
    loses no constraint and saves `cards.py` an exemption. ⭐ Five sibling files already hold
    one; a sixth for a docstring that could have been English would make the list stop
    meaning anything.

    ⭐⭐ **That stated reason was "keep semantics consistent with the existing repositories",
    and it is why this was fixed now rather than then: at the time of writing, `cards`
    was the *only* repository with a bare millis id, so consistency argued for leaving it
    alone. Since then three of them changed convention — `notes.py::_mint_note_id`,
    `note_recall.py::_new_id` and `lesson.py` all walk forward. ⭐ Consistency now argues
    the other way, so the deferral's premise is gone rather than merely inconvenient.

    ⭐ **The alternative the note offered — 「接受 500」 — is the reason this had to be
    decided at all.** A 500 on `POST /api/v1/cards` means the reader's claim is *lost*, with
    no envelope explaining why and nothing to retry. `notes.py` states the general rule:
    「the alternative to raising is worse — a note that silently overwrote another is the
    exact failure the whole append-only discipline exists to prevent」. ⭐ The same holds
    for a card: a card is 「有来源的主张」 and the product's whole claim is that a claim
    once recorded stays recorded.

    ⭐ **Reachability was measured, not assumed** (spec 057 §六 warns 「播种『成功』但库是空
    的」, and the mirror of that warning is 「播种失败了却没人发现」): the K1 note says a
    manual UI action cannot trigger this, and that is correct — ⭐ but `dev.py demo`'s
    seeder hit it **on its first run**, which is the 「脚本化调用」 the note predicted, four
    repositories later. `cards.id` needed no migration: `card_[0-9]*` still accepts a
    walked-forward id, verified against the schema's own GLOB.

    ⚠️ **`card_reviews` is a different row and is still bare** — `scheduling.py::_new_id`
    takes no connection, so it *cannot* check. `note_recall.py` already names it as
    inherited-and-unfixed, and it stays that way: fixing it needs the signature changed, and
    that is its own decision.

    ⚠️ **The exhaustion case raises a bare `RuntimeError`, and that is a decision rather
    than an omission** — this repository now has three answers to 「同一个问题」 and they
    disagree. `notes.py` raises `NoteIdExhaustedError` but stamps it
    `ErrorCode.NOTE_NOT_FOUND`, ⭐ which is *wrong*: the note exists, the id space is full.
    `note_recall.py` raises a domain error; `lesson.py`, the newest of the three, raises
    `RuntimeError`. ⭐ This copies `lesson.py` because it is both the latest decision and
    the only one that does not publish a misleading code — ⭐ and because the condition
    needs a thousand cards in one millisecond, so a registry entry would exist for no reader
    to ever see. ⭐ Written down here so the next reader does not take it for a missing
    registration.
    """
    millis = int(now_dt.timestamp() * 1000) if now_dt is not None else int(time.time() * 1000)
    for offset in range(_ID_COLLISION_LIMIT):
        candidate = f"card_{millis + offset}"
        taken = connection.execute(
            "SELECT 1 FROM cards WHERE id = ?", (candidate,)
        ).fetchone()
        if taken is None:
            return candidate
    raise RuntimeError(
        "无法为这张卡片生成唯一 id：同一毫秒内已有多达 "
        f"{_ID_COLLISION_LIMIT} 张卡片。"
    )


def create(
    connection: sqlite3.Connection,
    draft: CardDraft,
    *,
    now: str | None = None,
) -> CardRow:
    stamp = now if now is not None else utc_millis()
    now_dt = _stamp_to_dt(stamp)
    card_id = _generate_card_id(connection, now_dt)

    for sym in draft.symbols:
        instruments.ensure(connection, sym, now=stamp)

    as_of_str = draft.as_of.isoformat() if draft.as_of is not None else None

    connection.execute(
        _INSERT_CARD,
        (
            card_id,
            draft.content,
            draft.claim_type.value,
            draft.source_url,
            draft.source_title,
            stamp,
            as_of_str,
            draft.origin.value,
            draft.priority,
            draft.status.value,
            stamp,
        ),
    )

    for sym in draft.symbols:
        connection.execute(
            _INSERT_CARD_SYMBOL,
            (card_id, sym.market.value, sym.code, stamp),
        )

    return CardRow(
        id=card_id,
        content=draft.content,
        claim_type=draft.claim_type,
        source_url=draft.source_url,
        source_title=draft.source_title,
        captured_at=stamp,
        as_of=draft.as_of,
        origin=draft.origin,
        priority=draft.priority,
        status=draft.status,
        created_at=stamp,
        symbols=draft.symbols,
    )


def get_by_id(connection: sqlite3.Connection, card_id: str) -> CardRow | None:
    row = connection.execute(_SELECT_BY_ID, (card_id,)).fetchone()
    if row is None:
        return None
    return _to_card_row(
        row,
        _load_symbols(connection, card_id),
        _load_events(connection, card_id),
    )


def list_for_symbol(connection: sqlite3.Connection, symbol: Symbol) -> tuple[CardRow, ...]:
    rows = connection.execute(_SELECT_FOR_SYMBOL, (symbol.market.value, symbol.code)).fetchall()
    return tuple(
        _to_card_row(
            r,
            _load_symbols(connection, r["id"]),
            _load_events(connection, r["id"]),
        )
        for r in rows
    )


#: The only column names ``query`` may filter on. Kept as a closed table so the
#: ``WHERE`` clause below is assembled from literals, never from caller input.
_FILTER_CLAUSES: dict[str, str] = {
    "claim_type": "claim_type = ?",
    "origin": "origin = ?",
    "status": "status = ?",
}


def query(
    connection: sqlite3.Connection,
    *,
    claim_type: ClaimType | None = None,
    origin: CardOrigin | None = None,
    status: CardStatus | None = None,
    limit: int = 50,
) -> tuple[CardRow, ...]:
    clauses: list[str] = []
    params: list[object] = []

    for key, value in (
        ("claim_type", claim_type),
        ("origin", origin),
        ("status", status),
    ):
        if value is not None:
            clauses.append(_FILTER_CLAUSES[key])
            params.append(value.value)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    # ``clauses`` is assembled only from the _FILTER_CLAUSES literals above;
    # no part of it ever comes from caller input, and every bound value is
    # passed as a separate parameter.
    sql = (
        "SELECT id, content, claim_type, source_url, source_title, captured_at, "  # noqa: S608 -- see the note above
        f"as_of, origin, priority, status, created_at FROM cards {where} "
        "ORDER BY created_at DESC LIMIT ?"
    )
    params.append(limit)

    rows = connection.execute(sql, tuple(params)).fetchall()
    return tuple(
        _to_card_row(
            r,
            _load_symbols(connection, r["id"]),
            _load_events(connection, r["id"]),
        )
        for r in rows
    )


def list_all(connection: sqlite3.Connection) -> tuple[CardRow, ...]:
    sql = (
        "SELECT id, content, claim_type, source_url, source_title, captured_at, "
        "as_of, origin, priority, status, created_at FROM cards "
        "ORDER BY created_at ASC"
    )
    rows = connection.execute(sql).fetchall()
    return tuple(
        _to_card_row(
            r,
            _load_symbols(connection, r["id"]),
            _load_events(connection, r["id"]),
        )
        for r in rows
    )


def list_events(connection: sqlite3.Connection, card_id: str) -> tuple[CardEventRow, ...]:
    """Return the append-only lifecycle events of one card, oldest first."""
    rows = connection.execute(_SELECT_EVENTS_FOR_CARD, (card_id,)).fetchall()
    return tuple(_to_event_row(r) for r in rows)


def verify(
    connection: sqlite3.Connection,
    card_id: str,
    *,
    now: str | None = None,
) -> CardRow:
    """Upgrade an ai_generated card to user_written and record the event (K2)."""
    stamp = now if now is not None else utc_millis()
    existing = get_by_id(connection, card_id)
    if existing is None:
        raise CardNotFoundError(f"card {card_id!r} not found")
    if existing.origin is not CardOrigin.AI_GENERATED:
        raise CardAlreadyVerifiedError(
            f"card {card_id!r} origin is already {existing.origin.value}"
        )

    event = CardEventRow(
        id=_event_id_for(_stamp_to_dt(stamp)),
        card_id=card_id,
        event_type=CardEventType.VERIFIED,
        reason=None,
        created_at=stamp,
    )
    require_open_transaction(connection, operation="cards.verify")
    connection.execute(_UPDATE_ORIGIN, (CardOrigin.USER_WRITTEN.value, card_id))
    connection.execute(
        _INSERT_EVENT,
        (event.id, event.card_id, event.event_type.value, event.reason, event.created_at),
    )
    return replace(existing, origin=CardOrigin.USER_WRITTEN, events=(*existing.events, event))


def converge(
    connection: sqlite3.Connection,
    card_id: str,
    reason: str,
    *,
    now: str | None = None,
) -> CardRow:
    """Retire an active card to converged with a user-written reason (K2).

    Only an active card may converge, and the reason is mandatory: the exit
    from the current body of claims must itself say why the claim no longer
    stands. The status UPDATE and the event INSERT are one transaction.
    """
    stamp = now if now is not None else utc_millis()
    existing = get_by_id(connection, card_id)
    if existing is None:
        raise CardNotFoundError(f"card {card_id!r} not found")
    if existing.status is not CardStatus.ACTIVE:
        raise CardNotActiveError(
            f"card {card_id!r} status is already {existing.status.value}"
        )
    cleaned = reason.strip()
    if not cleaned:
        raise CardConvergeReasonRequiredError("converging a card requires a reason")

    event = CardEventRow(
        id=_event_id_for(_stamp_to_dt(stamp)),
        card_id=card_id,
        event_type=CardEventType.CONVERGED,
        reason=cleaned,
        created_at=stamp,
    )
    require_open_transaction(connection, operation="cards.converge")
    connection.execute(_UPDATE_STATUS, (CardStatus.CONVERGED.value, card_id))
    connection.execute(
        _INSERT_EVENT,
        (event.id, event.card_id, event.event_type.value, event.reason, event.created_at),
    )
    return replace(existing, status=CardStatus.CONVERGED, events=(*existing.events, event))


def _load_symbols(connection: sqlite3.Connection, card_id: str) -> tuple[Symbol, ...]:
    rows = connection.execute(_SELECT_SYMBOLS_FOR_CARD, (card_id,)).fetchall()
    return tuple(Symbol(market=Market(r["market"]), code=r["code"]) for r in rows)


def _load_events(connection: sqlite3.Connection, card_id: str) -> tuple[CardEventRow, ...]:
    rows = connection.execute(_SELECT_EVENTS_FOR_CARD, (card_id,)).fetchall()
    return tuple(_to_event_row(r) for r in rows)


def _to_event_row(row: sqlite3.Row) -> CardEventRow:
    return CardEventRow(
        id=row["id"],
        card_id=row["card_id"],
        event_type=CardEventType(row["event_type"]),
        reason=row["reason"],
        created_at=row["created_at"],
    )


def _to_card_row(
    row: sqlite3.Row,
    symbols: tuple[Symbol, ...],
    events: tuple[CardEventRow, ...],
) -> CardRow:
    as_of_val = date.fromisoformat(row["as_of"]) if row["as_of"] is not None else None
    return CardRow(
        id=row["id"],
        content=row["content"],
        claim_type=ClaimType(row["claim_type"]),
        source_url=row["source_url"],
        source_title=row["source_title"],
        captured_at=row["captured_at"],
        as_of=as_of_val,
        origin=CardOrigin(row["origin"]),
        priority=int(row["priority"]),
        status=CardStatus(row["status"]),
        created_at=row["created_at"],
        symbols=symbols,
        events=events,
    )
