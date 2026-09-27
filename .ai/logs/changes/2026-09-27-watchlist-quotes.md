# 变更记录 · 2026-09-27 · 关注池行情（把 D3 接到 D1，spec 004）

- 日期：2026-09-27
- 类型：功能（S1 收尾 —— 首页「我关注的」从"只有记录"变为"记录 + 现价涨跌"）
- 范围：
  - 修改 `backend/src/alphacouncil/api/routes/watchlist.py`（新增 `GET /quotes`）
  - 新增 `backend/tests/unit/test_pool_quotes_api.py`（5 项）
  - 修改 `frontend/src/api.ts`（`PoolQuote` + `getWatchlistQuotes`）· `frontend/src/PoolPage.tsx`（行情列）· `frontend/src/InstrumentPage.tsx`（TONE_CLASS 上移，行为无变化）· `frontend/src/format.ts`（接收 `TONE_CLASS`）
  - 新增 `frontend/src/quoteSummary.ts` · `frontend/src/quoteSummary.test.ts`（7 项）
  - 新增 `.ai/specs/004-watchlist-quotes/`（spec / plan / tasks）· 修改 `.ai/status.md` · `frontend/README.md`
- 依据：宪法 2.1 / 2.3 / 4.6 / 7.5 / 8.1 / 8.3 / 10.3 · ADR-0017 · `.ai/status.md` S1 还差项 · 上一轮变更日志「下一步」#2
- **背景**：本条是上一会话中断后的**第一次接手开发**。接手时核实：工作树干净（HEAD `885711f`）· 后端 421 passed · 前端 51 passed · CI 全绿 —— **上一个会话没有留下半成品或损坏**，中断点在 #31（J1）完整提交之后。

---

## ① 想做什么

status.md S1 行的最后一个"还差"是「**行情与关注池之间还没有连接**（首页"我关注的"取不到涨跌）」。数据层的两半都已存在：D1 关注池打通到 HTTP 边界，D3 行情有唯一入口 + 三源互备 + 四态契约 —— 缺的只是一根管子。P0 验收句「每天打开能看到动态」里"动态"两个字，至今没有着落。

本条只做**连接**，不新增数据能力：不加数据源、不加缓存、不加字段。所有行情语义（四态 / 熔断 / 降级）已由路由器拥有，这里只是调用它。

## ② 做了什么

**规格先行**（宪法 10.3）：`.ai/specs/004-watchlist-quotes/`，8 条 FR + 8 条 AC + 6 条"已知的失败"。核心决定有三条，全部写进了端点 docstring：

| 决定 | 理由 |
|---|---|
| 定价范围 = `watchlist_current` 视图，与 `GET /watchlist` **同一来源** | 两个端点对"谁在池子里"各持一份理解，页面就会给一只列表说你已离开的股票报现价 |
| **每行自己的四态，绝不合并成批次状态** | 十只票的真话是「7 只 ok · 2 只无报价 · 1 只失败」；任何单一批次状态都是对其中至少一只的谎报（TSP T-06 连坐语义） |
| **顺序遍历，每只恰好一次**，循环里没有 `try` | 十只票并发 = 十个同时的上游请求 —— 东财限流实测过一次；providers 自己把传输异常映射成四态，循环里的异常只能是 bug，应当 500 |

**后端**：`PoolQuoteRead(market, code, display, quote)` + `GET /api/v1/watchlist/quotes`。无新错误码（复用 `DATA_SOURCE_*` 命名空间），`error-codes.md` 不动。

**前端**：`quoteSummary.ts` 纯函数（`QuoteResult | undefined` → 行内价格 / 涨跌 / stale / 四态文案 + 悬停出处），`PoolPage` 列表与行情**两个请求并行发出、各自失败各自说**；「刷新行情」按钮；页脚加"不自动刷新"声明。`TONE_CLASS` 从 `InstrumentPage` 上移到 `format.ts` —— 我的行情列是它的第二个使用方，按"先复用"上移而不是复制第二份。

## ③ 得到了什么样的结果

| 项 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `pytest -q` | **426 passed**（421 + 5） |
| 后端静态 | `ruff check` / `ruff format --check` / `mypy` | 全过（72 source files） |
| 静态检查 | `python -m checks --strict` | `ran 12 · skipped 0 · crashed 0 · 0 error` ✓ |
| 前端四道 | typecheck / lint / vitest / build | **58 passed**（51 + 7）· 0 errors / 3 warnings（既有刻意保留）· build 25 modules · JS 258.06 kB |
| 质量门禁 | `scripts/dev.py check` | **`ran 9 · passed 9 · failed 0 · skipped 0`** · 退出码 0 |
| ⭐ 真实冒烟 | uvicorn + `curl --noproxy` | `GET /watchlist/quotes` 对真实库的 2 只票返回 **2/2 ok（腾讯源）**：600036 = 40.69（+0.22%）· 600519 = 1237.00（−1.14%），`change_pct` 服务端计算、时间戳带 `Z`、`stale=false` |

### 3.1 变异检查（5 条，全部变红；宪法 8.3）

| # | 改坏哪里 | 变红的用例 |
|---|---|---|
| M1 | 每行自己的结果 → **循环外共享一份**（批次状态谎报） | `test_one_symbols_failure_does_not_contaminate_the_others` · `test_every_followed_instrument_...`（2 failed） |
| M2 | `Symbol(market=entry.market, …)` → **写死 `Market.SH`**（丢市场） | 同上两条（sz 行 KeyError → 500） |
| M3 | 透传 stale → **`model_copy(update={"stale": False})`**（抹平陈旧标记） | `test_a_stale_price_arrives_still_labelled_stale` |
| M4 | 前端 `stale: result.stale` → `stale: false` | `marks a stale value instead of passing it off as today's` |
| M5 | no_data 强调级别 `faint` → `warn`（"确实没有"不该报警） | `says 无报价 when the source has nothing for the code` |

### 3.2 ⭐ 一次假绿（记录在案）

第一轮 M1 用 bash heredoc + 裸 `python` 做替换 —— **替换根本没发生**（`python` 不在此 shell 的 PATH，heredoc 在本机有已知的 MSYS 改写坑，`REFERENCE.md` R7.6 早已记录过），测试"5 passed"看似通过。识别线索：变异后**一个测试都没红**本身就是可疑信号 —— 5 个测试里没有一条压在"每行自己的结果"上是不可能的。改用 Edit 工具做变异（恢复时 old_string 不匹配即报错，天然可验证），五条全部真实变红。**教训与既有纪律同源：变异检查必须先确认"改坏"真的发生了。**

## ④ 留下了什么

- **新增能力**：`GET /api/v1/watchlist/quotes` + 关注池行情列（含刷新按钮、失败说明行、stale「旧」标记）
- **新增文件**：spec 004 三件套 · `test_pool_quotes_api.py` · `quoteSummary.ts` + 测试
- **status.md**：S1 行与 D1 行的"行情还没接进来"已消除；还差项剩磁盘缓存 / 交易日探针 / 能力矩阵
- **未做（不假装做过）**：
  - 顺序遍历是**临时**的限流纪律 —— 路由器自己的串行化 + 最小间隔（宪法 7.8 唯一入口的完整形态）仍是独立还差项，池子变大后这里要先动
  - 页面渲染与交互（浏览器层）验证只到 curl 级 —— Playwright 未进仓库的缺口未变（上一轮已标注为"当前最值得补"）
  - S1 其余还差项（磁盘缓存层 / 交易日探针 / 能力矩阵）未动
- **下一步**（按 P0 剩余）：**T1 今日页**（P0 五项的最后一个，四块内容里的"我关注的"现在有数据可用了）· 或 S1 收尾三件（磁盘缓存 / 交易日探针 / 能力矩阵）· 或 Playwright 入仓
