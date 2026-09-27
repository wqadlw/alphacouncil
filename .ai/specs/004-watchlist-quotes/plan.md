# Plan · Spec 004 关注池行情

> ⚠️ 按项目纪律，本文件对审查者隐藏（审查者只读 spec 与 diff，不读实现意图）。

## 技术方案

### 后端（`api/routes/watchlist.py` 内新增，不新建路由文件）

新端点挂在既有 watchlist 路由器上（`prefix=/api/v1/watchlist`），因为它定价的就是池子本身 —— 放到 `instruments/` 下会暗示"任意标的"，而它只服务"当前关注中"。

```python
class PoolQuoteRead(BaseModel):
    market: Market
    code: str
    display: str          # Symbol.full，如 600519.SH
    quote: DataResult[RealtimeQuote]

@router.get("/quotes")
def pool_quotes(connection: DatabaseConnection, market_data: MarketData) -> list[PoolQuoteRead]:
    entries = repository.current(connection)          # FR-1：与 GET /watchlist 同源
    for entry in entries:                             # FR-6：顺序，不并发
        symbol = Symbol(market=entry.market, code=entry.code)
        quote = market_data.get_realtime(symbol)
```

- `get_realtime` 不抛传输层异常（providers 自己把 `ProviderError / httpx.HTTPError / OSError` 映射成四态），循环不需要 try —— 意外异常让它冒泡到全局处理器，符合 7.3（捕具体，不裸吞）。
- `Symbol` 构造必须带 `entry.market`（测试用例里混入 sz 标的守这条）。
- 无新错误码：复用 D3 已有的 `DATA_SOURCE_*` 命名空间，`.ai/error-codes.md` 不动。

### 前端

1. `api.ts`：`PoolQuote` 接口 + `getWatchlistQuotes()`（第二个 GET，`/api/v1/watchlist/quotes`）。
2. 新纯函数模块 `quoteSummary.ts`：`QuoteResult | undefined → 行内展示`（价格文本 / 涨跌 / stale / 四态文案）。放纯函数是本仓惯例（`recovery.ts` / `format.ts` 同型），可测、组件保持薄。
3. `PoolPage.tsx`：并行发两个请求；列表先渲染（不等行情）；每行右侧价格单元格；行情请求失败 → 列表下方一行说明（不 blank）；「刷新行情」按钮 + "不自动刷新"说明。

### 测试

- 后端 `tests/unit/test_pool_quotes_api.py`：沿用 `test_instrument_detail_api.py` 的 Stub 模式，Stub 按(symbol→result)字典返回并记录 asked。
- 前端 `quoteSummary.test.ts`：八态用例（undefined / ok / ok+stale / no_data / error / unavailable / 平盘 / 格式）。

## 涉及文件

| 动作 | 文件 |
|---|---|
| 改 | `backend/src/alphacouncil/api/routes/watchlist.py` |
| 增 | `backend/tests/unit/test_pool_quotes_api.py` |
| 改 | `frontend/src/api.ts` · `frontend/src/PoolPage.tsx` |
| 增 | `frontend/src/quoteSummary.ts` · `frontend/src/quoteSummary.test.ts` |
| 改 | `.ai/status.md` · `frontend/README.md` |
| 增 | `.ai/logs/changes/2026-09-27-watchlist-quotes.md` · 本 spec 目录 |

## 风险

| 风险 | 对策 |
|---|---|
| 池子大时顺序取数慢（P0 = 10 只，每只数百 ms） | 页面先渲染列表，行情单元格后到；这是诚实的代价，直到路由器长出批量/限流能力（独立 spec） |
| 嵌套泛型 `DataResult[RealtimeQuote]` 的序列化 | 顶层端点已在返回同一泛型，FastAPI/Pydantic 已验证支持 |
| 谓词语义 | 无谓词 —— 只读端点，不碰写路径 |
