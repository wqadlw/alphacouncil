# spec 051 · 把财务数据接上：先决定两件设计问题，再写代码

> 立项：2026-10-02 · **状态：设计已定，未动代码**
> 依据：`.ai/specs/043-financial-data-source/spec.md`（D4 本体）· `ADR-0031`
> 上游计划：`.ai/logs/changes/2026-10-02-plan.md` 任务 4（**该任务的三处说法已被实测推翻，见文末**）
> 门禁现状：17 条静态检查全绿 · `S-08` 刚补上一个盲区（见 §五）

---

## 一、为什么先写这份文档，而不是直接接线

⚠️ **因为接线要跨过回看偏差那条线，而那条线上「写错也说得通」。**

D4 的数据层把防回看偏差做得**非常完整**：单独存 `announced_at` · 主键含它（重述 = 新行不是覆盖）·
两个 append-only 触发器 · provider 侧拒绝「公告早于报告期」· 按公告日而非报告期排序 ·
文档里点名了 constitution §4.4 与红线 17。

⇒ **而消费层零实现**：`as_of()` 零调用者，`criterion_eval.py:147` 按 `trade_date` 取行情，
`read_metric(metric, bars: Sequence[Quote])` 的签名里**没有位置放财务数据**。

⭐ **这一段是全文最重要的一句**：一个正确的存储层 + 一个没接的消费层，
**加起来是一个会说谎的产品** —— 库里有正确的公告日，而页面上算出来的判据看不到它。

## 二、要接的不是一个端点，是八处（逐条实测，不是估计）

| # | 位置 | 改动 | 不做会怎样 |
|---|---|---|---|
| 1 | `providers/router.py:149-162` | `MarketDataRouter.__init__` 收**第二个** provider 列表 | ⚠️ **不改这里 mypy 就红** —— 现有列表类型是 `list[MarketDataProvider]`，而财务实现的是 `FinancialDataProvider` |
| 2 | `providers/router.py:211-266` | `capability_matrix()` 并入财务源 | ⭐ **`/capabilities` 会一直说财务是 `pending`，而那句话在 `BaostockFinancial` 存在的前提下是错的** |
| 3 | `providers/router.py:203-209` | `usable_datasets()` 同上 | 同上 |
| 4 | **设计**（§三） | `MetricStatus` + `CriterionVerdict` 各加一个成员 | ⭐ **判据会说「回来等一根日线」，而读者该等的是财报公告那天** |
| 5 | **设计**（§四） | `MetricFacts` 加一组公告期字段 + `criterion_sentence` 加一支 | 财务判据会说「还没有值」，**与「没有公告」不是同一句话** |
| 6 | `domain/criterion_eval.py:143-154` | `evaluate()` 取数改 `announced_at <= as_of` | 回看偏差 |
| 7 | `metrics.py:51-63` | 8 个指标各写一条读法 | 连进目录的资格都没有 |
| 8 | `api/routes/financial.py`（新）+ `app.py:205` | 3 个端点 | 无界面 |
| 9 | `frontend/src/api.ts` + `TodayPage.tsx:142-146` | 面板 + **先问 `/capabilities`** | ⚠️ `TodayPage.tsx:144` 现在写着「公告与财务数据源尚未接入（D4 / D5）」，**接线后这句话就是假的** |

⚠️ **第 9 行的最后半句是最容易漏的**：`status.md` 说 provider 已落地，界面说尚未接入 ——
**两处「未接入」，其中一处已经错了。** 而 `S-03` 的 docstring（`:26-29`）说的正是这个形状：
「这个字段会存在，然后被下一个加界面的人填上」。

## 三、设计决定一：**「该指标有这个数据，但那天还没公告」不是 `WARMING`**

### 3.1 结构性事实（读出来的，不是推断的）

`_VERDICT_FOR_STATUS`（`criterion_eval.py:124-129`）是 `MetricStatus` 上的**双射**：
4 个状态 ↔ 4 个判据。⇒ **加一个判据就必须同时加一个状态**，否则要么映射不完备，
要么破掉双射。

### 3.2 为什么 `WARMING` 是错的（具体到句子）

`criterion_sentence.py:159-189` 的 `warming` 有两支：

```
bars_available 有值  -> 「还差 {missing} 根日线才有值，这条判据暂时没有被求值」
bars_available 为空  -> 「还没有值，这条判据没有被求值过」
```

⚠️ **两支都以「根日线」计量。** 一条财务判据**根本没有日线** ——
它会落进第二支，说「还没有值」。

而真相是**「那一期在那天没有公告」**。⇒ **两句话决定的事不同**：
「还差 N 根日线」是**一个会自己兑现的承诺**（`warming` 的注释把这称作
「一次延期与一句耸肩的区别」），而「那天没有公告」**没有这种承诺**。

⭐ **而这个承诺不能编。** `financial.py:372-377` 实测公告滞后 **25 / 46 / 93 天**
（2026Q1 / 2026Q2 / 2024 年报），并明写**「约 2 个月」是错的** ——
`spec 043:41-45` 已经因为官方文档的「约 2 个月」在季报上错了三次而推翻过一次。

⇒ **所以新的状态不给任何时间预测。** 它只说两件已知的事：
① 那一期在 `as_of` 之前没有公告；② **我们最后拿到的是哪一期**。

### 3.3 定下来的形状

```python
# domain/metrics.py
class MetricStatus(StrEnum):
    ...
    #: The metric is in the catalogue and the pipeline works, but **no report had been
    #: announced on or before the reader's as_of**. ⭐ Not `WARMING`: that one counts
    #: *bars*, and a promise of 「N more bars」 is a promise that resolves on its own. This
    #: one has no such promise, and `financial.py:372-377` measured the announcement lag at
    #: 25 / 46 / 93 days, so **any number here would be fabricated** (`spec 043:45`).
    NOT_ANNOUNCED = "not_announced"

# domain/criterion_eval.py
class CriterionVerdict(StrEnum):
    ...
    #: Due, the metric is one we compute, and **its report had not been announced on this
    #: date**. ⭐ A fourth kind of 「we don't know」, and the only one whose remedy is a
    #: *calendar* rather than more data.
    NOT_ANNOUNCED = "not_announced"
```

⚠️ **`answerable` 不变** —— 它只认 `CROSSED` / `NOT_CROSSED`，
而新状态显然不是对比较结果的陈述。**这一条不需要改，但它需要被确认过。**

### 3.4 ⭐ 状态名不变，但**必须携带一个事实**

原设计是一个孤立的布尔，调研把它改了。依据（`research.md` §四）：

> Treat `period` as the x-axis of your chart and `as_of` as the lens you view it through.
> The period tells you *which* point you are plotting; the cutoff tells you *which vintage*
> of that point you are allowed to see.

⇒ **读者需要的不是「还没公告」这四个字，是「你当时能看到的最新是哪一期」。**

| | 原（布尔） | 改后（带事实） |
|---|---|---|
| 状态 | `NOT_ANNOUNCED` | `NOT_ANNOUNCED`（**名字不变**） |
| 携带 | 无 | ⭐ `latest_announced_period_end: date \| None` |
| 句子 | 「这一期还没公告」 | 「2026 中报在 2026-09-20 之前没有公告；你当时最新能看到的是 2025 年报」 |

⚠️ **仍然不含任何时间预测** —— 它说的是**已经发生的事**，不是**将发生的事**。
⇒ 写进 `MetricFacts`（该类已有 `period` / `bars_available` 两组，**两组都是行情形状的**，
所以财务需要第三组）。

### 3.5 ⭐ 调研给出的两条额外要求

| # | 要求 | 依据 |
|---|---|---|
| 1 | ⭐ **一条 MUST-RED 的变异：把一条财报**重述一次**（同 `period_end`，更晚的 `announced_at`），断言 `as_of(重述前的日期)` 返回**旧值**。** ⚠️ **只测「没有重述」的路径永远抓不到这个 bug** —— 无重述时两条取数路径给出同一个答案 | `research.md` §三（`as-of join` 的 `leak` 列） |
| 2 | ⭐ **`as_of` 的解析要 fail closed。** 今天 `2026-9-20`（一位月份）静默通过，而它比 `2026-09-20` 小，**会让 `announced_at <= as_of` 少取一段报告** —— 一个时间参数写错 = 判据少看一期，而没有任何报错 | `research.md` §六 |

## 四、设计决定二：**报告期口径必须落库（年报 vs 季报）**

### 4.1 缺口

`FinancialPeriod`（`financial.py:115-135`）**只有 `period_end: date`**，
没有 `period_type` / `fiscal_year` / `quarter`。迁移里也没有。

⚠️ 而 `get_financial` **内部恰恰是按 `(year, quarter)` 枚举的**（`:392-393`）
—— **这个区分在出口被丢掉了。**

### 4.2 为什么这不是「以后再说」

8 个指标的口径**本身分属不同周期**：
`netProfit` / `MBRevenue` 是**累计**到报告期的，`roeAvg` 是**平均**，`epsTTM` 是**滚动 12 个月**。

⇒ 表里**没有任何一列记录口径**，而这直接撞宪法 §4.2「**一个字段只编码一件事**」：
今天 `roe_avg` 那一列，混着年报的平均 ROE 和一季报的年化 ROE，**读的人无从知道**。

### 4.3 定下来的形状

⭐ **决定：`FinancialPeriod` 不加 `period_type`。** 加的是**它旁边的一组事实**：

```python
period_end: date       # 报告期截止 —— 已有
announced_at: date     # 公告日 —— 已有，PIT 的全部依据
# 新增：
report_kind: str | None   # "annual" | "interim" | None（不可知就留空，红线 6）
fiscal_year: int | None
```

⚠️ **为什么是可空的 `report_kind` 而不是枚举列**：BaoStock 的 `query_profit_data` 每次调用
带一个 `(year, quarter)`，所以**调用时知道**，**存下去时也知道**。
但**历史数据里可能有一期无法判定** —— 那时必须留空而不是猜。
⭐ 「一个不可知的字段必须可空」是红线 6 的原文，而 `report_kind` 的 CHECK 会是
`CHECK (report_kind IS NULL OR report_kind IN ('annual','interim'))` ——
**`IS NULL` 在前，因为 SQLite 的 CHECK 遇 NULL 判为通过**（`0011_...up.sql:64-66` 已经为
`period_end` 踩过一次这个坑并写下理由）。

## 五、这一轮已经做完的（不需要等 spec 051）

| # | 改动 | 为什么现在做 |
|---|---|---|
| 1 | ⭐ **`S-08` 补上 8 个财务指标名**（`UNPUBLISHED_NAMES`，16 个拼写） | **实测的盲区**：把 `roe_avg ?? 0` / `revenue ?? 0` / `net_profit ?? 0` 三行写进真实前端源，`S-08` 报 clean。这三行是**宪法 §4.4 逐字**。⇒ 修完同一探针 **RED，3 条** |
| 2 | 四处「十个指标」改成八个（`financial.py:5`、`:139`、迁移 `:45`、`spec 043:54`） | 我自己读了 `:436-443`：**八个，一行一个**。⇒ 现在全仓「ten metrics」类断言剩 **0** |
| 3 | 计划的三处修正 | 见文末 |
| 4 | `S-17` 的两个未登记孤儿 | `/schema/quadrants` 实测是**被取代**（`DecisionReview.guidance` 每行都带同一句话）；`/capabilities` **故意不登记**，让它继续被报 |

⚠️ **第 1 条的理由值得单独说**：本项目为「未成熟结果留空」建了 `S-08`，
而**财务数据是这个产品里最典型的未成熟结果**（公告未到 ⇒ 没有值），
却**不在词表内**。⇒ **真正的风险不是「门禁拦住我」，是「门禁以为拦住了我」**（`F-218`）。

## 六、验收

| # | 断言 | 形态 |
|---|---|---|
| A1 | `MetricStatus.NOT_ANNOUNCED` ↔ `CriterionVerdict.NOT_ANNOUNCED` 双射完整 | 单测（`_VERDICT_FOR_STATUS` 是全覆盖） |
| A2 | 一条财务判据在 `as_of` 早于公告日时**不**说「还差 N 根日线」 | 单测（`criterion_sentence`） |
| A3 | 新句子里**没有任何时间预测**，且**携带最新已公告报告期** | 单测：断言句中不含「天」「周」「个月」 |
| A4 | `report_kind` 为 NULL 时渲染留空，且 CHECK 允许 | 变异检查 |
| A5 | ⭐ **重述一次后 `as_of` 仍返回旧值**（`announced_at <= as_of` 取数，**而不是 `period_end <= as_of`**），**不是 `trade_date`** | 变异检查（把条件换成 `trade_date` 必须变红） |
| A6 | `/capabilities` 对 `financial` 不再说 `pending` | 单测 |
| A7 | `TodayPage.tsx` 不再说「财务数据源尚未接入」 | 单测（文案断言） |

## 七、明确不做

- **不接 `peTTM` / `pbMRQ`** —— `spec 043:127-136` 已经写了理由：接它需要先决定它属于哪个 `Dataset`，那是另一个决定
- **不自动拉取** —— 「全市场定时拉取是招来封 IP 的做法」（`spec 043`）
- **不做第二财务源** —— 宪法 §4.5 要求三源互备，而 `financial.py:367-371` 诚实写着
  「D4 的唯一财务源，**没有主源可降级**」⇒ **这是一个被记录在案的差距，不是一个假装存在的机制**
- **不在本轮写代码** —— §三 §四两个决定会改 `domain/` 的枚举与文案，而它们各自都该先有单测

## 八、上游计划被实测推翻的三处

| 原写的 | 实测 | 为什么会错 |
|---|---|---|
| `financial_reports` 表 + **12 约束** | **8**（`constraints.json:148-159`）/ **9**（迁移 `:70`，含复合主键） | ⭐ **12 从 SQL 里推不出来** —— 它只有一个出处，没有推导 |
| `default_router()` 加 `BaostockFinancial` | ⭐ **照做会 mypy 失败** | 那个列表是 `list[MarketDataProvider]`，而财务实现的是**第二个协议** `FinancialDataProvider`（`financial.py:157`）；真正的改动点是 `router.py:149` 的签名 |
| 「整栈已交付，只差没插」 | **还差九处**，其中两处是设计决定 | 见 §二、§三、§四 |

⚠️ ⭐ **三处的共同形状：我在没有打开文件的情况下写了具体数字和具体做法。**
「先量」这条纪律，量到的是**数字**为止 —— **做法也要量**（读签名、读类型、读词表），
而上一轮我只量了前者。⇒ 这条补进 `.ai/README.md` 的纪律清单。