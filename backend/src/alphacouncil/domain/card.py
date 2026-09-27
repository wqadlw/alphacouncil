"""Knowledge cards domain model — the minimum atomic unit of the knowledge layer (K1).

In AlphaCouncil, a card is not a generic note. It is:
    "A statement you are willing to sign your name to, with traceable provenance."

Rules enforced here and mirrored in schema CHECK constraints:
1. Provenance Rule (red line 4):
   - ``source_url`` is required and must begin with http:// or https://.
   - ``source_title`` is required and not blank.
   - ``captured_at`` is the server UTC millisecond timestamp when the card was recorded.
2. Claim categorization (ADR-0021):
   - ``supporting``: reasons supporting a thesis or conviction.
   - ``challenging``: counter-evidence resisting confirmation bias.
   - ``neutral``: verifiable objective context or reference fact.
3. Three input channels & AI isolation (ADR-0022 / red line 15):
   - ``user_written``: authored or verified by human.
   - ``extracted``: deterministic extraction from filings/reports.
   - ``ai_generated``: candidate generation. Must stay explicitly flagged until verified.
4. Priority & Status:
   - ``priority``: 1 to 5. Default 3.
   - ``status``: ``active`` or ``converged``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from urllib.parse import urlparse

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import Symbol

__all__ = [
    "MAX_CONTENT_CHARS",
    "MAX_TITLE_CHARS",
    "Card",
    "CardAlreadyVerifiedError",
    "CardContentRequiredError",
    "CardDraft",
    "CardError",
    "CardNotFoundError",
    "CardOrigin",
    "CardPriorityInvalidError",
    "CardSourceTitleRequiredError",
    "CardSourceUrlRequiredError",
    "CardStatus",
    "CardTextTooLongError",
    "ClaimType",
    "build_card_draft",
]

MAX_CONTENT_CHARS = 1000
MAX_TITLE_CHARS = 255


class ClaimType(StrEnum):
    SUPPORTING = "supporting"
    CHALLENGING = "challenging"
    NEUTRAL = "neutral"


class CardOrigin(StrEnum):
    USER_WRITTEN = "user_written"
    EXTRACTED = "extracted"
    AI_GENERATED = "ai_generated"


class CardStatus(StrEnum):
    ACTIVE = "active"
    CONVERGED = "converged"


class CardError(ValueError):
    code: ErrorCode


class CardContentRequiredError(CardError):
    code = ErrorCode.CARD_CONTENT_REQUIRED


class CardSourceUrlRequiredError(CardError):
    code = ErrorCode.CARD_SOURCE_URL_REQUIRED


class CardSourceTitleRequiredError(CardError):
    code = ErrorCode.CARD_SOURCE_TITLE_REQUIRED


class CardTextTooLongError(CardError):
    code = ErrorCode.CARD_TEXT_TOO_LONG


class CardNotFoundError(CardError):
    code = ErrorCode.CARD_NOT_FOUND


class CardAlreadyVerifiedError(CardError):
    code = ErrorCode.CARD_ALREADY_VERIFIED


class CardPriorityInvalidError(CardError):
    code = ErrorCode.CARD_PRIORITY_INVALID


@dataclass(frozen=True, slots=True)
class CardDraft:
    content: str
    claim_type: ClaimType
    source_url: str
    source_title: str
    origin: CardOrigin
    priority: int
    status: CardStatus
    as_of: date | None = None
    symbols: tuple[Symbol, ...] = ()


@dataclass(frozen=True, slots=True)
class Card:
    id: str
    content: str
    claim_type: ClaimType
    source_url: str
    source_title: str
    captured_at: str
    as_of: date | None
    origin: CardOrigin
    priority: int
    status: CardStatus
    created_at: str
    symbols: tuple[Symbol, ...] = ()


def _validate_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise CardSourceUrlRequiredError("source_url is required")
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise CardSourceUrlRequiredError(f"invalid http/https URL: {cleaned!r}")
    return cleaned


def _validate_content(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        raise CardContentRequiredError("content is required")
    if len(cleaned) > MAX_CONTENT_CHARS:
        raise CardTextTooLongError(f"content exceeds {MAX_CONTENT_CHARS} chars")
    return cleaned


def _validate_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise CardSourceTitleRequiredError("source_title is required")
    if len(cleaned) > MAX_TITLE_CHARS:
        raise CardTextTooLongError(f"source_title exceeds {MAX_TITLE_CHARS} chars")
    return cleaned


def build_card_draft(
    *,
    content: str,
    claim_type: ClaimType,
    source_url: str,
    source_title: str,
    origin: CardOrigin = CardOrigin.USER_WRITTEN,
    priority: int = 3,
    status: CardStatus = CardStatus.ACTIVE,
    as_of: date | None = None,
    symbols: tuple[Symbol, ...] = (),
) -> CardDraft:
    if not (1 <= priority <= 5):
        raise CardPriorityInvalidError(f"priority must be 1..5, got {priority}")
    return CardDraft(
        content=_validate_content(content),
        claim_type=claim_type,
        source_url=_validate_url(source_url),
        source_title=_validate_title(source_title),
        origin=origin,
        priority=priority,
        status=status,
        as_of=as_of,
        symbols=symbols,
    )
