"""Repository for knowledge notes, their tags, their links and their instruments.

Spec 026. Three rules shape the code here, and all three are about **not losing
what the user wrote**:

* **The body is stored verbatim.** No trim, no newline normalisation, no
  Markdown round-trip. The schema's CHECK is on ``length(trim(body)) > 0`` — it
  tests *that* there is content without touching *what* the content is. A
  "tidy up the input" step here would rewrite the user's own words, and for a
  product whose whole premise is that your record is trustworthy, that is the one
  bug that would not be a bug at all — it would look like help.

* **Tags are rows, never a joined string.** ``note_tags`` is one row per tag
  precisely so that ``WHERE tag = '宏观'`` cannot return ``宏观债``. The schema
  also forbids a comma inside a tag, so the joined shape cannot be reintroduced
  by a later migration.

* **The instrument association is a real table with a real foreign key.** Unlike
  ``note_links`` (which is polymorphic and therefore checked in Python), a note's
  instruments go in ``note_note_symbols`` and the database enforces that they
  exist. The asymmetry is deliberate and is called out in the migration.

**Transactions.** The API layer owns the transaction (``storage.db.transaction``);
this module asserts one is open via ``require_open_transaction`` rather than
opening its own, so a note and its tags cannot be half-written.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, date, datetime

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.note import (
    Link,
    LinkKind,
    Note,
    NoteDraft,
    NoteIdExhaustedError,
    NoteLinkSelfError,
    NoteLinkTargetUnknownError,
    NoteNotFoundError,
    NoteRow,
    validate_draft,
    validate_tag,
)
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage.db import require_open_transaction

# ⭐ Imported here, not lazily inside the function, so the seam is visible at
# the top of the file: editing a note on the recall queue restarts its
# schedule (spec 028). A local import would hide the one line in this module
# that makes the queue trustworthy.
from alphacouncil.storage.repositories import instruments, note_recall

__all__ = [
    "add_link",
    "add_tag",
    "create",
    "get_by_id",
    "link_targets_exist",
    "list_all",
    "list_by_tag",
    "remove_tag",
    "update_body",
]


# ── SQL ─────────────────────────────────────────────────────────────────────

_INSERT_NOTE = """
INSERT INTO notes (id, title, body, as_of, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?)
"""

_UPDATE_NOTE = """
UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?
"""

# The column list is written out in each query rather than interpolated from a
# shared constant. A constant was the first draft and it cost two things: ruff's
# S608 fired on the f-string (a false positive — the value is a module constant,
# never user input), and the query could no longer be read top-to-bottom without
# jumping to another name. `cards.py` writes its columns out literally, so this
# matches the house style, and the duplication is six words per query.
_SELECT_BY_ID = """
SELECT id, title, body, as_of, created_at, updated_at
FROM notes WHERE id = ?
"""

_SELECT_ALL = """
SELECT id, title, body, as_of, created_at, updated_at
FROM notes
ORDER BY updated_at DESC, id DESC
"""

_SELECT_BY_TAG = """
SELECT n.id, n.title, n.body, n.as_of, n.created_at, n.updated_at
FROM notes AS n
JOIN note_tags AS t ON t.note_id = n.id
WHERE t.tag = ?
ORDER BY n.updated_at DESC, n.id DESC
"""

_INSERT_TAG = "INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)"
_DELETE_TAG = "DELETE FROM note_tags WHERE note_id = ? AND tag = ?"
_SELECT_TAGS = "SELECT tag FROM note_tags WHERE note_id = ? ORDER BY tag"
_SELECT_TAGS_GLOBAL = (
    "SELECT DISTINCT tag FROM note_tags ORDER BY tag"
)

_INSERT_LINK = """
INSERT OR IGNORE INTO note_links (from_note_id, to_kind, to_id, created_at)
VALUES (?, ?, ?, ?)
"""
_SELECT_LINKS = """
SELECT to_kind, to_id FROM note_links WHERE from_note_id = ?
ORDER BY to_kind, to_id
"""
_SELECT_BACKLINKS = """
SELECT from_note_id FROM note_links WHERE to_kind = ? AND to_id = ?
ORDER BY from_note_id
"""

_INSERT_SYMBOL = """
INSERT OR IGNORE INTO note_note_symbols (note_id, market, code, created_at)
VALUES (?, ?, ?, ?)
"""
_SELECT_SYMBOLS = """
SELECT market, code FROM note_note_symbols WHERE note_id = ?
ORDER BY market, code
"""

#: The table each link kind must resolve into. This is the check the schema
#: cannot do, so it is data rather than prose: a new `LinkKind` without an entry
#: here fails the tests rather than producing a dead link.
_LINK_TARGET_TABLE: dict[LinkKind, str] = {
    LinkKind.NOTE: "notes",
    LinkKind.CARD: "cards",
    LinkKind.DECISION: "decisions",
    LinkKind.INSTRUMENT: "instruments",
    # J5 教训转卡 is next round, so there is no lessons table yet. `LESSON` is in
    # the enum so the schema, the docs and the enum agree now; the lookup below
    # returns False for it until that table exists, which is the honest behaviour
    # — a link to a lesson cannot be written before lessons can be.
    LinkKind.LESSON: "lessons",
}


# ── id minting ──────────────────────────────────────────────────────────────


def _stamp_to_dt(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)


def _generate_note_id(now_dt: datetime | None = None) -> str:
    millis = int(now_dt.timestamp() * 1000) if now_dt is not None else int(time.time() * 1000)
    return f"note_{millis}"


#: How far past the requested millisecond we will look for a free id.
#:
#: 1000 is one second. Beyond that two writes are not "the same moment" any more,
#: and minting a note whose id lies about when it was written would break the
#: `GLOB('note_[0-9]*', id)` → timestamp reading that the whole scheme rests on.
_ID_COLLISION_LIMIT = 1_000


def _mint_note_id(connection: sqlite3.Connection, now_dt: datetime) -> str:
    """A note id that is not already taken.

    ⭐ The cards repository mints ``card_<millis>`` and, when two cards land in
    the same millisecond, the INSERT fails with a bare
    ``UNIQUE constraint failed``. That is a known hazard there — recorded in the
    K1 changelog — and it is **not** reproduced here.

    Two reasons. First, the failure mode is terrible for this feature: "快速记
    一句" means two notes inside one millisecond is an ordinary thing to do, and
    the user should not lose a note to it. Second, the alternative to raising is
    worse — a note that silently overwrote another is the exact failure the whole
    append-only discipline exists to prevent.

    So the id walks forward a millisecond at a time until it is free. `created_at`
    is still the real stamp; only the *id* moves, and only in the rare case.
    """
    base = int(now_dt.timestamp() * 1000)
    for offset in range(_ID_COLLISION_LIMIT):
        candidate = f"note_{base + offset}"
        taken = connection.execute(
            "SELECT 1 FROM notes WHERE id = ?", (candidate,)
        ).fetchone()
        if taken is None:
            return candidate
    raise NoteIdExhaustedError(
        "无法为这条笔记生成唯一 id：同一毫秒内已有多达 "
        f"{_ID_COLLISION_LIMIT} 条笔记。"
    )


# ── row mapping ─────────────────────────────────────────────────────────────


def _to_note(row: sqlite3.Row) -> Note:
    return Note(
        id=row["id"],
        title=row["title"],
        body=row["body"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _load_tags(connection: sqlite3.Connection, note_id: str) -> tuple[str, ...]:
    return tuple(
        r["tag"] for r in connection.execute(_SELECT_TAGS, (note_id,)).fetchall()
    )


def _load_links(connection: sqlite3.Connection, note_id: str) -> tuple[Link, ...]:
    return tuple(
        Link(to_kind=LinkKind(r["to_kind"]), to_id=r["to_id"])
        for r in connection.execute(_SELECT_LINKS, (note_id,)).fetchall()
    )


def _load_symbols(connection: sqlite3.Connection, note_id: str) -> tuple[Symbol, ...]:
    return tuple(
        Symbol(market=Market(r["market"]), code=r["code"])
        for r in connection.execute(_SELECT_SYMBOLS, (note_id,)).fetchall()
    )


def _to_note_row(connection: sqlite3.Connection, row: sqlite3.Row) -> NoteRow:
    note = _to_note(row)
    raw_as_of = row["as_of"]
    return NoteRow(
        note=note,
        tags=_load_tags(connection, note.id),
        links=_load_links(connection, note.id),
        symbols=_load_symbols(connection, note.id),
        # ⭐ Read from the row, not defaulted to None. The first draft of this
        # function had `as_of=None` hard-coded while `NoteRow.as_of` existed —
        # a field that always answers "no cutoff date" no matter what was stored,
        # which is worse than not having it, because the caller cannot tell the
        # two cases apart.
        as_of=date.fromisoformat(raw_as_of) if raw_as_of is not None else None,
    )


def _hydrate(connection: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[NoteRow]:
    return [_to_note_row(connection, r) for r in rows]


# ── public API ──────────────────────────────────────────────────────────────


def create(
    connection: sqlite3.Connection,
    draft: NoteDraft,
    *,
    now: str | None = None,
) -> NoteRow:
    """Write a note with its tags, links and instruments, in the caller's transaction."""
    require_open_transaction(connection, operation="notes.create")
    validate_draft(draft)

    stamp = now if now is not None else utc_millis()
    now_dt = _stamp_to_dt(stamp)
    note_id = _mint_note_id(connection, now_dt)

    for link in draft.links:
        if link.to_kind is LinkKind.NOTE and link.to_id == note_id:
            # A brand-new note cannot already be its own target, but the check is
            # here rather than in `validate_draft` because it needs the id, which
            # is only known after the stamp is chosen.
            raise NoteLinkSelfError("一条笔记不能链接到自己。")

    connection.execute(
        _INSERT_NOTE,
        (
            note_id,
            draft.title,
            draft.body,
            draft.as_of.isoformat() if draft.as_of is not None else None,
            stamp,
            stamp,
        ),
    )

    for tag in draft.tags:
        connection.execute(_INSERT_TAG, (note_id, validate_tag(tag)))

    for link in draft.links:
        if not link_targets_exist(connection, link):
            raise NoteLinkTargetUnknownError(
                f"链接目标不存在：{link.to_kind.value}/{link.to_id}"
            )
        connection.execute(_INSERT_LINK, (note_id, link.to_kind.value, link.to_id, stamp))

    for sym in draft.symbols:
        instruments.ensure(connection, sym, now=stamp)
        connection.execute(
            _INSERT_SYMBOL, (note_id, sym.market.value, sym.code, stamp)
        )

    return NoteRow(
        note=Note(
            id=note_id,
            title=draft.title,
            body=draft.body,
            created_at=stamp,
            updated_at=stamp,
        ),
        # ⭐ Sorted, not in the order they were supplied.
        #
        # `get_by_id` reads them back with `ORDER BY tag`, so returning insertion
        # order here made the *same note* answer with a different tag list
        # depending on whether you had just written it or fetched it again.
        # `test_tags_can_be_added_and_removed` caught it: a client that renders the
        # create response would show one order, and the same client a second later
        # another, with no edit in between.
        tags=tuple(sorted({validate_tag(t) for t in draft.tags})),
        links=tuple(sorted(draft.links, key=lambda lk: (lk.to_kind.value, lk.to_id))),
        symbols=draft.symbols,
        as_of=draft.as_of,
    )


def get_by_id(connection: sqlite3.Connection, note_id: str) -> NoteRow:
    """One note, or refuse. There is no "create if missing" here on purpose."""
    row = connection.execute(_SELECT_BY_ID, (note_id,)).fetchone()
    if row is None:
        raise NoteNotFoundError(f"没有这条笔记：{note_id}")
    return _to_note_row(connection, row)


def list_all(connection: sqlite3.Connection) -> list[NoteRow]:
    """Every note, newest edit first."""
    return _hydrate(connection, connection.execute(_SELECT_ALL).fetchall())


def list_by_tag(connection: sqlite3.Connection, tag: str) -> list[NoteRow]:
    """Notes carrying one tag, matched **exactly**.

    ⭐ This is the query the comma-string design would have broken. A
    ``LIKE '%宏观%'`` filter returns `宏观债` as well, and the user cannot see
    why — the row simply is not in the list they asked for.
    """
    return _hydrate(
        connection, connection.execute(_SELECT_BY_TAG, (validate_tag(tag),)).fetchall()
    )


def all_tags(connection: sqlite3.Connection) -> list[str]:
    return [r["tag"] for r in connection.execute(_SELECT_TAGS_GLOBAL).fetchall()]


def update_body(
    connection: sqlite3.Connection,
    note_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
    now: str | None = None,
) -> NoteRow:
    """Edit a note in place.

    ⭐ **An edit restarts the recall schedule** (spec 028). A card is immutable, so
    its schedule can only move forward. A note is not, and that breaks an assumption
    the card queue never had to make: FSRS stability would stay attached to text
    that no longer exists, and the note would resurface months later asking the
    reader to recall something they have never read. So an edit rebuilds the FSRS
    card — due now, stability nothing — and appends a ``reset`` row. Earlier reviews
    are untouched; the history is append-only.

    A note that is **not** on the queue causes no reset row and no schedule write:
    most notes never are, and the common path must not pay for the interesting one.

    ⭐ **Unlike `cards`, a note is mutable and does not grow an event stream.**
    Cards are append-only because a claim you later retract must leave a trace —
    that is the anti-hindsight mechanism, and it is not up for reuse. A note is
    the reader's own working text; demanding an event per keystroke would bury
    it. `created_at` never moves, so "我什么时候想到这个" stays answerable.
    """
    require_open_transaction(connection, operation="notes.update_body")
    current = get_by_id(connection, note_id)

    new_title = current.note.title if title is None else title
    new_body = current.note.body if body is None else body
    # Reuse the draft validator so a note cannot be edited into a state that
    # `create` would have refused.
    validate_draft(NoteDraft(title=new_title, body=new_body))

    stamp = now if now is not None else utc_millis()
    connection.execute(_UPDATE_NOTE, (new_title, new_body, stamp, note_id))

    # The seam. `update_body` runs inside the caller's transaction, and so does
    # `reset_on_edit`, so the new text and the restarted schedule commit together:
    # a queue that says 「come back now」 while the text is still the old one would be
    # the same lie in a different order.
    # ⭐ The moment is **handed through**, not left to the wall clock.
    # `update_body` takes `now` as a string stamp and `reset_on_edit` wants a
    # datetime, and the first version of this call passed neither — so the reset
    # stamped itself with whatever time the test happened to run. In production
    # that is right by accident; in a test it makes the reset's position in the
    # history unknowable. An injected `now` that the code it calls ignores is not
    # an injected `now`.
    note_recall.reset_on_edit(
        connection,
        note_id,
        now=datetime.fromisoformat(stamp.replace("Z", "+00:00")),
    )

    return get_by_id(connection, note_id)


def add_tag(connection: sqlite3.Connection, note_id: str, tag: str) -> None:
    require_open_transaction(connection, operation="notes.add_tag")
    get_by_id(connection, note_id)
    connection.execute(_INSERT_TAG, (note_id, validate_tag(tag)))


def remove_tag(connection: sqlite3.Connection, note_id: str, tag: str) -> None:
    require_open_transaction(connection, operation="notes.remove_tag")
    get_by_id(connection, note_id)
    connection.execute(_DELETE_TAG, (note_id, validate_tag(tag)))


def add_link(connection: sqlite3.Connection, note_id: str, link: Link) -> None:
    require_open_transaction(connection, operation="notes.add_link")
    get_by_id(connection, note_id)
    if link.to_kind is LinkKind.NOTE and link.to_id == note_id:
        raise NoteLinkSelfError("一条笔记不能链接到自己。")
    if not link_targets_exist(connection, link):
        raise NoteLinkTargetUnknownError(
            f"链接目标不存在：{link.to_kind.value}/{link.to_id}"
        )
    stamp = utc_millis()
    connection.execute(
        _INSERT_LINK, (note_id, link.to_kind.value, link.to_id, stamp)
    )


def link_targets_exist(connection: sqlite3.Connection, link: Link) -> bool:
    """Whether the link's target is really there.

    ⭐ The schema cannot do this — `note_links.to_id` points into five tables and
    SQLite has no polymorphic foreign key. So the table would happily hold a dead
    reference, and "这条笔记指向的东西没了" would only surface as a blank space in
    the UI much later. This is the check, and the test suite pins it.

    An `instruments` target is matched on ``market|code`` because that table's
    primary key is the pair, not a single id.

    ⭐ And the table is checked for existence first. `LESSON` is a declared kind
    whose table does not exist until J5 lands, so querying it would raise
    ``OperationalError: no such table`` — which the first draft of this function
    did, because its own docstring claimed it "returns False for it". **A
    documented behaviour that the code does not have is worse than an absent
    one**, because a caller is entitled to rely on it.
    """
    table = _LINK_TARGET_TABLE.get(link.to_kind)
    if table is None:
        return False

    present = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if present is None:
        return False

    if link.to_kind is LinkKind.INSTRUMENT:
        row = connection.execute(
            "SELECT 1 FROM instruments WHERE market || '|' || code = ?",
            (link.to_id,),
        ).fetchone()
        return row is not None
    row = connection.execute(
        f"SELECT 1 FROM {table} WHERE id = ?",  # noqa: S608 - table from a closed map
        (link.to_id,),
    ).fetchone()
    return row is not None


def backlinks_for(connection: sqlite3.Connection, kind: LinkKind, target_id: str) -> list[str]:
    """Which notes point at this thing.

    ⭐ This is the function that makes the vault a knowledge system rather than a
    folder. `references/research/02` is explicit that every notes app links
    「笔记 ↔ 笔记」 and that is not a differentiator; the point is being able to
    ask "what refers to this card" and get an answer.
    """
    return [
        r["from_note_id"]
        for r in connection.execute(
            _SELECT_BACKLINKS, (kind.value, target_id)
        ).fetchall()
    ]


# ── search (spec 027) ───────────────────────────────────────────────────────

#: The trigram tokenizer indexes **overlapping 3-character sequences**, so a
#: query shorter than this cannot match anything. Measured, not assumed:
#:
#: ```text
#:   2 chars  MATCH '利率'   -> 0 hits
#:   2 chars  MATCH '白酒'   -> 0 hits
#:   3 chars  MATCH '现金流' -> 1 hit
#: ```
#:
#: And two characters is what this domain searches for most: 「利率」「白酒」「估值」
#: 「宏观」「渠道」 are all two characters. So the floor is not a limitation to
#: document — it is a boundary this function routes around.
MIN_FTS_CHARS = 3

_SELECT_BY_FTS = """
SELECT n.id, n.title, n.body, n.as_of, n.created_at, n.updated_at
FROM notes_fts AS f
JOIN notes AS n ON n.id = f.note_id
WHERE notes_fts MATCH ?
ORDER BY n.updated_at DESC, n.id DESC
"""

_SELECT_BY_SUBSTRING = """
SELECT n.id, n.title, n.body, n.as_of, n.created_at, n.updated_at
FROM notes AS n
WHERE instr(n.title, ?) > 0 OR instr(n.body, ?) > 0
ORDER BY n.updated_at DESC, n.id DESC
"""


def fts_pattern(user: str) -> str:
    """Quote a user string so FTS5 reads it as **text**, not as a query.

    ⭐ FTS5 has its own query language: `"` opens a phrase, `*` is a prefix
    operator, `NEAR` / `AND` / `OR` are operators, `-` negates. Passed raw, a
    reader who types any of them gets a **SQLite syntax error** — not an empty
    result, not a wrong result, an error that looks like the app is broken.

    Measured across the whole hostile set (`"`, `*`, `NEAR(a b)`, `-x`, `AND`,
    `OR`, `NEAR`): all treated as text, and real text still findable — including a
    body that itself contains a `"` character. Quoting is `"` + doubled inner
    quotes, which is FTS5's own escaping rule.
    """
    return '"' + user.replace('"', '""') + '"'


def search(connection: sqlite3.Connection, query: str) -> list[NoteRow]:
    """Find notes by text, newest edit first.

    Two paths, and the boundary between them is **measured behaviour**, not taste:

    | query length | path | why |
    |---|---|---|
    | ≥ `MIN_FTS_CHARS` | `notes_fts MATCH` | indexed, so it does not degrade linearly |
    | < `MIN_FTS_CHARS` | `instr()` | trigram cannot match 2 characters |

    ⭐ **Search filters; it does not re-order.** Both paths carry the same
    `ORDER BY updated_at DESC, id DESC` as `list_all`. `bm25()` is available
    (verified) and deliberately unused: relevance-sorting would make the same
    notes appear in a different order depending on whether a query was typed, and
    the value of a notes list is 「我最近写了什么」 rather than 「哪条最匹配」.

    ⭐ **The short path uses `instr`, not `LIKE`.** `LIKE` carries wildcard
    semantics, and a reader who types `%` into a two-character search would get
    **every note in the vault** — measured: `LIKE '%%%'` returns 4 of 4 rows where
    `instr` returns 1. `instr` is a pure substring test with no wildcards at all,
    so the failure mode is removed rather than escaped. (spec 026's mutation check
    found the same hole in the tag filter; there the fix was a test, and here the
    shape changed so the test could not be forgotten.)

    An empty or whitespace-only query is **not a search** — it returns the whole
    vault in list order, so clearing the box is the same as never having typed.

    ⚠️ The early return below is a **clarity and cost** branch, not a behaviour
    one. ``instr(x, '')`` returns 1 in SQLite (measured), so the substring path
    with an empty needle already matches every row in the same order — deleting
    the branch changes nothing a caller can observe, and a mutation check
    confirmed it by staying green. It is kept because it says what is meant and
    skips a pointless scan, and it is recorded here so that nobody writes a test
    for a difference that does not exist.
    """
    cleaned = query.strip()
    if not cleaned:
        return list_all(connection)

    if len(cleaned) >= MIN_FTS_CHARS:
        rows = connection.execute(_SELECT_BY_FTS, (fts_pattern(cleaned),)).fetchall()
    else:
        rows = connection.execute(
            _SELECT_BY_SUBSTRING, (cleaned, cleaned)
        ).fetchall()
    return _hydrate(connection, list(rows))
