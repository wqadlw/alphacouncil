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

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field

from alphacouncil.api.deps import DatabaseConnection
from alphacouncil.core.time import utc_millis
from alphacouncil.domain.instrument import parse_ticker
from alphacouncil.domain.note import (
    MAX_BODY_CHARS,
    MAX_TITLE_CHARS,
    Link,
    LinkKind,
    NoteDraft,
    NoteNotFoundError,
)
from alphacouncil.domain.note_recall import NoteNotScheduledError
from alphacouncil.domain.scheduling import ReviewRating
from alphacouncil.storage.db import transaction
from alphacouncil.storage.repositories import note_recall as recall_repository
from alphacouncil.storage.repositories import notes as repository

router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


def _now() -> datetime:
    """The current moment, as an aware UTC datetime.

    Named so the queue's "what is due?" is visibly a question about *now* at the
    call site, rather than a `datetime.now(UTC)` buried in a default argument where
    it would be evaluated once and shared.
    """
    return datetime.fromisoformat(utc_millis().replace("Z", "+00:00"))


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


# ⭐ These two models are declared **above** the handlers that annotate with
# them, and that is load-bearing too. `from __future__ import annotations` makes
# every annotation a string, and FastAPI resolves a return type when it
# *decorates* the function — so a `list[NoteScheduleRead]` pointing at a class
# further down raises `TypeAdapter[...ForwardRef...] is not fully defined`. The
# first version of the reorder moved the handler alone and hit exactly that.

class NoteScheduleRead(BaseModel):
    note_id: str
    state: str
    due_at: str
    enrolled_at: str
    updated_at: str


class NoteReviewRead(BaseModel):
    id: str
    note_id: str
    outcome: str
    rating: str | None
    reviewed_at: str
    duration_ms: int | None
    from_due_at: str
    to_due_at: str
    from_state: str
    to_state: str


# ⭐ This handler is declared **above** `/{note_id}` on purpose, and that is
# load-bearing rather than cosmetic: FastAPI matches in declaration order, so
# `/{note_id}` declared first swallows `/due` and the queue answers
# 「没有这条笔记：due」. That is what happened, and  # noqa: RUF003
# `test_the_due_route_is_not_captured_by_the_note_id_route` failed on its first
# run to say so. The card queue hit the same trap and answered it with a
# second prefix (`/api/v1/card-reviews`); a prefix is not needed here because
# the noun is already correct, so the constraint is kept local to the handler
# it constrains.
@router.get("/due", summary="The notes you asked to be brought back to")
def due_notes(
    connection: DatabaseConnection,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[NoteScheduleRead]:
    """The queue, oldest due first.

    ⭐ **No count is returned.** The product's rule is 「一句陈述，无推送、无红点、
    无催促词」, and a length here would become the number the reader is trying to
    clear. The page says what is due; it does not grade how much of it is left.
    """
    return [
        _schedule_read(row)
        for row in recall_repository.due_notes(connection, as_of=_now(), limit=limit)
    ]


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


class BacklinkRead(BaseModel):
    """One note that points at something, as the reader needs to see it.

    ⭐ **`from_note_id` plus `title`, not the whole note.** A backlink list is read by
    someone who has just followed a link and wants to know *where they arrived*, so the
    two things they need are 「which note」 and 「what it is called」. The body is not
    one of them, and ⭐ sending it would make this endpoint a way to fetch any note
    the caller can name — which `GET /notes/{id}` already is, but with an id the caller
    had to guess.

    ⭐ The id travels because the row is a link: **a list of titles with no way to open
    them is a list of labels**, and the whole point of a backlink is to be clickable.
    """

    model_config = ConfigDict(extra="forbid")

    from_note_id: str
    title: str


@router.get(
    "/{note_id}/backlinks",
    summary="Notes that point at this note",
    response_model=list[BacklinkRead],
)
def backlinks(note_id: str, connection: DatabaseConnection) -> list[BacklinkRead]:
    """Which notes point **at** this one.

    ⭐ **A backlink is only interesting the other way round, so this exists because
    `note_links` can already store it and nothing could read it.** `notes.py`'s
    `backlinks_for` has been in the repository since spec 026 with a test and no caller
    — which is the shape `status.md` has been carrying as 「反链有函数无面板」 since the
    day it was true.

    ⚠️ **Two things about this handler that look like boilerplate and are not:**

    1. ⭐ **`get_by_id` is called first and raises.** `NOTE_NOT_FOUND` is **not** in
       `errors.py`'s status table, so an uncaught `NoteNotFoundError` would answer
       **400, not 404** — a wrong status code for a missing note, on the one route where
       "missing" is a plausible thing for a client to ask about. ⭐ `GET /{note_id}`
       already has the explicit `try/except` for this reason; this route reuses the
       same shape rather than trusting the fallback.
    2. ⭐ **The rows are resolved in order and nothing is filtered, because there is
       nothing to filter.** ⭐ The first version of this handler carried
       `if row is not None` with a comment explaining that a backlink to a deleted note
       is skipped — ⭐ **and the comment was wrong in two ways at once.** Measured
       against a real database on 2026-09-30: `note_links.from_note_id` **cascades**, so
       deleting the source note removes the link row before any query runs; and
       `get_by_id` **raises** rather than returning `None` for a missing note, so the
       guard could never have been reached even if the row had survived.

       ⭐ So the filter was unreachable code that read as though it were protecting
       something — the same shape as `EVENT_LABEL` in `format.ts`, deleted the same day
       for the same reason. ⭐ A guard written from an assumption instead of a
       measurement is worse than no guard: it survives review, it reads as diligence,
       and the protection it appears to provide was never there.
    """
    try:
        repository.get_by_id(connection, note_id)
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [
        BacklinkRead(
            from_note_id=from_id,
            title=repository.get_by_id(connection, from_id).note.title,
        )
        for from_id in repository.backlinks_for(connection, LinkKind.NOTE, note_id)
    ]


@router.post("/{note_id}/links", summary="Point a note at a card, decision or note")
def add_link(
    note_id: str, payload: NoteLinkInput, connection: DatabaseConnection
) -> NoteRead:
    with transaction(connection):
        repository.add_link(
            connection, note_id, Link(to_kind=payload.to_kind, to_id=payload.to_id)
        )
        return _to_read(repository.get_by_id(connection, note_id))


# ── the recall queue (spec 028) ─────────────────────────────────────────────
#
# ⭐ **`/due` is declared before `/{note_id}`**, and that ordering is the whole
# reason this block sits here rather than at the end of the file. FastAPI matches
# in declaration order, so `GET /due` registered after `GET /{note_id}` is
# captured by it and answers 404 with a message about a note whose id is "due".
# The card router hit precisely this and gave its queue a separate prefix
# (`reviews.py`); here the prefix is already right, so the fix is ordering — and
# `test_the_due_route_is_not_captured_by_the_note_id_route` is what keeps it.


class NoteReviewRequest(BaseModel):
    """A rating for a re-read.

    ⭐ For a note `again` means 「**我的想法已经变了**」, not 「我忘了」. The wire
    format cannot express the difference — it is the same string — so the wording
    that carries it lives in the UI, and `notesContract.test.ts` pins that the
    client is given something to say other than "again".
    """

    model_config = ConfigDict(extra="forbid")

    rating: ReviewRating
    duration_ms: int | None = Field(default=None, gt=0)


class DeferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=7, gt=0, le=90)


def _schedule_read(row: Any) -> NoteScheduleRead:
    return NoteScheduleRead(
        note_id=row.note_id,
        state=row.state.value,
        due_at=row.due_at.isoformat(),
        enrolled_at=row.enrolled_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _review_read(row: Any) -> NoteReviewRead:
    return NoteReviewRead(
        id=row.id,
        note_id=row.note_id,
        outcome=row.outcome.value,
        rating=None if row.rating is None else row.rating.value,
        reviewed_at=row.reviewed_at.isoformat(),
        duration_ms=row.duration_ms,
        from_due_at=row.from_due_at.isoformat(),
        to_due_at=row.to_due_at.isoformat(),
        from_state=row.from_state.value,
        to_state=row.to_state.value,
    )


@router.post("/{note_id}/schedule", summary="Ask for a note to come back")
def enroll(note_id: str, connection: DatabaseConnection) -> NoteScheduleRead:
    """Put a note on the recall queue.

    ⭐ **Explicit, and never automatic.** Enrolling everything the reader ever
    wrote builds a backlog nobody drains.

    ⭐ The note is looked up **first** so a bad id answers 404. Without it the
    foreign key does the refusing, and a caller mistake surfaces as a
    ``sqlite3.IntegrityError`` — a 500 for something it got wrong, and a stack
    trace naming a constraint instead of the note.
    """
    try:
        repository.get_by_id(connection, note_id)
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    with transaction(connection):
        row = recall_repository.enroll(connection, note_id)
    return _schedule_read(row)


@router.get("/{note_id}/schedule", summary="One note's schedule")
def read_schedule(note_id: str, connection: DatabaseConnection) -> NoteScheduleRead:
    try:
        return _schedule_read(recall_repository.get_schedule(connection, note_id))
    except NoteNotScheduledError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{note_id}/reviews", summary="Everything that happened to a note's schedule")
def read_reviews(note_id: str, connection: DatabaseConnection) -> list[NoteReviewRead]:
    """The history, oldest first — **including the resets**.

    This is the function that answers 「我复习过好几次，为什么今天又来?」, so a
    rewrite that restarted the schedule is in it rather than invisible.
    """
    return [_review_read(row) for row in recall_repository.list_reviews(connection, note_id)]


@router.post("/{note_id}/review", summary="Record a re-read")
def review(
    note_id: str, payload: NoteReviewRequest, connection: DatabaseConnection
) -> NoteReviewRead:
    """Record a re-read and move the schedule. One transaction, both or neither."""
    with transaction(connection):
        row = recall_repository.record_review(
            connection, note_id, payload.rating, duration_ms=payload.duration_ms
        )
    return _review_read(row)


@router.post("/{note_id}/defer", summary="Postpone: 我的想法还没定")
def defer(
    note_id: str, payload: DeferRequest, connection: DatabaseConnection
) -> NoteReviewRead:
    """Postpone a note without touching its memory.

    ⭐ 「还没想清楚」 is not a failure. A note pushed three times must not come back
    angrier each time, so ``state_json`` is written back byte-identical.
    """
    with transaction(connection):
        row = recall_repository.defer(connection, note_id, days=payload.days)
    return _review_read(row)
