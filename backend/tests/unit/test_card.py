import sqlite3
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pytest

from alphacouncil.domain.card import (
    CardAlreadyVerifiedError,
    CardContentRequiredError,
    CardConvergeReasonRequiredError,
    CardDraft,
    CardEventType,
    CardNotActiveError,
    CardNotFoundError,
    CardOrigin,
    CardPriorityInvalidError,
    CardSourceTitleRequiredError,
    CardSourceUrlRequiredError,
    CardStatus,
    CardTextTooLongError,
    ClaimType,
    build_card_draft,
)
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage import db, migrate
from alphacouncil.storage.repositories import cards as repository

pytestmark = pytest.mark.unit


def test_valid_card_draft_construction() -> None:
    symbol = Symbol(market=Market.SH, code="600519")
    draft = build_card_draft(
        content="渠道库存是白酒先行指标",
        claim_type=ClaimType.SUPPORTING,
        source_url="https://example.com/reports/123",
        source_title="白酒渠道深度调研",
        origin=CardOrigin.USER_WRITTEN,
        priority=4,
        status=CardStatus.ACTIVE,
        as_of=date(2026, 6, 30),
        symbols=(symbol,),
    )
    assert draft.content == "渠道库存是白酒先行指标"
    assert draft.claim_type == ClaimType.SUPPORTING
    assert draft.source_url == "https://example.com/reports/123"
    assert draft.source_title == "白酒渠道深度调研"
    assert draft.origin == CardOrigin.USER_WRITTEN
    assert draft.priority == 4
    assert draft.status == CardStatus.ACTIVE
    assert draft.as_of == date(2026, 6, 30)
    assert draft.symbols == (symbol,)


def test_blank_content_raises() -> None:
    with pytest.raises(CardContentRequiredError):
        build_card_draft(
            content="   ",
            claim_type=ClaimType.NEUTRAL,
            source_url="https://example.com",
            source_title="Report",
        )


def test_overlong_content_raises() -> None:
    with pytest.raises(CardTextTooLongError):
        build_card_draft(
            content="x" * 1001,
            claim_type=ClaimType.NEUTRAL,
            source_url="https://example.com",
            source_title="Report",
        )


def test_blank_source_url_raises() -> None:
    with pytest.raises(CardSourceUrlRequiredError):
        build_card_draft(
            content="Valid statement",
            claim_type=ClaimType.NEUTRAL,
            source_url="   ",
            source_title="Report",
        )


def test_invalid_source_url_scheme_raises() -> None:
    with pytest.raises(CardSourceUrlRequiredError):
        build_card_draft(
            content="Valid statement",
            claim_type=ClaimType.NEUTRAL,
            source_url="ftp://example.com",
            source_title="Report",
        )

    with pytest.raises(CardSourceUrlRequiredError):
        build_card_draft(
            content="Valid statement",
            claim_type=ClaimType.NEUTRAL,
            source_url="not-a-url",
            source_title="Report",
        )


def test_blank_source_title_raises() -> None:
    with pytest.raises(CardSourceTitleRequiredError):
        build_card_draft(
            content="Valid statement",
            claim_type=ClaimType.NEUTRAL,
            source_url="https://example.com",
            source_title="   ",
        )


def test_invalid_priority_raises() -> None:
    with pytest.raises(CardPriorityInvalidError):
        build_card_draft(
            content="Valid statement",
            claim_type=ClaimType.NEUTRAL,
            source_url="https://example.com",
            source_title="Report",
            priority=0,
        )

    with pytest.raises(CardPriorityInvalidError):
        build_card_draft(
            content="Valid statement",
            claim_type=ClaimType.NEUTRAL,
            source_url="https://example.com",
            source_title="Report",
            priority=6,
        )


# ---------------------------------------------------------------------------
# Repository layer (storage/repositories/cards.py).
# ---------------------------------------------------------------------------
# These live in the same file as the domain tests because the repository is the
# second half of the same K1 contract: the domain refuses bad input, the
# repository must persist and return every field unchanged. Until this section
# existed the repository had zero coverage — and a CardRow field defect shipped
# green because nothing ever called ``create`` (constitution 8.1: a defect the
# tests cannot see is the same as no tests at all).


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """A real database file at the current shipped schema version."""
    path = tmp_path / "alphacouncil.db"
    connection = db.connect_for_migration(path)
    try:
        migrate.apply(connection, database_path=path)
    finally:
        connection.close()
    return path


@pytest.fixture
def connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    conn = db.connect(database_path)
    try:
        yield conn
    finally:
        conn.close()


def _write[T](connection: sqlite3.Connection, call: Callable[[], T]) -> T:
    """Run one multi-table write inside a transaction, the way a route does.

    ``cards.verify`` and ``cards.converge`` each write a row to ``cards`` and a
    row to ``card_events``, so they require an open transaction and refuse to run
    without one (``db.require_open_transaction``, regression 0006). The project
    convention is that the **caller** owns it, because a repository call often
    sits inside a larger unit of work — so a test calling the repository directly
    is a caller too, and owes the same wrapper.
    """
    with db.transaction(connection):
        return call()


def _draft(
    *,
    content: str = "渠道库存是白酒先行指标",
    claim_type: ClaimType = ClaimType.SUPPORTING,
    origin: CardOrigin = CardOrigin.USER_WRITTEN,
    symbols: tuple[Symbol, ...] = (),
) -> CardDraft:
    return build_card_draft(
        content=content,
        claim_type=claim_type,
        source_url="https://example.com/reports/123",
        source_title="白酒渠道深度调研",
        origin=origin,
        priority=4,
        status=CardStatus.ACTIVE,
        symbols=symbols,
    )


def test_create_persists_every_field_and_round_trips(
    connection: sqlite3.Connection,
) -> None:
    sym = Symbol(market=Market.SH, code="600519")
    row = repository.create(connection, _draft(symbols=(sym,)), now="2026-09-27T12:00:00.000Z")

    assert row.id.startswith("card_")
    assert row.captured_at == "2026-09-27T12:00:00.000Z"
    assert row.symbols == (sym,)

    got = repository.get_by_id(connection, row.id)
    assert got is not None
    assert got.content == "渠道库存是白酒先行指标"
    assert got.claim_type is ClaimType.SUPPORTING
    assert got.source_url == "https://example.com/reports/123"
    assert got.source_title == "白酒渠道深度调研"
    assert got.origin is CardOrigin.USER_WRITTEN
    assert got.priority == 4
    assert got.status is CardStatus.ACTIVE
    assert got.created_at == "2026-09-27T12:00:00.000Z"
    assert got.symbols == (sym,)


def test_create_without_symbols_round_trips(connection: sqlite3.Connection) -> None:
    row = repository.create(connection, _draft(), now="2026-09-27T12:00:00.000Z")
    assert row.symbols == ()
    got = repository.get_by_id(connection, row.id)
    assert got is not None
    assert got.symbols == ()


def test_create_ensures_instrument_rows_exist(connection: sqlite3.Connection) -> None:
    sym = Symbol(market=Market.SZ, code="000001")
    repository.create(connection, _draft(symbols=(sym,)), now="2026-09-27T12:00:00.000Z")
    row = connection.execute(
        "SELECT market, code FROM instruments WHERE market = ? AND code = ?",
        ("sz", "000001"),
    ).fetchone()
    assert row is not None


def test_get_by_id_missing_returns_none(connection: sqlite3.Connection) -> None:
    assert repository.get_by_id(connection, "card_1") is None


def test_query_filters_each_dimension_independently(
    connection: sqlite3.Connection,
) -> None:
    base = Symbol(market=Market.SH, code="600519")
    c1 = repository.create(
        connection,
        _draft(claim_type=ClaimType.SUPPORTING, symbols=(base,)),
        now="2026-09-27T12:00:00.000Z",
    )
    c2 = repository.create(
        connection,
        _draft(content="质疑的卡片", claim_type=ClaimType.CHALLENGING, symbols=(base,)),
        now="2026-09-27T12:00:01.000Z",
    )
    c3 = repository.create(
        connection,
        _draft(
            content="中性的卡片",
            claim_type=ClaimType.NEUTRAL,
            origin=CardOrigin.AI_GENERATED,
            symbols=(base,),
        ),
        now="2026-09-27T12:00:02.000Z",
    )

    supporting = repository.query(connection, claim_type=ClaimType.SUPPORTING)
    assert {c.id for c in supporting} == {c1.id}

    ai = repository.query(connection, origin=CardOrigin.AI_GENERATED)
    assert {c.id for c in ai} == {c3.id}

    both = repository.query(
        connection,
        claim_type=ClaimType.NEUTRAL,
        origin=CardOrigin.AI_GENERATED,
    )
    assert {c.id for c in both} == {c3.id}

    everything = repository.query(connection)
    assert {c.id for c in everything} == {c1.id, c2.id, c3.id}


def test_query_respects_limit(connection: sqlite3.Connection) -> None:
    for i in range(3):
        repository.create(
            connection, _draft(content=f"卡片 {i}"), now=f"2026-09-27T12:00:0{i}.000Z"
        )
    one = repository.query(connection, limit=1)
    assert len(one) == 1


def test_list_for_symbol_returns_only_that_symbol(
    connection: sqlite3.Connection,
) -> None:
    moutai = Symbol(market=Market.SH, code="600519")
    pab = Symbol(market=Market.SZ, code="000001")
    c1 = repository.create(connection, _draft(symbols=(moutai,)))
    repository.create(connection, _draft(content="另一只票的卡片", symbols=(pab,)))

    got = repository.list_for_symbol(connection, moutai)
    assert [c.id for c in got] == [c1.id]


def test_duplicate_symbol_association_is_idempotent(
    connection: sqlite3.Connection,
) -> None:
    sym = Symbol(market=Market.SH, code="600519")
    c1 = repository.create(
        connection, _draft(symbols=(sym,)), now="2026-09-27T12:00:00.000Z"
    )
    c2 = repository.create(
        connection, _draft(content="第二张", symbols=(sym,)), now="2026-09-27T12:00:01.000Z"
    )

    got = repository.list_for_symbol(connection, sym)
    assert {c.id for c in got} == {c1.id, c2.id}


def test_verify_upgrades_ai_generated_to_user_written(
    connection: sqlite3.Connection,
) -> None:
    row = repository.create(
        connection,
        _draft(origin=CardOrigin.AI_GENERATED),
        now="2026-09-27T12:00:00.000Z",
    )
    assert row.origin is CardOrigin.AI_GENERATED

    verified = _write(connection, lambda: repository.verify(connection, row.id))
    assert verified.origin is CardOrigin.USER_WRITTEN

    # The upgrade persists; a second read agrees with the returned row.
    again = repository.get_by_id(connection, row.id)
    assert again is not None
    assert again.origin is CardOrigin.USER_WRITTEN


def test_verify_on_user_written_card_raises(
    connection: sqlite3.Connection,
) -> None:
    row = repository.create(connection, _draft())
    with pytest.raises(CardAlreadyVerifiedError):
        repository.verify(connection, row.id)


def test_verify_on_missing_card_raises(connection: sqlite3.Connection) -> None:
    with pytest.raises(CardNotFoundError):
        repository.verify(connection, "card_999")


def test_list_all_orders_by_created_at(connection: sqlite3.Connection) -> None:
    c1 = repository.create(connection, _draft(), now="2026-09-27T12:00:00.000Z")
    c2 = repository.create(connection, _draft(content="第二张"), now="2026-09-27T12:00:01.000Z")
    got = repository.list_all(connection)
    assert [c.id for c in got] == [c1.id, c2.id]


# --- K2 (spec 013): lifecycle events and the convergence exit ---


def test_verify_records_a_verified_event(connection: sqlite3.Connection) -> None:
    row = repository.create(
        connection,
        _draft(origin=CardOrigin.AI_GENERATED),
        now="2026-09-27T12:00:00.000Z",
    )
    verified = _write(
        connection,
        lambda: repository.verify(connection, row.id, now="2026-09-27T12:05:00.000Z"),
    )

    assert len(verified.events) == 1
    event = verified.events[0]
    assert event.event_type is CardEventType.VERIFIED
    assert event.reason is None
    assert event.created_at == "2026-09-27T12:05:00.000Z"

    stored = repository.list_events(connection, row.id)
    assert [e.event_type for e in stored] == [CardEventType.VERIFIED]


def test_converge_moves_active_card_to_converged(
    connection: sqlite3.Connection,
) -> None:
    row = repository.create(connection, _draft(), now="2026-09-27T12:00:00.000Z")
    converged = _write(
        connection,
        lambda: repository.converge(
            connection,
            row.id,
            "公司改直营，渠道先行关系失效",
            now="2026-09-27T12:05:00.000Z",
        ),
    )

    assert converged.status is CardStatus.CONVERGED
    assert len(converged.events) == 1
    event = converged.events[0]
    assert event.event_type is CardEventType.CONVERGED
    assert event.reason == "公司改直营，渠道先行关系失效"

    again = repository.get_by_id(connection, row.id)
    assert again is not None
    assert again.status is CardStatus.CONVERGED
    assert again.events[0].event_type is CardEventType.CONVERGED


def test_converge_on_converged_card_raises_not_active(
    connection: sqlite3.Connection,
) -> None:
    row = repository.create(connection, _draft(), now="2026-09-27T12:00:00.000Z")
    _write(
        connection,
        lambda: repository.converge(connection, row.id, "理由", now="2026-09-27T12:05:00.000Z"),
    )
    with pytest.raises(CardNotActiveError):
        repository.converge(connection, row.id, "再试一次")


def test_converge_with_blank_reason_raises(connection: sqlite3.Connection) -> None:
    row = repository.create(connection, _draft(), now="2026-09-27T12:00:00.000Z")
    with pytest.raises(CardConvergeReasonRequiredError):
        repository.converge(connection, row.id, "   ")


def test_converge_on_missing_card_raises(connection: sqlite3.Connection) -> None:
    with pytest.raises(CardNotFoundError):
        repository.converge(connection, "card_999", "理由")


def test_list_events_orders_by_created_at(connection: sqlite3.Connection) -> None:
    row = repository.create(
        connection,
        _draft(origin=CardOrigin.AI_GENERATED),
        now="2026-09-27T12:00:00.000Z",
    )
    _write(
        connection,
        lambda: repository.verify(connection, row.id, now="2026-09-27T12:05:00.000Z"),
    )
    _write(
        connection,
        lambda: repository.converge(
            connection, row.id, "收敛理由", now="2026-09-27T12:10:00.000Z"
        ),
    )

    events = repository.list_events(connection, row.id)
    assert [e.event_type for e in events] == [
        CardEventType.VERIFIED,
        CardEventType.CONVERGED,
    ]
    assert events[1].reason == "收敛理由"
