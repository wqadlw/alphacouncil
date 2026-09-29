"""Concrete market data providers: Tencent, Sina, Eastmoney.

All three are free, key-less public endpoints — that is a hard requirement
(constitution: zero-registration), not a convenience.

Each provider is split into a **fetch** step and a **parse** step. Parsing is a
pure function of the response text, so the unit tests exercise real payload
shapes without touching the network. This is deliberate: the interesting bugs
in financial data are parsing bugs (unit confusion, shifted columns), not
transport bugs.

Unit boundary (constitution 4.2): sources express change as percentage points;
the internal contract uses decimal fractions. Conversion happens *here*, and
the resulting model recomputes the value rather than trusting the source.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import httpx

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.core.http import build_client
from alphacouncil.models.market import (
    AssetType,
    DataResult,
    Market,
    Quote,
    RealtimeQuote,
    Symbol,
)
from alphacouncil.providers.base import (
    BatchSemantics,
    Dataset,
    ProviderBlockedError,
    ProviderCapabilities,
    ProviderEmptyError,
    ProviderError,
    ProviderProtocolError,
    ProviderUnreachableError,
    now,
)

#: ⭐ These sources refuse agents they do not recognise, so this string is deliberately
#: **not** the product's name. It is the one place in the codebase that lies about who it
#: is, and it is a named constant with a comment rather than a default buried in a factory.
#: ADR-0031 records why the webhook channel is not allowed to reuse it.
_MARKET_DATA_UA = "Mozilla/5.0 (compatible; AlphaCouncil/0.2)"


def _client(headers: dict[str, str] | None = None) -> httpx.Client:
    """Build a client for a market data source.

    ⭐ This no longer constructs anything — ``core/http.py`` owns that (ADR-0031, S-01).
    It stays as a named wrapper because the browser User-Agent belongs to **this** package
    and not to the shared factory, and a function whose whole body is one call is still
    the thing that says which policy a market data request gets.
    """
    return build_client(user_agent=_MARKET_DATA_UA, headers=headers)


def _guard(response: httpx.Response) -> None:
    """Map HTTP outcomes onto provider errors.

    403 is deliberately *not* retried anywhere upstream: a source that already
    refused us should not be asked again in a loop.
    """
    if response.status_code in {403, 429}:
        raise ProviderBlockedError(f"HTTP {response.status_code}")
    if response.status_code >= 400:
        raise ProviderUnreachableError(f"HTTP {response.status_code}")


def _secid_prefix(market: Market) -> str:
    """Map a venue to Eastmoney's numeric prefix."""
    return "1" if market is Market.SH else "0"


def _failure(exc: Exception, *, source: str, stamp: datetime) -> DataResult[Any]:
    """Map a provider exception onto the honest data state.

    One mapping shared by every provider, so the four-state contract cannot
    drift between sources: an empty answer is ``no_data``, a refusal is
    ``blocked``, a malformed answer is ``unavailable``, and a transport fault is
    an ``error``. Collapsing any two of those is how a bug becomes a wrong
    number instead of a visible absence.
    """
    if isinstance(exc, ProviderEmptyError):
        return DataResult.no_data(str(exc), source=source, fetched_at=stamp)
    if isinstance(exc, ProviderBlockedError):
        return DataResult.error(
            ErrorCode.DATA_SOURCE_FORBIDDEN,
            source=source,
            fetched_at=stamp,
            detail=str(exc),
        )
    if isinstance(exc, ProviderProtocolError):
        return DataResult.unavailable(str(exc), source=source, fetched_at=stamp)
    return DataResult.error(
        ErrorCode.DATA_SOURCE_UNREACHABLE,
        source=source,
        fetched_at=stamp,
        detail=type(exc).__name__,
    )


# ---------------------------------------------------------------------------
# Tencent  (qt.gtimg.cn)  — realtime snapshots
# ---------------------------------------------------------------------------


class TencentProvider:
    """Realtime quotes from Tencent.

    Payload is GBK-encoded, semicolon-terminated, tilde-delimited. Field
    indices below were verified against live responses; the parser validates
    the bar afterwards so a shifted column cannot slip through silently.
    """

    _URL = "https://qt.gtimg.cn/q={code}"

    @property
    def name(self) -> str:
        return "tencent"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            datasets=frozenset({Dataset.REALTIME, Dataset.DAILY}),
            markets=frozenset({Market.SH, Market.SZ}),
            batch_semantics=BatchSemantics.INDEPENDENT,
            supports_batch=True,
            notes="Realtime and daily history. Daily bars carry **no turnover** "
            "(the endpoint returns six columns), so amount is None rather than "
            "estimated. BJ (Beijing exchange) is unverified and not claimed.",
        )

    def _fetch(self, symbol: Symbol) -> str:
        """Fetch the raw GBK payload for one symbol."""
        code = f"{symbol.market.value}{symbol.code}"
        with _client() as client:
            response = client.get(self._URL.format(code=code))
            _guard(response)
            return response.content.decode("gbk", errors="replace")

    @staticmethod
    def parse(text: str, symbol: Symbol, *, fetched_at: datetime) -> RealtimeQuote:
        """Parse a Tencent payload into a snapshot quote."""
        if '="' not in text:
            raise ProviderProtocolError("missing assignment in payload")
        payload = text.split('="', 1)[1].rstrip('";\n ')
        if not payload:
            # An empty assignment means the source has nothing for this code.
            # Reporting it as a protocol error would blame the source for our
            # own request, and the distinction reaches the user.
            raise ProviderEmptyError("empty payload (unknown symbol)")
        parts = payload.split("~")
        if len(parts) < 35:
            raise ProviderProtocolError(f"expected >=35 fields, got {len(parts)}")

        def num(index: int) -> float:
            raw = parts[index].strip()
            if raw in {"", "-"}:
                raise ProviderEmptyError(f"field {index} is empty")
            return float(raw)

        price, prev_close = num(3), num(4)
        if prev_close <= 0:
            raise ProviderProtocolError(f"prev_close must be > 0, got {prev_close}")
        return RealtimeQuote(
            symbol=symbol,
            price=price,
            prev_close=prev_close,
            open=num(5),
            high=num(33),
            low=num(34),
            volume=num(6) * 100.0,  # source reports lots; internal unit is shares
            amount=num(37) * 10_000.0,  # source reports 万元; internal unit is CNY
            quoted_at=fetched_at,
            source="tencent",
            fetched_at=fetched_at,
        )

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        """Fetch one realtime snapshot."""
        stamp = now()
        try:
            text = self._fetch(symbol)
            if f"{symbol.market.value}{symbol.code}" not in text:
                return DataResult.no_data(
                    "symbol not present in response", source=self.name, fetched_at=stamp
                )
            quote = self.parse(text, symbol, fetched_at=stamp)
            return DataResult.ok(quote, source=self.name, fetched_at=stamp)
        except (ProviderError, httpx.HTTPError, OSError) as exc:
            return _failure(exc, source=self.name, stamp=stamp)

    _DAILY_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    # Tencent caps a single response at a few hundred bars. Unverified exactly
    # where the cap sits, so we ask for a deliberately modest window.
    _DEFAULT_BARS = 320

    def _fetch_daily(self, symbol: Symbol, start: date | None, end: date | None) -> str:
        """Fetch the raw JSON payload for a daily series."""
        param = ",".join(
            (
                f"{symbol.market.value}{symbol.code}",
                "day",
                start.isoformat() if start else "",
                end.isoformat() if end else "",
                str(self._DEFAULT_BARS),
                "qfq",
            )
        )
        with _client() as client:
            response = client.get(self._DAILY_URL, params={"param": param})
            _guard(response)
            return response.text

    @staticmethod
    def parse_daily(text: str, symbol: Symbol, *, fetched_at: datetime) -> list[Quote]:
        """Parse a Tencent ``fqkline`` payload into daily bars.

        Only the forward-adjusted series (``qfqday``) is accepted. When Tencent
        answers with an unadjusted series instead, we report "unavailable" rather
        than pass raw prices off as adjusted ones — across an ex-dividend date
        those two differ, and the difference is invisible in the numbers.
        """
        try:
            payload: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderProtocolError(f"invalid JSON: {exc}") from exc

        if payload.get("code") != 0:
            raise ProviderProtocolError(f"non-zero code: {payload.get('code')!r}")

        data = payload.get("data")
        node = (data or {}).get(f"{symbol.market.value}{symbol.code}")
        if not node:
            raise ProviderEmptyError("symbol not present in response")

        # Tencent files stock series under ``qfqday`` (forward-adjusted) and
        # index series under ``day`` — an index has no adjustment basis at
        # all, so ``day`` *is* the only correct series for it, not a
        # substitute for one (that refusal stays in force for stocks).
        if symbol.asset_type is AssetType.INDEX:
            rows = node.get("day")
            if rows is None:
                raise ProviderProtocolError("index daily series ('day') missing from payload")
            adjustment = 1.0
        else:
            rows = node.get("qfqday")
            if rows is None:
                raise ProviderProtocolError("qfqday missing; refusing to substitute raw prices")
            adjustment = 1.0  # series is already forward-adjusted (qfq)
        if not rows:
            raise ProviderEmptyError("no bars in the requested range")

        bars: list[Quote] = []
        for row in rows:
            if len(row) < 6:
                raise ProviderProtocolError(f"expected >=6 cells, got {len(row)}: {row!r}")
            bars.append(
                Quote(
                    symbol=symbol,
                    trade_date=datetime.strptime(str(row[0]), "%Y-%m-%d").date(),
                    open=float(row[1]),
                    close=float(row[2]),
                    high=float(row[3]),
                    low=float(row[4]),
                    volume=float(row[5]) * 100.0,  # lots -> shares
                    amount=None,  # this endpoint publishes no turnover
                    adj_factor=adjustment,
                    source="tencent",
                    fetched_at=fetched_at,
                )
            )
        return bars

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> DataResult[list[Quote]]:
        """Fetch daily bars for one symbol."""
        stamp = now()
        try:
            text = self._fetch_daily(symbol, start, end)
            bars = self.parse_daily(text, symbol, fetched_at=stamp)
            return DataResult.ok(bars, source=self.name, fetched_at=stamp)
        except (ProviderError, httpx.HTTPError, OSError) as exc:
            return _failure(exc, source=self.name, stamp=stamp)


# ---------------------------------------------------------------------------
# Sina  (hq.sinajs.cn)  — realtime snapshots, requires a Referer
# ---------------------------------------------------------------------------


class SinaProvider:
    """Realtime quotes from Sina.

    Sina rejects requests without a finance.sina.com.cn referer, so the header
    is mandatory rather than cosmetic.
    """

    _URL = "https://hq.sinajs.cn/list={code}"
    _REFERER = "https://finance.sina.com.cn"

    @property
    def name(self) -> str:
        return "sina"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            datasets=frozenset({Dataset.REALTIME}),
            markets=frozenset({Market.SH, Market.SZ}),
            batch_semantics=BatchSemantics.INDEPENDENT,
            supports_batch=True,
            notes="Realtime only. Differs from Tencent: reports volume in shares, "
            "not lots; requires a Referer header. BJ is unverified.",
        )

    def _fetch(self, symbol: Symbol) -> str:
        """Fetch the raw payload for one symbol."""
        code = f"{symbol.market.value}{symbol.code}"
        with _client({"Referer": self._REFERER}) as client:
            response = client.get(self._URL.format(code=code))
            _guard(response)
            return response.content.decode("gbk", errors="replace")

    @staticmethod
    def parse(text: str, symbol: Symbol, *, fetched_at: datetime) -> RealtimeQuote:
        """Parse a Sina payload into a snapshot quote."""
        if '="' not in text:
            raise ProviderProtocolError("missing assignment in payload")
        payload = text.split('="', 1)[1].rstrip('";\n ')
        if not payload:
            raise ProviderEmptyError("empty payload (unknown symbol)")
        parts = payload.split(",")
        if len(parts) < 32:
            raise ProviderProtocolError(f"expected >=32 fields, got {len(parts)}")

        def num(index: int) -> float:
            raw = parts[index].strip()
            if raw in {"", "-"}:
                raise ProviderEmptyError(f"field {index} is empty")
            return float(raw)

        price, prev_close = num(3), num(2)
        if price <= 0:
            raise ProviderEmptyError("price is zero (not yet traded)")
        if prev_close <= 0:
            raise ProviderProtocolError(f"prev_close must be > 0, got {prev_close}")
        return RealtimeQuote(
            symbol=symbol,
            price=price,
            prev_close=prev_close,
            open=num(1),
            high=num(4),
            low=num(5),
            volume=num(8),  # already shares
            amount=num(9),  # already CNY
            quoted_at=fetched_at,
            source="sina",
            fetched_at=fetched_at,
        )

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        """Fetch one realtime snapshot."""
        stamp = now()
        try:
            text = self._fetch(symbol)
            quote = self.parse(text, symbol, fetched_at=stamp)
            return DataResult.ok(quote, source=self.name, fetched_at=stamp)
        except (ProviderError, httpx.HTTPError, OSError) as exc:
            return _failure(exc, source=self.name, stamp=stamp)

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> DataResult[list[Quote]]:
        """Sina does not serve daily history through this endpoint."""
        del start, end, symbol
        return DataResult.error(
            ErrorCode.DATA_SOURCE_NOT_SUPPORTED, source=self.name, fetched_at=now()
        )


# ---------------------------------------------------------------------------
# Eastmoney  (push2his.eastmoney.com)  — daily history, forward-adjusted
# ---------------------------------------------------------------------------


class EastmoneyProvider:
    """Forward-adjusted daily bars from Eastmoney.

    The endpoint is the one we measured as rate-limited in practice, so the
    router treats it as the *preferred but fragile* history source and backs it
    with a local cache.
    """

    _URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    _FIELDS1 = "f1,f2,f3,f4,f5,f6"
    _FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58"

    @property
    def name(self) -> str:
        return "eastmoney"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            datasets=frozenset({Dataset.DAILY, Dataset.ADJ_FACTOR}),
            markets=frozenset({Market.SH, Market.SZ}),
            batch_semantics=BatchSemantics.COLLATERAL,
            supports_batch=False,
            notes="Daily history only, forward-adjusted (fqt=1), **with turnover** — "
            "the reason it stays first for history despite being the most "
            "rate-limit-prone source. Returns data:null for unsupported venues "
            "instead of an error, so callers must pre-filter; never ask it for a "
            "batch. BJ secid prefix is unverified.",
        )

    def _fetch(self, symbol: Symbol, start: date | None, end: date | None) -> str:
        """Fetch the raw JSON payload."""
        params = {
            "secid": f"{_secid_prefix(symbol.market)}.{symbol.code}",
            "fields1": self._FIELDS1,
            "fields2": self._FIELDS2,
            "klt": "101",  # daily
            "fqt": "1",  # forward-adjusted
            "beg": start.strftime("%Y%m%d") if start else "0",
            "end": end.strftime("%Y%m%d") if end else "20500101",
        }
        with _client() as client:
            response = client.get(self._URL, params=params)
            _guard(response)
            return response.text

    @staticmethod
    def parse(text: str, symbol: Symbol, *, fetched_at: datetime) -> list[Quote]:
        """Parse an Eastmoney kline payload into daily bars."""
        try:
            payload: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderProtocolError(f"invalid JSON: {exc}") from exc

        data = payload.get("data")
        if data is None:
            raise ProviderEmptyError("data is null (unsupported venue or symbol)")
        klines = data.get("klines")
        if not klines:
            raise ProviderEmptyError("klines is empty")

        bars: list[Quote] = []
        for row in klines:
            cells = row.split(",")
            if len(cells) < 7:
                raise ProviderProtocolError(f"expected >=7 cells, got {len(cells)}: {row!r}")
            bars.append(
                Quote(
                    symbol=symbol,
                    trade_date=datetime.strptime(cells[0], "%Y-%m-%d").date(),
                    open=float(cells[1]),
                    close=float(cells[2]),
                    high=float(cells[3]),
                    low=float(cells[4]),
                    volume=float(cells[5]) * 100.0,  # lots -> shares
                    amount=float(cells[6]),
                    adj_factor=1.0,  # series is already forward-adjusted (fqt=1)
                    source="eastmoney",
                    fetched_at=fetched_at,
                )
            )
        return bars

    def get_daily(
        self,
        symbol: Symbol,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> DataResult[list[Quote]]:
        """Fetch daily bars for one symbol."""
        stamp = now()
        try:
            text = self._fetch(symbol, start, end)
            bars = self.parse(text, symbol, fetched_at=stamp)
            return DataResult.ok(bars, source=self.name, fetched_at=stamp)
        except (ProviderError, httpx.HTTPError, OSError) as exc:
            return _failure(exc, source=self.name, stamp=stamp)

    def get_realtime(self, symbol: Symbol) -> DataResult[RealtimeQuote]:
        """Eastmoney history endpoint does not serve snapshots."""
        del symbol
        return DataResult.error(
            ErrorCode.DATA_SOURCE_NOT_SUPPORTED, source=self.name, fetched_at=now()
        )


def default_symbol(
    code: str,
    market: Market = Market.SH,
    asset_type: AssetType = AssetType.STOCK,
) -> Symbol:
    """Convenience constructor used by scripts and tests."""
    return Symbol(market=market, code=code, asset_type=asset_type)
