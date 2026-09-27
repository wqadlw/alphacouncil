# Tasks · Spec 004 关注池行情

- [x] T1 后端：`GET /api/v1/watchlist/quotes`（`PoolQuoteRead` + 顺序遍历 + 复合键）
- [x] T2 后端测试：空池 / 两只定价 / 三态并存不连坐 / 移出不定价 / stale 透传 / 每只恰好被问一次
- [x] T3 前端：`api.ts` 的 `getWatchlistQuotes` + `PoolQuote`
- [x] T4 前端：`quoteSummary.ts` 纯函数 + `quoteSummary.test.ts`
- [x] T5 前端：`PoolPage` 行内价格单元格 + 刷新按钮 + 失败说明行
- [x] T6 门禁：后端 ruff / mypy / pytest；前端四道；静态检查 12/12
- [x] T7 变异检查 5 条并记录（3 后端 + 2 前端，见变更日志）
- [x] T8 台账：status.md（D1 / S1 行）· 变更记录 · frontend/README
