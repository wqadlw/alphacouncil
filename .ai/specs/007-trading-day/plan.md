# Plan · Spec 007 交易日判定

> ⚠️ 按项目纪律，本文件对审查者隐藏。

## 技术方案

### 领域（`domain/trading.py`，新文件，零依赖）

```python
class TradingDayVerdict(StrEnum):   # trading_day / non_trading_day / unknown
class TradingDayBasis(StrEnum):     # probe / weekend / none

#: 09:30 开盘 + 35 分钟余量：交易日必然已有当日 bar。
MARKET_OPEN_CERTAINTY: time = time(10, 5)

def verdict_for(*, now: datetime, last_trading_date: date | None) -> tuple[TradingDayVerdict, TradingDayBasis]:
```

规则表写成**有序元组序列**（条件 → 结论），不写 if/else 链——宪法 7.7"状态转移表是数据不是控制流"。周末分支最前（最确定、零成本）。`last_trading_date > now.date()` 抛 `ValueError`（未来数据 = 源异常）。

### 探针（`api/routes/today.py` 内编排）

```python
_PROBE_SYMBOL = Symbol(market=Market.SH, code="000001", asset_type=AssetType.INDEX)
_PROBE_WINDOW_DAYS = 14   # A股最长假期 ~8 天，窗口保证假期后仍有 bar

def _last_trading_date(market_data, now) -> date | None:
    result = market_data.get_daily(_PROBE_SYMBOL, start=now.date() - 14d, end=now.date())
    return result.value[-1].trade_date if result.status is OK and result.value else None
```

- 走路由：三源互备 / 熔断 / 缓存天然复用（日线允许缓存命中——历史不可变）。
- ValueError（未来日期）捕获 → warn + None。

### API

`TodayRead` + `market_status: MarketStatusRead{verdict, basis, last_trading_date, checked_at}`。`checked_at` = 服务器 UTC 时刻。

### 前端（`TodayPage` 头部 + `api.ts` 类型）

`non_trading_day` → 日期旁显示「休市 · 最后交易日 {formatDay(last_trading_date)}」；其余不显示。

## 测试

- `tests/unit/test_trading.py`（新）：规则表 6 行全覆盖（注入 now/last_trading_date）+ 未来日期抛错
- `tests/unit/test_today_api.py`（增）：stub `get_daily` → trading_day / unknown（探针失败）/ ValueError → unknown 且 200

## 风险

| 风险 | 对策 |
|---|---|
| 盘中当日 bar 缺失 → 交易日误报休市 | 已声明假设；basis 可溯源；status.md §五 登记，下个交易日早晨核实 |
| 探针每页一次请求 | 走路由缓存（日线可命中）；单 symbol 小窗口，成本 ≈ 一次普通取数 |
