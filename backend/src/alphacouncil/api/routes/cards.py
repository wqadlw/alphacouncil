"""The knowledge-card API (K1) — record a claim with its provenance.

Four verbs: ``POST`` records a card, ``GET`` lists and reads, ``PATCH
/{id}/verify`` upgrades an ``ai_generated`` card to ``user_written``. There is
no ``PUT``, no ``DELETE`` and no way to edit ``content``: a card is a signed
statement, and editing it after the fact would quietly rewrite what you once
claimed and where it came from. Changing your mind is a new card (or, later, a
``converged`` status), never an edit of the old one.

**The request schema forbids unknown fields, and that is load-bearing.** The
``id``, ``captured_at`` and ``created_at`` columns are server-generated — the
primary key is the moment the statement was recorded, which is the provenance.
A client that smuggles in an ``id`` is a client trying to back-date a claim,
and ``extra="forbid"`` turns that attempt into a ``422`` naming the field
(S-06, the same rule that guards ``decisions``).

**Symbols are tickers, resolved through the same parser the rest of the API
uses.** ``sh:600519`` in the spec sketch was written before ``parse_ticker``
existed; the conventional spelling here is ``600519`` / ``sh600519`` /
``600519.SH``, and ambiguity (``000xxx``) is refused loudly rather than
guessed — a card misattributed to the wrong exchange is a card that will later
read as evidence for the wrong thesis.

Nothing here re-checks what the domain checks. The route parses the tickers,
the domain refuses a blank claim or a sourceless one, and the database is the
floor under both.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field

from alphacouncil.api.deps import DatabaseConnection
from alphacouncil.domain.card import (
    MAX_CONTENT_CHARS,
    MAX_TITLE_CHARS,
    CardNotFoundError,
    CardOrigin,
    CardStatus,
    ClaimType,
    build_card_draft,
)
from alphacouncil.domain.instrument import parse_ticker
from alphacouncil.models.market import Market
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import cards as repository

__all__ = ["CardRead", "router", "to_read"]

router = APIRouter(prefix="/api/v1/cards", tags=["cards"])


class CardCreateRequest(BaseModel):
    """Record a card. No ``id``, no ``captured_at``, no ``created_at``.

    ``extra="forbid"`` is load-bearing, not tidiness: the primary key is the
    moment the statement was recorded, and a client-supplied moment is a client
    moving the provenance. There is deliberately no server-assigned field
    declared here, not even one that exists only to be refused — S-06 flags any
    request schema that declares one, and its reasoning is worth keeping: the
    defect is that the field *exists*, which no execution path reveals.
    """

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    claim_type: ClaimType
    source_url: str = Field(
        min_length=1,
        description="The provenance. Must be an http(s) URL (red line 4).",
    )
    source_title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    as_of: date | None = Field(
        default=None,
        description=(
            "Point-in-time cutoff for the claim's figures (e.g. a report period). "
            "Optional: a claim about the future has no as-of date."
        ),
    )
    origin: CardOrigin = CardOrigin.USER_WRITTEN
    priority: int = Field(default=3, ge=1, le=5)
    symbols: list[str] = Field(
        default_factory=list,
        description=(
            "Tickers this claim concerns, each in the conventional spelling "
            "(600519 / sh600519 / 600519.SH). Empty means the card is not tied "
            "to any instrument."
        ),
    )


class SymbolRead(BaseModel):
    """One instrument a card is attached to, in the conventional form."""

    market: str
    code: str
    display: str


class CardRead(BaseModel):
    """One card, as stored, with its symbols already rendered."""

    id: str = Field(
        description=(
            "The moment it was recorded, UTC with millisecond precision — the "
            "primary key and the provenance in one value. Server-generated."
        )
    )
    content: str
    claim_type: ClaimType
    source_url: str
    source_title: str
    captured_at: str = Field(description="UTC millisecond timestamp, server clock.")
    as_of: date | None = None
    origin: CardOrigin
    priority: int
    status: CardStatus
    created_at: str = Field(description="UTC millisecond timestamp, server clock.")
    symbols: list[SymbolRead] = Field(
        default_factory=list,
        description="Every instrument this card is tied to, newest association first.",
    )


def to_read(row: repository.CardRow) -> CardRead:
    """Render a stored row for the client.

    Public, and imported by :mod:`alphacouncil.api.routes.instruments`, because
    a card looks the same wherever it is read from, and the conventional ticker
    form must have exactly one implementation.
    """
    return CardRead(
        id=row.id,
        content=row.content,
        claim_type=row.claim_type,
        source_url=row.source_url,
        source_title=row.source_title,
        captured_at=row.captured_at,
        as_of=row.as_of,
        origin=row.origin,
        priority=row.priority,
        status=row.status,
        created_at=row.created_at,
        symbols=[
            SymbolRead(market=symbol.market.value, code=symbol.code, display=symbol.full)
            for symbol in row.symbols
        ],
    )


@router.get("", summary="List cards, filtered by claim type, origin, status or instrument")
def list_cards(
    connection: DatabaseConnection,
    market: Market | None = None,
    code: str | None = None,
    claim_type: ClaimType | None = None,
    origin: CardOrigin | None = None,
    status: CardStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CardRead]:
    """List cards newest first.

    ``market`` and ``code`` filter together: neither without the other is
    meaningful (a code alone cannot identify an exchange), so the route asks for
    both or neither and refuses the one-sided form with a ``422`` — guessing the
    exchange for a bare code is precisely the inference the domain forbids.

    An empty result answers ``[]``: nothing matched, which is not a failure.
    """
    if (market is None) != (code is None):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="market and code must be provided together",
        )

    if market is not None and code is not None:
        symbol = parse_ticker(code, market=market)
        rows = repository.list_for_symbol(connection, symbol)
    else:
        rows = repository.query(
            connection,
            claim_type=claim_type,
            origin=origin,
            status=status,
            limit=limit,
        )
    return [to_read(row) for row in rows]


@router.get("/{card_id}", summary="Read one card")
def get_card(card_id: str, connection: DatabaseConnection) -> CardRead:
    """Return one card, or a ``404`` envelope when it does not exist."""
    row = repository.get_by_id(connection, card_id)
    if row is None:
        raise CardNotFoundError(f"card {card_id!r} not found")
    return to_read(row)


@router.post("", status_code=http_status.HTTP_201_CREATED, summary="Record a card")
def create(payload: CardCreateRequest, connection: DatabaseConnection) -> CardRead:
    """Append a card, creating instrument rows for any new symbols.

    Raises:
        TickerInvalidError: A symbol is malformed or contradicts a stated
            market. Surfaces as the standard envelope with a 400.
        CardError: The claim or its source is blank, or the URL is not
            http(s). Also the standard envelope, with a 400.
    """
    draft = build_card_draft(
        content=payload.content,
        claim_type=payload.claim_type,
        source_url=payload.source_url,
        source_title=payload.source_title,
        origin=payload.origin,
        priority=payload.priority,
        status=CardStatus.ACTIVE,
        as_of=payload.as_of,
        symbols=tuple(parse_ticker(ticker) for ticker in payload.symbols),
    )
    with transaction(connection):
        return to_read(repository.create(connection, draft))


@router.patch("/{card_id}/verify", summary="Upgrade an ai_generated card to user_written")
def verify(card_id: str, connection: DatabaseConnection) -> CardRead:
    """Mark an ``ai_generated`` card as checked against its source.

    Only an ``ai_generated`` card may be upgraded — that is the isolation red
    line (15): an AI candidate stays flagged until a person has actually looked
    at the source. Upgrading anything else is a ``409``.

    Raises:
        CardNotFoundError: The card does not exist. 404.
        CardAlreadyVerifiedError: The card is not ``ai_generated``. 409.
    """
    with transaction(connection):
        return to_read(repository.verify(connection, card_id))
