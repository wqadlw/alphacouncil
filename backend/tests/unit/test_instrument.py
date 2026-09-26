"""Ticker normalisation: the rules that stop a code becoming the wrong company.

Marked ``unit`` — no network, no database. Most cases here are *refusals*,
because that is where the value is: a test showing ``600519`` resolving proves
nothing about the rules that matter, and the failure this module guards against
does not raise — it returns another company's numbers, correctly formatted.

Each test names the ADR-0017 rule it holds, so that someone changing one can see
what else leans on it.
"""

from __future__ import annotations

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.domain.instrument import (
    TickerAmbiguousError,
    TickerError,
    TickerInvalidError,
    candidate_markets,
    parse_ticker,
)
from alphacouncil.models.market import AssetType, Market, Symbol

pytestmark = pytest.mark.unit


class TestTheAmbiguousSegment:
    """ADR-0017 rule 3: ``000xxx`` is ambiguous, not contradictory."""

    def test_a_bare_000_code_asks_instead_of_choosing(self) -> None:
        """``000001`` is the Shanghai Composite *and* Ping An Bank."""
        with pytest.raises(TickerAmbiguousError) as caught:
            parse_ticker("000001")

        assert caught.value.candidates == frozenset({Market.SH, Market.SZ})
        assert caught.value.code is ErrorCode.DATA_SOURCE_TICKER_AMBIGUOUS

    def test_the_two_readings_are_both_reachable(self) -> None:
        """The ambiguous code is real on both exchanges, so both must work."""
        assert parse_ticker("000001", market=Market.SH).market is Market.SH
        assert parse_ticker("000001", market=Market.SZ).market is Market.SZ

    def test_the_ambiguous_error_is_not_an_invalid_error(self) -> None:
        """A caller can tell "choose one" from "that is not a ticker"."""
        with pytest.raises(TickerAmbiguousError):
            parse_ticker("000001")
        assert issubclass(TickerAmbiguousError, TickerError)
        assert not issubclass(TickerAmbiguousError, TickerInvalidError)

    def test_the_affix_form_still_needs_no_choice(self) -> None:
        """``sh000001`` states the market, so nothing is ambiguous about it."""
        assert parse_ticker("sh000001").market is Market.SH
        assert parse_ticker("sz000001").market is Market.SZ


class TestSingleCandidateResolution:
    """ADR-0017 rule 2: resolve a lookup, never guess among candidates."""

    @pytest.mark.parametrize(
        ("ticker", "expected"),
        [
            ("600519", Market.SH),  # Shanghai main board
            ("601398", Market.SH),
            ("688981", Market.SH),  # STAR market
            ("300750", Market.SZ),  # ChiNext
            ("002594", Market.SZ),
            ("159915", Market.SZ),  # Shenzhen ETF
            ("510300", Market.SH),  # Shanghai ETF
            ("399001", Market.SZ),  # Shenzhen index
            ("430047", Market.BJ),
            ("920001", Market.BJ),
        ],
    )
    def test_a_code_that_admits_one_exchange_resolves(self, ticker: str, expected: Market) -> None:
        assert parse_ticker(ticker).market is expected

    def test_candidate_markets_reports_the_possibilities(self) -> None:
        assert candidate_markets("600519") == frozenset({Market.SH})
        assert candidate_markets("000001") == frozenset({Market.SH, Market.SZ})

    def test_an_unknown_range_is_unknown_rather_than_impossible(self) -> None:
        """Empty means "no rule covers this", not "this code is wrong".

        The distinction matters: a range added by a future release must not be
        rejected by a table written today.
        """
        assert candidate_markets("999999") == frozenset()

    def test_an_unknown_range_needs_an_explicit_market(self) -> None:
        with pytest.raises(TickerInvalidError):
            parse_ticker("204001")
        assert parse_ticker("204001", market=Market.SH).market is Market.SH

    def test_a_prefix_mapped_too_broadly_is_caught_here(self) -> None:
        """``204001`` is a Shanghai repo, not a Shenzhen B share.

        Regression test for the table row that was ``20`` before it was ``200``:
        a prefix covering more than it should would have resolved this to
        Shenzhen without a word.
        """
        assert candidate_markets("200001") == frozenset({Market.SZ})
        assert candidate_markets("204001") == frozenset()


class TestContradictions:
    """ADR-0017 rule 2: a stated market that the code cannot have is an error."""

    def test_a_contradicting_parameter_is_refused(self) -> None:
        with pytest.raises(TickerInvalidError):
            parse_ticker("600519", market=Market.SZ)

    def test_a_contradicting_affix_is_refused(self) -> None:
        with pytest.raises(TickerInvalidError):
            parse_ticker("sz600519")

    def test_an_affix_and_a_parameter_that_disagree_are_refused(self) -> None:
        with pytest.raises(TickerInvalidError):
            parse_ticker("600519.SH", market=Market.SZ)

    def test_an_affix_and_a_parameter_that_agree_are_fine(self) -> None:
        assert parse_ticker("600519.SH", market=Market.SH).market is Market.SH

    def test_prefix_and_suffix_together_are_refused(self) -> None:
        """ADR-0017 rule 4: pick one form. ``SH000001.SZ`` is not a ticker."""
        with pytest.raises(TickerInvalidError):
            parse_ticker("sh000001.SZ")

    def test_the_two_affix_case_is_diagnosed_not_merely_refused(self) -> None:
        """Removing this guard still refuses the string — the shape check
        catches it — so the guard's entire contribution is the diagnosis.

        Verified by mutation on 2026-09-26: deleting the guard left the test
        above green. Pinning the wording here is therefore pinning the feature
        rather than pinning prose: a user who wrote the market twice should be
        told that, not told their code is malformed.
        """
        with pytest.raises(TickerInvalidError) as caught:
            parse_ticker("sh000001.SZ")

        assert "twice" in str(caught.value)


class TestAnchoring:
    """ADR-0017 rule 4: match the whole string, never hunt for six digits."""

    @pytest.mark.parametrize(
        "raw",
        [
            "abc600519",  # digits after junk
            "600519x",  # digits before junk
            "6005199",  # seven digits
            "6005 19",  # a space inside
            "600-519",  # a separator inside
            "600519.XX",  # unknown exchange suffix
            "xx600519",  # the shape of the bug this guards
        ],
    )
    def test_six_digits_inside_a_longer_string_are_not_a_ticker(self, raw: str) -> None:
        with pytest.raises(TickerInvalidError):
            parse_ticker(raw)

    def test_full_width_digits_are_refused(self) -> None:
        """``\\d`` matches Unicode digits; ``[0-9]`` does not.

        Verified 2026-09-26: with ``\\d{6}`` this string is accepted, and
        pydantic's ``^\\d{6}$`` accepts it too, so a code no source recognises
        would reach the database looking entirely normal.
        """
        with pytest.raises(TickerInvalidError):
            parse_ticker("６００５１９")

    def test_full_width_digits_are_refused_even_with_a_stated_market(self) -> None:
        """The case above is caught twice over, which hides the rule.

        ``６００５１９`` matches no row in the segment table, so the
        unknown-range guard refuses it whether or not the digit pattern is
        ASCII-only — verified by mutation on 2026-09-26, when widening the
        pattern to ``\\d{6}`` left the test above still green. Supplying the
        market takes that guard out of the way, so only the digit pattern is
        left standing between the user and a ``Symbol`` no source can serve.
        """
        with pytest.raises(TickerInvalidError):
            parse_ticker("６００５１９", market=Market.SH)

    def test_a_case_folded_ascii_impostor_is_refused(self) -> None:
        """``ſh`` upper-cases to ``SH``, so ``IGNORECASE`` alone accepts it.

        Without ``re.ASCII`` the prefix matched and ``Market("ſh")`` raised a
        bare ``ValueError`` — an error with no code, which no caller can branch
        on and which the error-code gate would never see.
        """
        with pytest.raises(TickerInvalidError):
            parse_ticker("ſh600519")

    def test_empty_and_blank_are_refused(self) -> None:
        for raw in ("", "   ", "\t"):
            with pytest.raises(TickerInvalidError):
                parse_ticker(raw)

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        """Trimming is not the same as accepting junk."""
        assert parse_ticker("  600519  ").code == "600519"


class TestAffixForms:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("SH600519", Market.SH),
            ("Sh600519", Market.SH),
            ("sh600519", Market.SH),
            ("600519.sh", Market.SH),
            ("600519.SH", Market.SH),
            ("SZ300750", Market.SZ),
            ("300750.sz", Market.SZ),
            ("BJ430047", Market.BJ),
        ],
    )
    def test_every_affix_form_parses(self, raw: str, expected: Market) -> None:
        assert parse_ticker(raw).market is expected


class TestAssetTypeIsNeverInferred:
    """The code's prefix says nothing reliable about what the thing is."""

    def test_the_default_is_a_stock(self) -> None:
        assert parse_ticker("600519").asset_type is AssetType.STOCK

    def test_an_index_can_share_a_stock_range(self) -> None:
        """``000001`` is an index on Shanghai and a stock on Shenzhen.

        ``asset_type`` is carried explicitly, so nothing has to guess from the
        code which of the two the user meant.
        """
        index = parse_ticker("000001", market=Market.SH, asset_type=AssetType.INDEX)
        stock = parse_ticker("000001", market=Market.SZ, asset_type=AssetType.STOCK)
        assert index.asset_type is AssetType.INDEX
        assert stock.asset_type is AssetType.STOCK
        assert index != stock

    def test_an_etf_code_still_defaults_to_stock_without_being_asked(self) -> None:
        """Resolution is about the exchange only — it never implies a type."""
        assert parse_ticker("510300").asset_type is AssetType.STOCK


class TestTheResultIsAlwaysValid:
    def test_the_returned_symbol_passes_its_own_validation(self) -> None:
        """Whatever comes out could be constructed by hand, so callers can trust it."""
        symbol = parse_ticker("600519")
        assert isinstance(symbol, Symbol)
        assert Symbol(market=symbol.market, code=symbol.code) == symbol

    def test_every_failure_carries_a_registered_code(self) -> None:
        """A code that cannot be looked up cannot be reported or counted."""
        for raw, market in (("600519", Market.SZ), ("000001", None), ("nonsense", None)):
            with pytest.raises(TickerError) as caught:
                parse_ticker(raw, market=market)
            assert caught.value.code in set(ErrorCode)
