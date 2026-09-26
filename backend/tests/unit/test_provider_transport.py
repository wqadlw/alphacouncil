"""Transport-level provider tests, with the network stubbed.

Parsing is already covered against real payloads in ``test_market_data``. What
these tests pin down is everything *around* parsing: the unit and date formats
each source wants on the way out, the mandatory Sina referer, and — most
importantly — that each class of HTTP failure lands on the right one of the four
data states. Collapsing "blocked" into "unreachable" is how a source gets
hammered until the IP is banned.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

# Reuse the live captures verbatim — duplicating them would let the two files
# drift apart, and then neither would be proof of anything.
from test_market_data import (
    EASTMONEY_DAILY,
    SINA_REALTIME,
    TENCENT_DAILY,
    TENCENT_REALTIME,
)

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import DataStatus, Market, Symbol
from alphacouncil.providers.sources import (
    EastmoneyProvider,
    SinaProvider,
    TencentProvider,
)

TENCENT_URL = "https://qt.gtimg.cn/q=sh600519"
SINA_URL = "https://hq.sinajs.cn/list=sh600519"
EASTMONEY_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
TENCENT_DAILY_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def _moutai() -> Symbol:
    return Symbol(market=Market.SH, code="600519")


# --------------------------------------------------------------------------
# HTTP failure classes → data states
# --------------------------------------------------------------------------


class TestFailureClassification:
    """Each failure class must land on exactly one of the four states."""

    @respx.mock
    def test_a_403_is_blocked(self) -> None:
        """A refusal is not a transient fault and must not be retried."""
        respx.get(TENCENT_URL).mock(return_value=httpx.Response(403))

        result = TencentProvider().get_realtime(_moutai())

        assert result.status is DataStatus.ERROR
        assert result.error_code is ErrorCode.DATA_SOURCE_FORBIDDEN

    @respx.mock
    def test_a_429_is_also_blocked(self) -> None:
        respx.get(TENCENT_URL).mock(return_value=httpx.Response(429))

        result = TencentProvider().get_realtime(_moutai())

        assert result.error_code is ErrorCode.DATA_SOURCE_FORBIDDEN

    @respx.mock
    def test_a_server_error_is_unreachable_not_blocked(self) -> None:
        """A 500 is the source being broken, not the source refusing us."""
        respx.get(TENCENT_URL).mock(return_value=httpx.Response(500))

        result = TencentProvider().get_realtime(_moutai())

        assert result.status is DataStatus.ERROR
        assert result.error_code is ErrorCode.DATA_SOURCE_UNREACHABLE

    @respx.mock
    def test_a_connection_failure_is_unreachable(self) -> None:
        respx.get(TENCENT_URL).mock(side_effect=httpx.ConnectError("no route"))

        result = TencentProvider().get_realtime(_moutai())

        assert result.status is DataStatus.ERROR
        assert result.error_code is ErrorCode.DATA_SOURCE_UNREACHABLE
        # The exception class survives in ``detail`` so a bug report can name it.
        assert result.detail == "ConnectError"

    @respx.mock
    def test_a_malformed_payload_is_unavailable(self) -> None:
        """The source answered, but not in a shape we can trust.

        This is the fourth state: the value may exist, we just cannot verify it.
        Reporting it as an error would hide that the source is up.
        """
        respx.get(TENCENT_URL).mock(
            return_value=httpx.Response(200, content=b'v_sh600519="garbage";')
        )

        result = TencentProvider().get_realtime(_moutai())

        assert result.status is DataStatus.UNAVAILABLE
        assert result.reason is not None

    @respx.mock
    def test_a_symbol_missing_from_the_response_is_no_data(self) -> None:
        respx.get(TENCENT_URL).mock(
            return_value=httpx.Response(200, content=b'v_sh600519="";')
        )

        result = TencentProvider().get_realtime(_moutai())

        assert result.status is DataStatus.NO_DATA

    @respx.mock
    def test_a_good_response_is_ok(self) -> None:
        respx.get(TENCENT_URL).mock(
            return_value=httpx.Response(200, content=TENCENT_REALTIME.encode("gbk"))
        )

        result = TencentProvider().get_realtime(_moutai())

        assert result.status is DataStatus.OK
        assert result.value is not None
        assert result.value.price == pytest.approx(1237.00)


# --------------------------------------------------------------------------
# Outbound format: the boundary conversion rule
# --------------------------------------------------------------------------


class TestOutboundFormat:
    """Sources want different formats; callers must never see either."""

    @respx.mock
    def test_sina_sends_the_mandatory_referer(self) -> None:
        """Sina rejects requests without it — the header is functional, not decorative."""
        route = respx.get(SINA_URL).mock(
            return_value=httpx.Response(200, content=SINA_REALTIME.encode("gbk"))
        )

        SinaProvider().get_realtime(_moutai())

        assert route.calls[0].request.headers["Referer"] == "https://finance.sina.com.cn"

    @respx.mock
    def test_tencent_asks_for_dashed_dates_and_forward_adjustment(self) -> None:
        route = respx.get(url__startswith=TENCENT_DAILY_URL).mock(
            return_value=httpx.Response(200, text=TENCENT_DAILY)
        )

        TencentProvider().get_daily(_moutai(), start=date(2026, 9, 18), end=date(2026, 9, 26))

        param = route.calls[0].request.url.params["param"]
        assert param == "sh600519,day,2026-09-18,2026-09-26,320,qfq"

    @respx.mock
    def test_eastmoney_asks_for_compact_dates(self) -> None:
        """Same ``date`` object, different wire format. That is the point."""
        route = respx.get(EASTMONEY_URL).mock(
            return_value=httpx.Response(200, text=EASTMONEY_DAILY)
        )

        EastmoneyProvider().get_daily(_moutai(), start=date(2026, 9, 18), end=date(2026, 9, 26))

        params = route.calls[0].request.url.params
        assert params["beg"] == "20260918"
        assert params["end"] == "20260926"
        assert params["fqt"] == "1"

    @respx.mock
    def test_eastmoney_uses_the_shanghai_prefix_for_shanghai(self) -> None:
        route = respx.get(EASTMONEY_URL).mock(
            return_value=httpx.Response(200, text=EASTMONEY_DAILY)
        )

        EastmoneyProvider().get_daily(_moutai())

        assert route.calls[0].request.url.params["secid"] == "1.600519"

    @respx.mock
    def test_tencent_daily_returns_bars_without_turnover(self) -> None:
        respx.get(url__startswith=TENCENT_DAILY_URL).mock(
            return_value=httpx.Response(200, text=TENCENT_DAILY)
        )

        result = TencentProvider().get_daily(_moutai())

        assert result.status is DataStatus.OK
        assert result.value is not None
        assert len(result.value) == 5
        assert all(bar.amount is None for bar in result.value)


# --------------------------------------------------------------------------
# Router + real providers, end to end but offline
# --------------------------------------------------------------------------


class TestRouterWithRealProviders:
    """The degradation chain, exercised through the real provider classes."""

    @respx.mock
    def test_snapshots_survive_the_primary_source_being_blocked(self) -> None:
        """The whole point of two realtime sources: one can be refused."""
        respx.get(TENCENT_URL).mock(return_value=httpx.Response(403))
        respx.get(SINA_URL).mock(
            return_value=httpx.Response(200, content=SINA_REALTIME.encode("gbk"))
        )

        from alphacouncil.providers import MarketDataRouter

        router = MarketDataRouter([TencentProvider(), SinaProvider()])
        result = router.get_realtime(_moutai())

        assert result.status is DataStatus.OK
        assert result.source == "sina"
        assert result.value is not None
        assert result.value.price == pytest.approx(1237.00)

    @respx.mock
    def test_history_survives_eastmoney_being_unreachable(self) -> None:
        """Eastmoney is the richest history source and the most fragile one.

        When it drops out, the page must still draw a chart — with the honest
        consequence that turnover is missing.
        """
        respx.get(EASTMONEY_URL).mock(side_effect=httpx.ConnectError("blocked by proxy"))
        respx.get(url__startswith=TENCENT_DAILY_URL).mock(
            return_value=httpx.Response(200, text=TENCENT_DAILY)
        )

        from alphacouncil.providers import MarketDataRouter

        router = MarketDataRouter([EastmoneyProvider(), TencentProvider()])
        result = router.get_daily(_moutai(), start=date(2026, 9, 18), end=date(2026, 9, 26))

        assert result.status is DataStatus.OK
        assert result.source == "tencent"
        assert result.value is not None
        assert len(result.value) == 5
        assert all(bar.amount is None for bar in result.value)

    @respx.mock
    def test_when_every_source_fails_the_ui_gets_a_reason_not_a_crash(self) -> None:
        respx.get(TENCENT_URL).mock(side_effect=httpx.ConnectError("down"))
        respx.get(SINA_URL).mock(side_effect=httpx.ConnectError("down"))

        from alphacouncil.providers import MarketDataRouter

        router = MarketDataRouter([TencentProvider(), SinaProvider()])
        result = router.get_realtime(_moutai())

        assert result.status is DataStatus.ERROR
        assert result.error_code is not None
        assert result.source in {"tencent", "sina"}
