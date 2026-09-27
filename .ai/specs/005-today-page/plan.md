# Plan · Spec 005 今日页（最小切片）

> ⚠️ 按项目纪律，本文件对审查者隐藏。

## 技术方案

### 后端

1. `domain/decision.py`：`KillCriterion.due(as_of: date) -> bool` —— 唯一的规则落点（今天 >= as_of 即到期）。纯函数、日期注入。
2. `storage/repositories/decisions.py`：`list_all(connection)` —— 无 LIMIT 全量（`ORDER BY id ASC`，写序一致）。个人级规模可承受；LIMIT 会静默漏掉旧决策的到期条件。
3. `api/routes/today.py`：`GET /api/v1/today` → `TodayRead{generated_at, attention: list[DueCriterionRead]}`。路由只做编排：`list_all` → 展平每行 `kill_criteria` → 用领域规则 `due(date.today())` 过滤 → 组装。不写规则本身。
   - `DueCriterionRead{decision_id, market, code, display, action, criterion: KillCriterionRead}` —— 复用 `routes/decisions.py` 的谓词读模型（单一来源）。
   - `date.today()` 是**服务器本地**日期 = 读者日期（单机桌面应用，服务器就是读者）。
4. `app.py` 注册 router。

### 前端

1. `routing.ts`：`#/` → `today`；`#/pool` → `pool`；`TODAY_HREF='#/'`、`POOL_HREF` 改值 `'#/'`→`'#/pool'`；其余不变。`routing.test.ts` 同步改写（AC-1）。
2. `QuoteCell.tsx`：从 `PoolPage.tsx` 原样提出为共享组件（无逻辑改动，纯移动）；PoolPage 改为 import。
3. `TodayPage.tsx`：三个独立请求（getToday / listWatchlist / getWatchlistQuotes），各自失败各自说。
   - ① 需要你处理（attention）：每条 = 标的 + action + 谓词句（`formatPredicate`）+ "观察期已到，去核实"，链到标的页。空态 = 事实陈述。
   - ② 我关注的：紧凑行（代码 / 现价 / 涨跌 / 理由），QuoteCell 复用；区块头链接到关注池管理页。
   - ③ ④：一句"还没有"（各自注明缺的编号：D4/D5、J4）。
   - 页头日期：`format.ts` 新增 `todayLabel(now: Date)`（注入时钟，纯格式化，周几用中文）。
4. `api.ts`：`Today` / `AttentionItem` 接口 + `getToday()`。
5. `App.tsx`：today 路由 + document.title。

## 涉及文件

| 动作 | 文件 |
|---|---|
| 改 | `domain/decision.py` · `repositories/decisions.py` · `api/app.py` |
| 增 | `api/routes/today.py` · `tests/unit/test_today_api.py`（+ `test_domain.py` 领域规则用例） |
| 改 | `routing.ts`(+test) · `format.ts` · `App.tsx` · `PoolPage.tsx` |
| 增 | `QuoteCell.tsx` · `TodayPage.tsx` · `api.ts` 增量 |
| 改 | `.ai/status.md` · `frontend/README.md` |

## 风险

| 风险 | 对策 |
|---|---|
| 时区：as_of 是日期、决策 id 是 UTC | as_of 本就是"读者日历上的日期"（产品语义），到期比较用服务器本地 today；领域规则注入日期，测试不受时钟影响 |
| `#/` 语义变化的兼容 | 无持久化链接存量（hash 路由，应用内跳转），POOL_HREF 常量收口所有外部引用 |
