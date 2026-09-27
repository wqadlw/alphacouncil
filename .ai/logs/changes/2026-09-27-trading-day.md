# 变更记录 · 2026-09-27 · 交易日探针（spec 007）

- 日期：2026-09-27
- 类型：功能（S1 收尾第二件 · TSP 借鉴 T-08 落地）
- 范围：
  - 新增 `backend/src/alphacouncil/domain/trading.py`（verdict 状态表）· `tests/unit/test_trading.py`（9 项）
  - 修改 `backend/src/alphacouncil/api/routes/today.py`（探针编排 + `market_status`）· `tests/unit/test_today_api.py`（stub 化 + 3 项新测试）
  - 修改 `backend/src/alphacouncil/providers/sources.py`（⭐ 腾讯指数日线 `day` 键支持）· `tests/unit/test_market_data.py`（+2 项，真实 payload 夹具）
  - 修改 `frontend/src/api.ts`（MarketStatus 类型）· `frontend/src/TodayPage.tsx`（休市徽标）
  - 新增 `.ai/specs/007-trading-day/` · 修改 `.ai/status.md` · `.ai/data-sources.md` · `frontend/README.md`
- 依据：宪法 4.6 / 7.7 / 2.4 · TSP T-08（**两处有意偏离，见 spec**）· status.md D3 还差项

---

## ① 想做什么

周日打开应用，看到的是"上周四"的收盘价，页面没有任何东西解释为什么——用户可能以为数据坏了，更糟的是可能把旧价当现价做判断（4.6 的安静失效）。T-08 交易日探针正好回答这个问题：**今天到底开不开市、依据是什么**。本日恰逢周日，是最真实的验收环境。

## ② 做了什么

**⭐ 先实测，后设计**——两次实测推翻了原方案的一半：

1. **腾讯指数快照的 `quoted_at` 是取数时刻而非成交时刻**（周日实测：戳=当下、价格=09-24 收盘）→ TSP 的"行情时间戳"探针在我们这层不成立 → 已登记 data-sources.md「已知的骗人方式」第 6 条。
2. **指数日线最后一根 bar 的 `trade_date` 就是最后交易日** → 探针改用它。零节假日知识：不维护会过时的日历表（凭记忆写节假日 = 宪法 2.4 禁止的虚构）。实测窗口内最后一根 bar = 09-24，**数据自己说出了 09-25（周五）是中秋节休市**——本仓没有任何人硬编码过这个知识。

**判定规则 = 数据表**（宪法 7.7），`domain/trading.py` 纯函数 + 注入时钟：周末 → 休市（确定，调休周末仍休市）；最后交易日==今天 → 交易日；工作日 ≥10:05 且 bar 停在过去 → 休市；工作日 <10:05 → unknown（未开盘 vs 节假日不可分）；探针失败 → unknown；**未来日期 → 抛错**（源异常不是答案）。**对 TSP 的有意偏离**：不做"工作日 → 交易日"兜底——周一可能是国庆，未验证的推断不得冒充答案（4.6）。

**顺带修了一个真实缺口**：腾讯对**指数**日线返回 `day` 键（指数无复权概念，`day` 就是唯一正确序列），而 provider 按"股票拒绝 `day` 替代"的纪律把它拒了——探针曾因此单点依赖最不稳的东财。现在：股票拒绝 `day` 不变，指数读 `day`，各自有真实 payload 夹具的测试守着。

**集成**：`GET /api/v1/today` + `market_status {verdict, basis, last_trading_date, checked_at}`；前端今日页头部在休市时显示「休市 · 最后交易日 09-24」并说明"这不是故障"。trading_day / unknown 不显示徽标（不制造不存在的信息）。

## ③ 得到了什么样的结果

| 项 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `pytest -q` | **461 passed**（447 + 9 领域 + 3 API + 2 指数解析） |
| 后端静态 | mypy / ruff check / format | 全过（77 source files） |
| 前端四道 | typecheck / lint / vitest / build | 全过（62 passed · 0 errors） |
| 质量门禁 | `scripts/dev.py check` | `ran 9 · passed 9 · failed 0` |
| ⭐ 真实冒烟 | uvicorn + curl（周日） | `{"verdict":"non_trading_day","basis":"weekend","last_trading_date":"2026-09-24",...}` —— 周日判休市 ✓，最后交易日 09-24（09-25 中秋）由数据自证 ✓ |

### 3.1 变异检查（4 条，全部变红）

| # | 改坏哪里 | 变红的用例 |
|---|---|---|
| M1 | 拿掉周末规则 | 两条周末用例 |
| M2 | 截点 `>=` → `>` | `test_the_cutoff_second_itself_belongs_to_the_decided_side` |
| M3 | 拿掉未来日期拒绝（改为当答案返回） | `test_a_trading_date_from_the_future_is_a_source_fault` |
| M4 | 路由无视探针结果（last 恒 None） | `test_the_market_status_carries_the_verdict_with_its_basis` |

### 3.2 测试纪律的一次自我纠正

探针接入后，/today 的既有单测**悄悄开始联网**（路由会真的探针）——测试仍绿但 2.97s 的耗时露了馅。conftest 的"测试不碰网络"规则为此而设；随即在 client fixture 装 stub（探针恒拒 → 走 unknown 路径），并把"拒绝探针时 attention 照常工作"补成显式用例。

## ④ 留下了什么

- **新增能力**：交易日判定（探针）· 今日页休市徽标 · 腾讯指数日线支持
- **status.md**：D3 还差项只剩能力矩阵（T-02）；§五 新增一条**已声明假设**（盘中当日 bar，下个交易日早晨必须核实）+ 东财单点依赖随 `day` 键支持缓解的记录
- **data-sources.md**：「骗人方式」+1（快照 quoted_at 语义）；数据边界表更新（腾讯指数日线）
- **未做（不假装做过）**：非交易日跳过取数的优化（依赖与缓存 TTL 的交互设计，另立决策）· 日历层（待可人工核实的权威来源）· 能力矩阵（T-02）
- **下一步候选**：能力矩阵（S1 收尾最后一件）· Playwright 入仓 · `core/config.py` v1 检索配置清理
