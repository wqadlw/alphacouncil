"""Ticker normalisation — the single place a string becomes an instrument.

ADR-0017 puts three rules here, and each one is easy to state and easy to get
wrong:

1. **An instrument's identity is ``(market, code)``, never ``code`` alone.**
   ``000001`` is the Shanghai Composite on one exchange and Ping An Bank on the
   other. The failure this prevents does not raise: it returns another company's
   numbers, formatted correctly.
2. **The market is never invented from the code.** It comes from explicit input
   or from the data source. Inference exists to *check* a stated market
   (contradiction -> error), and — only where the code can sit on exactly one
   exchange — to *resolve* an under-specified input.
3. **``000xxx`` is ambiguous, not contradictory.** ``sh000001`` and ``sz000001``
   are both real, so the input is incomplete rather than wrong; the user is
   asked which one they mean.

Rules 2 and 3 look like they disagree, so the boundary is worth stating: rule 2
forbids *guessing* — choosing among several candidates — while rule 3 hands the
ambiguous segment to the user. Together they read as: resolve when the code
admits exactly one exchange, because that is a lookup rather than a guess;
refuse when it admits more than one. ``.ai/error-codes.md`` §2.1 fixes the same
intent from the user's side — ``600519`` is listed as a *valid* input form, and
only ``000001`` gets "choose a market".
"""

from __future__ import annotations

import re

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import AssetType, Market, Symbol

__all__ = [
    "AssetTypeConflictError",
    "InstrumentError",
    "TickerAmbiguousError",
    "TickerError",
    "TickerInvalidError",
    "candidate_markets",
    "parse_ticker",
]

#: A bare code is exactly six ASCII digits, matched against the **whole**
#: remainder. Two details are load-bearing:
#:
#: * ``re.search`` would happily find six digits inside ``600519xx`` or
#:   ``prefix-600519-suffix`` and accept garbage; anchoring is the difference
#:   between parsing a ticker and hunting for something that looks like one.
#: * ``[0-9]`` rather than ``\d``, because Python's ``\d`` matches any Unicode
#:   decimal digit — verified 2026-09-26, ``\d{6}`` accepts ``600519`` typed in
#:   full-width characters (U+FF10 .. U+FF19). That would sail through into a
#:   ``Symbol`` (pydantic's ``^\d{6}$`` is equally Unicode-loose) and reach a
#:   data source that has never heard of it. ``re.ASCII`` on the affix patterns
#:   closes the same hole from the other side: ``IGNORECASE`` alone lets U+017F
#:   (LATIN SMALL LETTER LONG S) stand in for ``s``, so a string that reads as
#:   ``sh600519`` would parse, and ``Market`` would then raise a bare
#:   ``ValueError`` carrying no error code.
CODE_PATTERN = re.compile(r"[0-9]{6}")

_AFFIX = r"(sh|sz|bj)"
_PREFIX = re.compile(rf"^{_AFFIX}", re.IGNORECASE | re.ASCII)
_SUFFIX = re.compile(rf"\.{_AFFIX}$", re.IGNORECASE | re.ASCII)

_SH = frozenset({Market.SH})
_SZ = frozenset({Market.SZ})
_BJ = frozenset({Market.BJ})
_SH_OR_SZ = frozenset({Market.SH, Market.SZ})

#: Which exchanges a bare code can belong to, by leading digits.
#:
#: Granularity is mostly two digits, three where two would collide — ``000``
#: because the Shanghai index range shares it with Shenzhen stocks, and ``200``
#: because ``204xxx`` is a Shanghai repo rather than a Shenzhen B share. The
#: rule is "as coarse as is still correct", not "as coarse as possible", because
#: being wrong here costs in both directions: a prefix mapped too broadly fails
#: to notice a contradiction, one mapped too narrowly rejects a valid code.
#:
#: This table is a **possibility set**, never a decision. It exists so a stated
#: market can be checked, and so a single-candidate code can be resolved; a code
#: matching no row is "unknown" and requires an explicit market rather than a
#: guess. Bonds, repos and warrants are absent on purpose — they are outside the
#: asset types this product covers, so they take the explicit-market path.
_CODE_MARKETS: tuple[tuple[str, frozenset[Market]], ...] = (
    ("000", _SH_OR_SZ),  # the ambiguous segment — Shanghai index / Shenzhen stock
    ("001", _SZ),
    ("002", _SZ),
    ("003", _SZ),
    ("004", _SZ),
    ("15", _SZ),  # Shenzhen funds and ETFs
    ("16", _SZ),
    ("18", _SZ),
    ("200", _SZ),  # Shenzhen B shares (not 20 — 204xxx is a Shanghai repo)
    ("30", _SZ),  # ChiNext
    ("39", _SZ),  # Shenzhen indices
    ("43", _BJ),
    ("51", _SH),  # Shanghai funds and ETFs
    ("52", _SH),
    ("56", _SH),
    ("58", _SH),
    ("60", _SH),  # Shanghai main board
    ("68", _SH),  # STAR market
    ("83", _BJ),
    ("87", _BJ),
    ("88", _BJ),
    ("89", _BJ),
    ("90", _SH),  # Shanghai B shares
    ("92", _BJ),
)

#: Longest prefix first, so ``000`` is tested before any two-digit rule could
#: ever shadow it. Sorting here rather than relying on the literal order above
#: means adding a row cannot silently change how an existing code resolves.
_CODE_MARKETS_BY_LENGTH = tuple(sorted(_CODE_MARKETS, key=lambda row: -len(row[0])))


class InstrumentError(ValueError):
    """A problem with an instrument as a thing, not with a ticker string.

    The base exists so the API can install one handler for "the user asked for
    an instrument we cannot give them" instead of one per subclass.
    """

    code: ErrorCode = ErrorCode.INSTRUMENT_ASSET_TYPE_CONFLICT


class TickerError(InstrumentError):
    """A ticker string could not be turned into an instrument."""

    code = ErrorCode.DATA_SOURCE_TICKER_INVALID


class TickerInvalidError(TickerError):
    """Malformed input, or an explicit market that contradicts the code."""

    code = ErrorCode.DATA_SOURCE_TICKER_INVALID


class AssetTypeConflictError(InstrumentError):
    """The same ``(market, code)`` was asserted with two different types.

    Raised by the instrument repository, not by :func:`parse_ticker`: the string
    parses fine, and it is the *stored* row that disagrees. It lives here because
    "this instrument is a stock" is a statement about the instrument, and storage
    only happens to be where the previous statement is kept.
    """

    code = ErrorCode.INSTRUMENT_ASSET_TYPE_CONFLICT


class TickerAmbiguousError(TickerError):
    """The code is real on more than one exchange; the user must choose.

    ``candidates`` is carried on the exception rather than only inside the
    message, so the API can render the choice from data instead of parsing
    English out of a string.
    """

    code = ErrorCode.DATA_SOURCE_TICKER_AMBIGUOUS

    def __init__(self, ticker: str, candidates: frozenset[Market]) -> None:
        self.ticker = ticker
        self.candidates = candidates
        super().__init__(f"{ticker} exists on {_joined(candidates)} — choose one")


def _joined(markets: frozenset[Market]) -> str:
    """Render a market set the same way in every message."""
    return " / ".join(sorted(market.value for market in markets))


def candidate_markets(code: str) -> frozenset[Market]:
    """Every exchange a bare code could belong to.

    Args:
        code: Six digits. Not validated here — a code that matches no row simply
            returns nothing.

    Returns:
        The possible markets, or an empty set when the code falls outside the
        ranges this build knows. **Empty means unknown, not impossible** — a
        caller must then require an explicit market rather than conclude the
        code is wrong, because a range added by a future release would otherwise
        be rejected by code that predates it.
    """
    for prefix, markets in _CODE_MARKETS_BY_LENGTH:
        if code.startswith(prefix):
            return markets
    return frozenset()


def parse_ticker(
    raw: str,
    *,
    market: Market | None = None,
    asset_type: AssetType = AssetType.STOCK,
) -> Symbol:
    """Turn a ticker string into a :class:`Symbol`.

    Accepted forms — the market may also arrive separately via ``market``::

        600519        # resolved: only the Shanghai exchange uses this range
        600519.SH     # explicit suffix
        sh600519      # explicit prefix
        000001        # ambiguous -> TickerAmbiguousError, ask the user

    Args:
        raw: The text to parse. Typed ``str`` and not re-checked at run time:
            a caller that passes something else is a type error, which is a
            cheaper place to catch it than here (constitution 0.2 — a rule
            belongs as far down the ladder as it will go, and the type checker
            sits below this function).
        market: A market stated elsewhere, e.g. by a form's selector.
        asset_type: Stored alongside the code. Never inferred from it — the
            prefix of a code says nothing reliable about what the thing is.

    Returns:
        A :class:`Symbol` with a resolved market.

    Raises:
        TickerInvalidError: The text is not a ticker, states two markets that
            disagree, or states a market the code is not listed on.
        TickerAmbiguousError: The code is real on several exchanges and no
            market was stated.
    """
    text = raw.strip()
    if not text:
        msg = "ticker is empty"
        raise TickerInvalidError(msg)

    prefix = _PREFIX.match(text)
    suffix = _SUFFIX.search(text)
    if prefix and suffix:
        msg = (
            f"{raw!r} states the market twice ({prefix.group(1)} and "
            f"{suffix.group(1)}) — use one form, e.g. sh600519 or 600519.SH"
        )
        raise TickerInvalidError(msg)

    affix = prefix or suffix
    if prefix:
        text = text[prefix.end() :]
    elif suffix:
        text = text[: suffix.start()]
    stated = Market(affix.group(1).lower()) if affix else None

    if not CODE_PATTERN.fullmatch(text):
        msg = f"{raw!r} is not a six-digit code (optionally with sh/sz/bj)"
        raise TickerInvalidError(msg)
    return _resolve(raw, text, stated, market, asset_type)


def _resolve(
    raw: str,
    code: str,
    embedded: Market | None,
    requested: Market | None,
    asset_type: AssetType,
) -> Symbol:
    """Decide the market, refusing to guess."""
    if embedded is not None and requested is not None and embedded is not requested:
        msg = (
            f"{raw!r} says {embedded.value} but the request says {requested.value} "
            "— the market must come from one place"
        )
        raise TickerInvalidError(msg)
    stated = embedded if embedded is not None else requested

    candidates = candidate_markets(code)
    if stated is not None:
        if candidates and stated not in candidates:
            msg = f"{raw!r}: {code} is not listed on {stated.value} (only {_joined(candidates)})"
            raise TickerInvalidError(msg)
        return Symbol(market=stated, code=code, asset_type=asset_type)

    if not candidates:
        msg = (
            f"{raw!r}: {code} is outside the code ranges this build knows, so its "
            "market cannot be derived — pass one explicitly"
        )
        raise TickerInvalidError(msg)
    if len(candidates) == 1:
        return Symbol(market=next(iter(candidates)), code=code, asset_type=asset_type)
    raise TickerAmbiguousError(raw, candidates)
