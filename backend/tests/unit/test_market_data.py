"""Data-boundary tests: parsing, capability routing, and degradation.

Marked ``unit`` — nothing here touches the network. The Tencent and Sina
payloads below are **verbatim captures from 2026-09-26** (``sh600519``, 中秋
休市前夕), so a parser change that breaks on real data fails here instead of in
production.

⚠️ The Eastmoney fixture is **not** a live capture: this sandbox's egress proxy
drops connections to ``push2his.eastmoney.com`` (``server closed abruptly``),
verified three times. That fixture is built from the documented response shape
and is labelled as such wherever it is used.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.models.market import (
    DataResult,
    DataStatus,
    Market,
    Quote,
    RealtimeQuote,
    Symbol,
)
from alphacouncil.providers.base import (
    Dataset,
    ProviderCapabilities,
    ProviderEmptyError,
    ProviderProtocolError,
)
from alphacouncil.providers.cache import MemoryCache
from alphacouncil.providers.router import MarketDataRouter
from alphacouncil.providers.sources import (
    EastmoneyProvider,
    SinaProvider,
    TencentProvider,
)

STAMP = datetime(2026, 9, 26, 16, 30, 0)

# --------------------------------------------------------------------------
# Live captures (2026-09-26)
# --------------------------------------------------------------------------

TENCENT_REALTIME = (
    'v_sh600519="1~贵州茅台~600519~1237.00~1251.24~1250.01~31239~13918~17321~'
    "1237.00~13~1236.95~4~1236.85~1~1236.83~1~1236.51~2~1237.05~1~1237.50~1~"
    "1237.70~1~1237.90~1~1237.97~1~~20260924161444~-14.24~-1.14~1256.13~1231.05~"
    "1237.00/31239/3867310920~31239~386731~0.25~18.99~~1256.13~1231.05~2.00~"
    "15463.51~15463.51~6.15~1376.36~1126.12~1.27~16~1237.96~17.37~18.78~~~0.07~"
    '386731.0920~74.2200~6~   A~GP-A~-8.31~-2.37~4.21~32.41~27.30~1539.98~'
    '1151.01~-3.75~-4.28~2.83~1250081601~1250081601~61.54~-9.97~1250081601~~~'
    '-11.01~-0.09~~CNY~0~___D__F__N~1238.05~-39~";'
)

SINA_REALTIME = (
    'var hq_str_sh600519="贵州茅台,1250.010,1251.240,1237.000,1256.130,1231.050,'
    "1237.000,1237.050,3123935,3867310920.000,1337,1237.000,400,1236.950,100,"
    "1236.850,100,1236.830,200,1236.510,100,1237.050,100,1237.500,100,1237.700,"
    '100,1237.900,100,1237.970,2026-09-24,15:34:59,00,D|600|742200.00";'
)

TENCENT_DAILY = json.dumps(
    {
        "code": 0,
        "msg": "",
        "data": {
            "sh600519": {
                "qfqday": [
                    ["2026-09-18", "1262.990", "1257.120", "1265.880", "1256.100", "24891.000"],
                    ["2026-09-21", "1259.000", "1252.570", "1259.950", "1250.800", "25017.000"],
                    ["2026-09-22", "1252.150", "1253.800", "1265.880", "1248.100", "24573.000"],
                    ["2026-09-23", "1255.030", "1251.240", "1271.500", "1250.890", "30981.000"],
                    ["2026-09-24", "1250.010", "1237.000", "1256.130", "1231.050", "31239.000"],
                ],
                "qt": {"sh600519": ["1", "贵州茅台", "600519"]},
                "prec": "31.390",
                "version": "18",
            }
        },
    }
)

# ⚠️ Constructed from the documented shape, NOT a live capture — Eastmoney is
# unreachable from this sandbox. Replace with a real payload once reachable.
EASTMONEY_DAILY = json.dumps(
    {
        "rc": 0,
        "data": {
            "code": "600519",
            "market": 1,
            "name": "贵州茅台",
            "klines": [
                "2026-09-23,1255.03,1251.24,1271.50,1250.89,30981,3873372920.00,1.65,-0.30,-3.79,0.25",
                "2026-09-24,1250.01,1237.00,1256.13,1231.05,31239,3867310920.00,2.01,-1.14,-14.24,0.25",
            ],
        },
    }
)


def _moutai() -> Symbol:
    return Symbol(market=Market.SH, code="600519")


# --------------------------------------------------------------------------
# Parsing: Tencent
# --------------------------------------------------------------------------


class TestTencentParsing:
    """Field indices and unit conversions, checked against a live payload."""

    def test_realtime_fields_match_the_live_payload(self) -> None:
        quote = TencentProvider.parse(TENCENT_REALTIME, _moutai(), fetched_at=STAMP)

        assert quote.price == pytest.approx(1237.00)
        assert quote.prev_close == pytest.approx(1251.24)
        assert quote.open == pytest.approx(1250.01)
        assert quote.high == pytest.approx(1256.13)
        assert quote.low == pytest.approx(1231.05)
        assert quote.source == "tencent"

    def test_volume_is_converted_from_lots_to_shares(self) -> None:
        """Tencent reports 手 (lots); the internal unit is shares."""
        quote = TencentProvider.parse(TENCENT_REALTIME, _moutai(), fetched_at=STAMP)

        assert quote.volume == pytest.approx(31_239 * 100)

    def test_turnover_is_converted_from_wan_yuan_to_yuan(self) -> None:
        """Tencent reports 万元; the internal unit is CNY."""
        quote = TencentProvider.parse(TENCENT_REALTIME, _moutai(), fetched_at=STAMP)

        assert quote.amount == pytest.approx(386_731 * 10_000)

    def test_change_pct_is_a_decimal_fraction(self) -> None:
        """The source says -1.14 percentage points; the contract says -0.0114."""
        quote = TencentProvider.parse(TENCENT_REALTIME, _moutai(), fetched_at=STAMP)

        assert quote.change_pct == pytest.approx(-0.011381, rel=1e-4)

    def test_daily_bars_carry_no_turnover(self) -> None:
        """The daily endpoint returns six columns — there is no turnover to read.

        ``None`` is the honest answer; ``close * volume`` would be an estimate
        presented as a measurement.
        """
        bars = TencentProvider.parse_daily(TENCENT_DAILY, _moutai(), fetched_at=STAMP)

        assert len(bars) == 5
        assert all(bar.amount is None for bar in bars)

    def test_daily_volume_is_converted_from_lots(self) -> None:
        bars = TencentProvider.parse_daily(TENCENT_DAILY, _moutai(), fetched_at=STAMP)

        assert bars[-1].trade_date == date(2026, 9, 24)
        assert bars[-1].volume == pytest.approx(31_239 * 100)

    def test_daily_prices_agree_with_the_realtime_snapshot(self) -> None:
        """Cross-check: the last bar must equal the live OHLC.

        Two different endpoints of the same source, parsed by two different code
        paths, must produce the same numbers. If a column ever shifts, this is
        what catches it.
        """
        bar = TencentProvider.parse_daily(TENCENT_DAILY, _moutai(), fetched_at=STAMP)[-1]
        live = TencentProvider.parse(TENCENT_REALTIME, _moutai(), fetched_at=STAMP)

        assert bar.open == pytest.approx(live.open)
        assert bar.close == pytest.approx(live.price)
        assert bar.high == pytest.approx(live.high)
        assert bar.low == pytest.approx(live.low)

    def test_unadjusted_series_is_refused_rather_than_substituted(self) -> None:
        """If Tencent answers with ``day`` instead of ``qfqday``, say so.

        Raw and adjusted prices differ across an ex-dividend date and the
        difference is invisible in the numbers, so silently accepting the raw
        series would corrupt every downstream comparison.
        """
        payload = json.dumps(
            {"code": 0, "data": {"sh600519": {"day": [["2026-09-24", "1", "1", "1", "1", "1"]]}}}
        )

        with pytest.raises(ProviderProtocolError, match="qfqday missing"):
            TencentProvider.parse_daily(payload, _moutai(), fetched_at=STAMP)

    def test_empty_range_is_no_data_not_an_error(self) -> None:
        payload = json.dumps({"code": 0, "data": {"sh600519": {"qfqday": []}}})

        with pytest.raises(ProviderEmptyError):
            TencentProvider.parse_daily(payload, _moutai(), fetched_at=STAMP)


# --------------------------------------------------------------------------
# Parsing: Sina
# --------------------------------------------------------------------------


class TestSinaParsing:
    def test_realtime_fields_match_the_live_payload(self) -> None:
        quote = SinaProvider.parse(SINA_REALTIME, _moutai(), fetched_at=STAMP)

        assert quote.price == pytest.approx(1237.000)
        assert quote.prev_close == pytest.approx(1251.240)
        assert quote.open == pytest.approx(1250.010)
        assert quote.high == pytest.approx(1256.130)
        assert quote.low == pytest.approx(1231.050)

    def test_volume_and_turnover_are_not_rescaled(self) -> None:
        """Sina already reports shares and yuan — the opposite of Tencent.

        This is exactly the unit confusion the constitution calls out: two
        sources, same field name, different multipliers.
        """
        quote = SinaProvider.parse(SINA_REALTIME, _moutai(), fetched_at=STAMP)

        assert quote.volume == pytest.approx(3_123_935)
        assert quote.amount == pytest.approx(3_867_310_920.0)

    def test_the_two_sources_agree_on_price(self) -> None:
        """Independent operators, different payloads — the numbers must still match."""
        tencent = TencentProvider.parse(TENCENT_REALTIME, _moutai(), fetched_at=STAMP)
        sina = SinaProvider.parse(SINA_REALTIME, _moutai(), fetched_at=STAMP)

        assert tencent.price == pytest.approx(sina.price, abs=0.01)
        assert tencent.open == pytest.approx(sina.open, abs=0.01)
        assert tencent.high == pytest.approx(sina.high, abs=0.01)
        assert tencent.low == pytest.approx(sina.low, abs=0.01)
        assert tencent.volume == pytest.approx(sina.volume, rel=1e-3)
        assert tencent.amount == pytest.approx(sina.amount, rel=1e-3)

    def test_unknown_symbol_is_no_data(self) -> None:
        with pytest.raises(ProviderEmptyError):
            SinaProvider.parse('var hq_str_sh999999="";', _moutai(), fetched_at=STAMP)


# --------------------------------------------------------------------------
# Parsing: Eastmoney
# --------------------------------------------------------------------------


class TestEastmoneyParsing:
    def test_daily_bars_include_turnover(self) -> None:
        """Eastmoney publishes turnover — the reason it stays first for history."""
        bars = EastmoneyProvider.parse(EASTMONEY_DAILY, _moutai(), fetched_at=STAMP)

        assert len(bars) == 2
        assert bars[-1].trade_date == date(2026, 9, 24)
        assert bars[-1].close == pytest.approx(1237.00)
        assert bars[-1].volume == pytest.approx(31_239 * 100)
        assert bars[-1].amount == pytest.approx(3_867_310_920.0)

    def test_null_data_is_no_data(self) -> None:
        """``data: null`` is how Eastmoney says "I do not serve this venue"."""
        payload = json.dumps({"rc": 0, "data": None})

        with pytest.raises(ProviderEmptyError, match="data is null"):
            EastmoneyProvider.parse(payload, _moutai(), fetched_at=STAMP)


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------


class _Clock:
    """A manually advanced monotonic clock."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class _FakeProvider:
    """A provider whose every answer is scripted, and which counts its calls."""

    def __init__(
        self,
        name: str,
        *,
        datasets: frozenset[Dataset],
        markets: frozenset[Market] | None = None,
        realtime: DataResult[RealtimeQuote] | None = None,
        daily: DataResult[list[Quote]] | None = None,
    ) -> None:
        self._name = name
        self._caps = ProviderCapabilities(
            datasets=datasets,
            markets=markets if markets is not None else frozenset(Market),
        )
        self._realtime = realtime
        self._daily = daily
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._caps

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        self.calls.append("realtime")
        assert self._realtime is not None
        return self._realtime

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> DataResult[list[Quote]]:
        self.calls.append("daily")
        assert self._daily is not None
        return self._daily


def _ok_realtime(source: str, price: float = 10.0) -> DataResult[RealtimeQuote]:
    return DataResult.ok(
        RealtimeQuote(
            symbol=_moutai(),
            price=price,
            prev_close=9.0,
            open=9.5,
            high=10.5,
            low=9.2,
            volume=100.0,
            amount=1000.0,
            quoted_at=STAMP,
            source=source,
            fetched_at=STAMP,
        ),
        source=source,
        fetched_at=STAMP,
    )


def _error(
    source: str,
    code: ErrorCode = ErrorCode.DATA_SOURCE_UNREACHABLE,
) -> DataResult[RealtimeQuote]:
    return DataResult.error(code, source=source, fetched_at=STAMP)


def _rt_provider(name: str, answer: DataResult[RealtimeQuote]) -> _FakeProvider:
    """A provider that serves snapshots and nothing else."""
    return _FakeProvider(name, datasets=frozenset({Dataset.REALTIME}), realtime=answer)


class TestCapabilityRouting:
    """Selection is driven by declarations, never by hard-coded names."""

    def test_dataset_declaration_decides_who_is_asked(self) -> None:
        snapshots = _rt_provider("snap", _ok_realtime("snap"))
        history = _FakeProvider("hist", datasets=frozenset({Dataset.DAILY}))
        router = MarketDataRouter([snapshots, history])

        result = router.get_realtime(_moutai())

        assert result.status is DataStatus.OK
        assert snapshots.calls == ["realtime"]
        assert history.calls == []

    def test_usable_datasets_reflects_declarations(self) -> None:
        snapshots = _FakeProvider("snap", datasets=frozenset({Dataset.REALTIME}))
        history = _FakeProvider("hist", datasets=frozenset({Dataset.DAILY}))
        router = MarketDataRouter([snapshots, history])

        assert router.usable_datasets(_moutai()) == frozenset({Dataset.REALTIME, Dataset.DAILY})

    def test_unsupported_venue_is_never_asked(self) -> None:
        """A venue a source does not claim must not produce a request.

        Sending it anyway invites ``data: null``, which is indistinguishable from
        "this symbol has no data" — and that ambiguity would reach the user.
        """
        provider = _FakeProvider(
            "shsz-only",
            datasets=frozenset({Dataset.REALTIME}),
            markets=frozenset({Market.SH, Market.SZ}),
            realtime=_ok_realtime("shsz-only"),
        )
        router = MarketDataRouter([provider])
        beijing = Symbol(market=Market.BJ, code="430047")

        result = router.get_realtime(beijing)

        assert result.status is DataStatus.ERROR
        assert result.error_code is ErrorCode.DATA_SOURCE_UNAVAILABLE
        assert provider.calls == []


class TestDegradation:
    """Failure handling: fall back, then go stale, never go blank."""

    def test_falls_back_to_the_next_source(self) -> None:
        broken = _rt_provider("broken", _error("broken"))
        backup = _rt_provider("backup", _ok_realtime("backup"))
        router = MarketDataRouter([broken, backup])

        result = router.get_realtime(_moutai())

        assert result.status is DataStatus.OK
        assert result.source == "backup"
        assert broken.calls == ["realtime"]
        assert backup.calls == ["realtime"]

    def test_all_sources_down_falls_back_to_stale_cache(self) -> None:
        """An outage must not blank the page — but the value must be marked old."""
        healthy = _rt_provider("healthy", _ok_realtime("healthy", 42.0))
        router = MarketDataRouter([healthy], cache=MemoryCache())

        assert router.get_realtime(_moutai()).status is DataStatus.OK

        healthy._realtime = _error("healthy")
        stale = router.get_realtime(_moutai())

        assert stale.status is DataStatus.OK
        assert stale.stale is True
        assert stale.source == "healthy"  # provenance is preserved, not rewritten
        assert stale.fetched_at == STAMP
        assert stale.value is not None
        assert stale.value.price == pytest.approx(42.0)

    def test_a_definitive_no_data_outranks_a_stale_value(self) -> None:
        """A live source saying "nothing" beats our cache saying "yesterday".

        Otherwise a delisted symbol would keep showing its last traded price
        forever, which is the opposite of honest.
        """
        provider = _rt_provider("p", _ok_realtime("p"))
        router = MarketDataRouter([provider], cache=MemoryCache())
        router.get_realtime(_moutai())

        provider._realtime = DataResult.no_data(
            "symbol not present in response", source="p", fetched_at=STAMP
        )
        result = router.get_realtime(_moutai())

        assert result.status is DataStatus.NO_DATA
        assert result.stale is False

    def test_without_a_cache_an_outage_reports_the_failure(self) -> None:
        """No cache, no pretending: the error is surfaced, not swallowed."""
        broken = _rt_provider("broken", _error("broken"))
        router = MarketDataRouter([broken])

        result = router.get_realtime(_moutai())

        assert result.status is DataStatus.ERROR
        assert result.error_code is ErrorCode.DATA_SOURCE_UNREACHABLE
        assert result.source == "broken"


class TestCircuitBreaking:
    """A source that said no is not asked again in a loop."""

    def test_a_blocked_source_enters_cooldown(self) -> None:
        clock = _Clock()
        blocked = _rt_provider(
            "blocked", _error("blocked", ErrorCode.DATA_SOURCE_FORBIDDEN)
        )
        backup = _rt_provider("backup", _ok_realtime("backup"))
        router = MarketDataRouter([blocked, backup], clock=clock)

        router.get_realtime(_moutai())
        router.get_realtime(_moutai())

        assert blocked.calls == ["realtime"]  # asked once, then left alone
        assert backup.calls == ["realtime", "realtime"]

    def test_cooldown_expires(self) -> None:
        clock = _Clock()
        blocked = _rt_provider(
            "blocked", _error("blocked", ErrorCode.DATA_SOURCE_FORBIDDEN)
        )
        router = MarketDataRouter([blocked], clock=clock)

        router.get_realtime(_moutai())
        clock.t = 400.0  # past the 300s blocked cooldown
        router.get_realtime(_moutai())

        assert blocked.calls == ["realtime", "realtime"]

    def test_repeated_transport_failures_fuse_the_source(self) -> None:
        clock = _Clock()
        flaky = _rt_provider("flaky", _error("flaky"))
        router = MarketDataRouter([flaky], clock=clock)

        for _ in range(3):
            router.get_realtime(_moutai())
        router.get_realtime(_moutai())

        assert flaky.calls == ["realtime", "realtime", "realtime"]

    def test_a_success_resets_the_failure_count(self) -> None:
        clock = _Clock()
        provider = _rt_provider("p", _error("p"))
        router = MarketDataRouter([provider], clock=clock)

        router.get_realtime(_moutai())
        router.get_realtime(_moutai())
        provider._realtime = _ok_realtime("p")
        router.get_realtime(_moutai())
        provider._realtime = _error("p")
        router.get_realtime(_moutai())
        router.get_realtime(_moutai())

        # The success in the middle cleared the counter, so no fuse yet.
        assert len(provider.calls) == 5


class TestCacheKeying:
    def test_daily_windows_do_not_collide(self) -> None:
        provider = _FakeProvider(
            "p",
            datasets=frozenset({Dataset.DAILY}),
            daily=DataResult.ok([], source="p", fetched_at=STAMP),
        )
        router = MarketDataRouter([provider], cache=MemoryCache())

        router.get_daily(_moutai(), start=date(2026, 1, 1), end=date(2026, 6, 30))
        router.get_daily(_moutai(), start=date(2026, 7, 1), end=date(2026, 9, 26))

        assert provider.calls == ["daily", "daily"]

    def test_an_identical_window_is_served_from_cache(self) -> None:
        provider = _FakeProvider(
            "p",
            datasets=frozenset({Dataset.DAILY}),
            daily=DataResult.ok([], source="p", fetched_at=STAMP),
        )
        router = MarketDataRouter([provider], cache=MemoryCache())

        router.get_daily(_moutai(), start=date(2026, 1, 1))
        router.get_daily(_moutai(), start=date(2026, 1, 1))

        assert provider.calls == ["daily"]

    def test_a_snapshot_is_never_served_from_cache_as_if_current(self) -> None:
        """A cached price is a past price.

        Serving it as the current one would be a quiet lie, so snapshots always
        hit the source even when a perfectly good cached value exists.
        """
        provider = _rt_provider("p", _ok_realtime("p"))
        router = MarketDataRouter([provider], cache=MemoryCache())

        router.get_realtime(_moutai())
        router.get_realtime(_moutai())

        assert provider.calls == ["realtime", "realtime"]


class TestLiveProviders:
    """Guards on the real provider declarations, not on network behaviour."""

    def test_default_router_orders_history_before_convenience(self) -> None:
        from alphacouncil.providers import default_router

        router = default_router()

        # Snapshots: Eastmoney declares no REALTIME, so it is skipped and the
        # realtime sources keep their own order.
        assert [p.name for p in router._providers] == ["eastmoney", "tencent", "sina"]
        snapshots = [p.name for p in router._candidates(Dataset.REALTIME, _moutai())]
        history = [p.name for p in router._candidates(Dataset.DAILY, _moutai())]
        assert snapshots == ["tencent", "sina"]
        assert history == ["eastmoney", "tencent"]

    def test_sina_declares_its_difference_from_tencent(self) -> None:
        """A backup source must state how it differs, or it is not a backup."""
        notes = SinaProvider().capabilities.notes or ""

        assert "shares" in notes
        assert "Referer" in notes

    def test_only_eastmoney_claims_turnover_in_history(self) -> None:
        assert Dataset.DAILY in TencentProvider().capabilities.datasets
        assert Dataset.DAILY in EastmoneyProvider().capabilities.datasets
        assert Dataset.DAILY not in SinaProvider().capabilities.datasets
