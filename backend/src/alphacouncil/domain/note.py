"""Notes — the other half of the knowledge layer (spec 026).

## Why this module exists at all

The knowledge layer had exactly one table, `cards`, and every row in it was
pinned by three constraints: `source_url` required and http(s), `source_title`
required, and — in the frontend — a hard-coded single instrument. So these could
not be recorded at all:

- 「流动性收紧时周期股先跌」 — a macro view. No instrument, no source.
- 「我的估值框架是这样」 — a method. Same.
- 「我第 3 次因为只看 PE 错过」 — a lesson. Same.
- A reading note. Same.

Which means the product could **review** knowledge but not **record** it. It had
a queue and no vault. That is the literal meaning of the owner's complaint, and
the measurement behind it was four zeros: no note concept, no FTS, no tags, no
Markdown anywhere in the backend.

## ⭐ The provenance rule is not relaxed. It is given a proper container.

`基础功能打磨与AI桥接.md` §2.1 says it outright: 「**不是**笔记。笔记可以没有来源；
**卡片必须有**」. Cards still require a source here, untouched. Loosening it
would make "I thought I remembered this, but I was quoting something I never
read" undetectable — and that is precisely the failure this product exists to
prevent.

So a note is not a card with the source removed. It is a different thing:

| | card | note |
|---|---|---|
| is | a claim you will sign your name to | something you wrote down |
| source | **required** | may be absent |
| instrument | attached | may be absent |
| length | ≤ 1000 chars, "超过 3 行不算卡片，算文章" | an article is the point |
| stance | supporting / challenging / neutral | none — a note is not a claim |
| lifecycle | verify / converge (K2) | none — convergence is a verdict on a claim |

The last two rows are why this is a separate table rather than a nullable
`cards` row: `claim_type` and `status` would have to become nullable, and every
existing read would have to handle three-valued logic. Nullable columns are how
tables rot.

## What a note is *not* allowed to be

**Not a second card store.** There is no `priority` here. Priority orders work;
a vault is a body of writing, and ranking it by an integer the user set months
ago is the "list I have to feel something about" failure the product's red lines
already reject elsewhere.

**Not un-searchable.** Tags and the link skeleton are in the schema rather than
deferred, because a note you cannot find again is a note you have lost. Full-text
search is the next round (spec 026 §6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from alphacouncil.core.error_codes import ErrorCode

# `Symbol` lives in `models.market`, not `domain.instrument` — the first draft
# imported it from the latter and mypy caught it, because `domain/instrument.py`
# re-exports it for the API layer without listing it in its own `__all__`.
# An instrument is a *value* type, so its home is the models package.
from alphacouncil.models.market import Symbol

__all__ = [
    "MAX_BODY_CHARS",
    "MAX_TAG_CHARS",
    "MAX_TITLE_CHARS",
    "Link",
    "LinkKind",
    "Note",
    "NoteBodyBlankError",
    "NoteDraft",
    "NoteError",
    "NoteIdExhaustedError",
    "NoteLinkSelfError",
    "NoteLinkTargetUnknownError",
    "NoteNotFoundError",
    "NoteRow",
    "NoteTagInvalidError",
    "NoteTextTooLongError",
    "NoteTitleRequiredError",
    "NoteTitleTooLongError",
    "validate_draft",
    "validate_tag",
]

#: A size guard against a pasted file, not a style rule. See the module docstring.
MAX_BODY_CHARS = 200_000
MAX_TITLE_CHARS = 200
MAX_TAG_CHARS = 40


class LinkKind(StrEnum):
    """What a note may point at.

    ⭐ `LESSON` is in here with nothing behind it yet — J5 教训转卡 is the next
    round. It is listed **now** so the enum, the migration's CHECK, and the docs
    agree from the start: a link table whose kinds are extended later needs a
    migration, and a link kind that appears with its first row is a link kind
    that appears without a decision.
    """

    NOTE = "note"
    CARD = "card"
    DECISION = "decision"
    INSTRUMENT = "instrument"
    LESSON = "lesson"


class NoteError(ValueError):
    """Base for every note-domain refusal."""

    code: ErrorCode


class NoteTitleRequiredError(NoteError):
    code = ErrorCode.NOTE_TITLE_REQUIRED


class NoteTitleTooLongError(NoteError):
    code = ErrorCode.NOTE_TITLE_TOO_LONG


class NoteBodyBlankError(NoteError):
    code = ErrorCode.NOTE_BODY_BLANK


class NoteTextTooLongError(NoteError):
    code = ErrorCode.NOTE_TEXT_TOO_LONG


class NoteNotFoundError(NoteError):
    code = ErrorCode.NOTE_NOT_FOUND


class NoteTagInvalidError(NoteError):
    code = ErrorCode.NOTE_TAG_INVALID


class NoteLinkSelfError(NoteError):
    code = ErrorCode.NOTE_LINK_SELF


class NoteLinkTargetUnknownError(NoteError):
    """The target id does not exist in the table its kind names.

    ⭐ This is the one constraint the schema cannot enforce, and saying so is the
    point of having the code: `note_links.to_id` deliberately carries **no foreign
    key**, because it points into five different tables and SQLite cannot
    constrain a polymorphic reference. A dead link is therefore possible at the
    SQL level, and this error is what stops one being written.

    It also covers the case where the *table* does not exist yet — `LESSON` is a
    declared kind with no table behind it until J5 教训转卡 lands. That is the
    same refusal seen from the other side: a link that cannot be resolved is a
    link that must not be written.
    """

    code = ErrorCode.NOTE_LINK_TARGET_UNKNOWN


class NoteIdExhaustedError(NoteError):
    """No free id within the collision window.

    Effectively unreachable — it needs a thousand notes in one millisecond — but
    it is named rather than allowed to surface as a driver error, because
    "the write failed" is not something the reader can act on.
    """

    code = ErrorCode.NOTE_NOT_FOUND


@dataclass(frozen=True, slots=True)
class NoteDraft:
    """What the caller supplies when writing a note.

    ⭐ `body` is stored **verbatim**. No trimming, no newline normalisation, no
    Markdown re-serialisation. The first two would silently rewrite the user's
    text; the third would reformat their notes behind their back, and the
    Markdown is the part they are most attached to.
    """

    title: str
    body: str
    tags: tuple[str, ...] = ()
    links: tuple[Link, ...] = ()
    symbols: tuple[Symbol, ...] = ()
    as_of: date | None = None


@dataclass(frozen=True, slots=True)
class Link:
    """One outgoing reference."""

    to_kind: LinkKind
    to_id: str


@dataclass(frozen=True, slots=True)
class Note:
    """A stored note."""

    id: str
    title: str
    body: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class NoteRow:
    """A note with its relationships — what the API returns."""

    note: Note
    tags: tuple[str, ...] = ()
    links: tuple[Link, ...] = ()
    symbols: tuple[Symbol, ...] = ()
    as_of: date | None = None


def validate_draft(draft: NoteDraft) -> None:
    """Refuse a draft the domain will not accept.

    Called by the repository before anything is written, so a bad note never
    reaches a transaction. The schema enforces the same shapes as CHECKs — this
    exists so the refusal arrives as *our* error code with our message, rather
    than as a raw `IntegrityError` from the driver.
    """
    if not draft.title.strip():
        raise NoteTitleRequiredError("笔记需要一个标题：空标题的笔记在列表里认不出来。")
    if len(draft.title) > MAX_TITLE_CHARS:
        raise NoteTitleTooLongError(f"标题超过 {MAX_TITLE_CHARS} 个字符。")
    if not draft.body.strip():
        raise NoteBodyBlankError("笔记正文不能是空的。")
    if len(draft.body) > MAX_BODY_CHARS:
        raise NoteTextTooLongError(f"正文超过 {MAX_BODY_CHARS} 个字符。")
    for tag in draft.tags:
        validate_tag(tag)


def validate_tag(tag: str) -> str:
    """One tag, normalised by trimming and nothing else.

    ⭐ Trimming is the **only** normalisation, and it is deliberate. Tags are set
    members: `「 宏观 」` and `「宏观」` must be the same tag or filtering silently
    splits in two. But nothing else is touched — no case folding (a Chinese tag
    has no case, and lowercasing a Latin one would merge `PE` with `pe` behind
    the user's back), no separator rewriting, no truncation.
    """
    cleaned = tag.strip()
    if not cleaned:
        raise NoteTagInvalidError("标签不能是空的。")
    if len(cleaned) > MAX_TAG_CHARS:
        raise NoteTagInvalidError(f"标签超过 {MAX_TAG_CHARS} 个字符。")
    # A comma is what the schema forbids, because a comma-joined column is the
    # shape this table exists to avoid. Refusing it here means the error names
    # the reason instead of surfacing as an IntegrityError.
    if "," in cleaned:
        raise NoteTagInvalidError(
            "标签里不能有逗号 —— 逗号会让「宏观」和「宏观债」互相命中。"
        )
    return cleaned
