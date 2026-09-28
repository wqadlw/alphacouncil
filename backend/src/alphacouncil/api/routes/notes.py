"""The knowledge-note API (spec 026) — the other half of the knowledge layer.

Verbs: ``POST`` records a note, ``GET`` lists and reads, ``PATCH /{id}`` edits
title and body, and ``POST /{id}/tags`` / ``DELETE /{id}/tags/{tag}`` manage the
tag set.

**What is different from the card API, and why each difference is the point:**

* **No source is required.** A card is a signed claim, so it carries a
  ``source_url``; a note is a note, and 「流动性收紧时周期股先跌」 has no citation.
  Forcing one would push the reader to attach a link they have not read — which
  makes the provenance rule *worse*, not more forgiving. The rule is untouched
  on the card side, and ``test_a_card_still_may_not_be_written_without_a_source``
  pins it.
* **There is a ``PATCH``.** Cards have no edit verb, on purpose: editing a claim
  rewrites what you once said and where it came from. A note is working text, so
  refusing to edit it would just push people to keep re-typing the same note.
  ``created_at`` never moves, so "我什么时候想到这个" stays answerable.
* **Instruments are optional and there may be several.** The card API takes one
  symbol from the path. A note about a method or a macro view has none; a note
  about a stock has one; a note about a sector might have several.

**Unknown fields are refused** (``extra="forbid"``, the same rule that guards
``cards`` and ``decisions``): ``id``, ``created_at`` and ``updated_at`` are
server-generated, and a client that smuggles one in is trying to back-date a
record.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field

from alphacouncil.api.deps import DatabaseConnection
from alphacouncil.domain.instrument import parse_ticker
from alphacouncil.domain.note import (
    MAX_BODY_CHARS,
    MAX_TITLE_CHARS,
    Link,
    LinkKind,
    NoteDraft,
    NoteNotFoundError,
)
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import notes as repository

router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


class NoteLinkRead(BaseModel):
    to_kind: str
    to_id: str


class NoteSymbolRead(BaseModel):
    market: str
    code: str


class NoteRead(BaseModel):
    """One note, flattened for the wire.

    Flattened rather than nested under a `note` key because the API is the
    contract and a client should not have to know that the repository returns a
    row *with relationships* — the shape it happens to have in Python is not the
    shape the product has.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    body: str
    as_of: date | None
    created_at: str
    updated_at: str
    tags: list[str]
    links: list[NoteLinkRead]
    symbols: list[NoteSymbolRead]


def _to_read(row: object) -> NoteRead:
    from alphacouncil.domain.note import NoteRow

    assert isinstance(row, NoteRow)
    return NoteRead(
        id=row.note.id,
        title=row.note.title,
        body=row.note.body,
        as_of=row.as_of,
        created_at=row.note.created_at,
        updated_at=row.note.updated_at,
        tags=list(row.tags),
        links=[NoteLinkRead(to_kind=lk.to_kind.value, to_id=lk.to_id) for lk in row.links],
        symbols=[
            NoteSymbolRead(market=s.market.value, code=s.code) for s in row.symbols
        ],
    )


class NoteLinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_kind: LinkKind
    to_id: str = Field(min_length=1)


class NoteCreate(BaseModel):
    """A new note. No ``id``, no timestamps, no source."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)
    as_of: date | None = None
    tags: list[str] = Field(default_factory=list)
    links: list[NoteLinkInput] = Field(default_factory=list)
    #: Tickers, in the same three spellings the rest of the API accepts.
    symbols: list[str] = Field(default_factory=list)

    def to_draft(self) -> NoteDraft:
        return NoteDraft(
            title=self.title,
            body=self.body,
            as_of=self.as_of,
            tags=tuple(self.tags),
            links=tuple(Link(to_kind=lk.to_kind, to_id=lk.to_id) for lk in self.links),
            symbols=tuple(parse_ticker(raw) for raw in self.symbols),
        )


class NoteUpdate(BaseModel):
    """Edit a note. Either field may be omitted; `created_at` is not editable."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_CHARS)
    body: str | None = Field(default=None, min_length=1, max_length=MAX_BODY_CHARS)


class TagWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str = Field(min_length=1)


@router.post("", status_code=http_status.HTTP_201_CREATED, summary="Record a note")
def create_note(
    payload: NoteCreate, connection: DatabaseConnection
) -> NoteRead:
    """Record a note. **No source required, and that is the feature.**"""
    with transaction(connection):
        created = repository.create(connection, payload.to_draft())
    return _to_read(created)


@router.get("", summary="List notes, newest edit first")
def list_notes(
    connection: DatabaseConnection,
    tag: Annotated[str | None, Query(description="Exact tag match; never a prefix")] = None,
    q: Annotated[
        str | None,
        Query(
            description=(
                "Substring search over title and body. Two characters work — the "
                "trigram tokenizer's floor is three, so shorter queries take a "
                "substring path that has no tokeniser and therefore no floor."
            )
        ),
    ] = None,
) -> list[NoteRead]:
    """Every note, or the ones matching a tag, a search, or both.

    ⭐ The tag filter is an **exact** match, and that is not an implementation
    detail: a ``LIKE '%宏观%'`` filter returns 宏观债 as well, and the reader's
    filtered list then silently omits a note they can see in the unfiltered one
    with no way to work out why.

    ⭐ **Search reads the title and the body, not the tags.** Tags have their own
    control one row above the list, and indexing them would mean the FTS triggers
    had to re-read ``note_tags`` on every note write. Stated here as well as in the
    repository, because a reader who types a tag into the search box and gets
    nothing needs to be able to find out why.

    `q` and `tag` **compose** — 「流动性」 within 「宏观」. The tag filter is applied
    after the search, in Python, because every row is hydrated with its tags
    anyway; that is the cheap choice at the constitution's stated scale (个人级
    几千条) and it keeps one `ORDER BY` rather than three copies of it.
    """
    if q and q.strip():
        rows = repository.search(connection, q)
    elif tag:
        rows = repository.list_by_tag(connection, tag)
    else:
        rows = repository.list_all(connection)

    if tag and q and q.strip():
        rows = [row for row in rows if tag in row.tags]
    return [_to_read(r) for r in rows]


@router.get("/tags", summary="Every tag in use")
def list_tags(connection: DatabaseConnection) -> list[str]:
    return repository.all_tags(connection)


@router.get("/{note_id}", summary="One note")
def get_note(note_id: str, connection: DatabaseConnection) -> NoteRead:
    try:
        return _to_read(repository.get_by_id(connection, note_id))
    except NoteNotFoundError as exc:
        # Refusing rather than returning an empty note: a caller that treats
        # "absent" as "empty" renders a blank page for a deleted id and calls it
        # an empty vault.
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{note_id}", summary="Edit a note's title or body")
def update_note(
    note_id: str, payload: NoteUpdate, connection: DatabaseConnection
) -> NoteRead:
    with transaction(connection):
        updated = repository.update_body(
            connection, note_id, title=payload.title, body=payload.body
        )
    return _to_read(updated)


@router.post("/{note_id}/tags", summary="Add a tag")
def add_tag(
    note_id: str, payload: TagWrite, connection: DatabaseConnection
) -> NoteRead:
    with transaction(connection):
        repository.add_tag(connection, note_id, payload.tag)
        return _to_read(repository.get_by_id(connection, note_id))


@router.delete("/{note_id}/tags/{tag}", summary="Remove a tag")
def remove_tag(note_id: str, tag: str, connection: DatabaseConnection) -> NoteRead:
    with transaction(connection):
        repository.remove_tag(connection, note_id, tag)
        return _to_read(repository.get_by_id(connection, note_id))


@router.post("/{note_id}/links", summary="Point a note at a card, decision or note")
def add_link(
    note_id: str, payload: NoteLinkInput, connection: DatabaseConnection
) -> NoteRead:
    with transaction(connection):
        repository.add_link(
            connection, note_id, Link(to_kind=payload.to_kind, to_id=payload.to_id)
        )
        return _to_read(repository.get_by_id(connection, note_id))
