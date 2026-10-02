# spec 051 · 把财务数据接上：先决定两件设计问题，再写代码

> 立项：2026-10-02 · **状态：渲染侧已落地，接线未开始** · 记录与接线现状见 `§十`
> ⚠️ 本行原写「未动代码」，而 §三/§四 的枚举、字段、句子分支**已经在树里**；盘点实测出**七个「已落地但无生产路径」**的东西，逐项列在 §十.2。
> 依据：`.ai/specs/043-financial-data-source/spec.md`（D4 本体）· `ADR-0031`
> 轮次：两轮调研（`research.md` §一~七 与 §八）· 结论与实施细节分离。
> 门禁现状：17 条静态检查全绿 · 冻结字节契约 · 本会话新增 `F-219`~`F-222` 与 `0023`
> 纪律与经验沉淀：`.ai/README.md`（纪律 7）、`research.md` §八、`regressions/0023`
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

### ⚠️ 2026-10-02 消费侧盘点后修正：**它不是双射**

原写的是「4 状态 ↔ 4 判据的双射」。**实际不是**：

```
MetricStatus       4 个   ok / warming / unknown_metric / no_bars
CriterionVerdict   5 个   crossed / not_crossed / warming / undetermined / no_bars
_VERDICT_FOR_STATUS          四个状态 → 后四个判据
evaluate() 的比较分支      CROSSED 不在这张表里生成
```

⇒ **新增一个状态仍然需要同时加一个判据**（新状态不能落到已有的判据上），
**但原因不是「要保持双射」。** 本来就没有双射可保。

⭐ 同时：**`criterion_eval.py:63` 自己的 docstring 写着「Four, and they are not degrees.」**
而它有五个成员 —— 这是一位**今天就是假的声明**，而我正要去编辑这个文件。
⇒ 一并改掉（`regressions/0011`）。

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
# alphacouncil/metrics.py   ⭐ AT THE PACKAGE ROOT, not domain/
# (一开始写成 `domain/metrics.py`。那会创出一个不存在的文件，里面会有第二份 MetricStatus ——而这正是本仓反复付代价的那一件事。)
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

## 九、消费侧盘点推翻的六处（写代码之前）

⭐ **这是纪律 6 一轮后的收益：盘点在任何代码写之前发出，它推翻了这份规格的六处**
—— 包括一处**照写会创出一个不存在的文件**，和一处**数了新代码转的那个枚举的成员数**。
若先写代码，这六处会以运行错误或门禁失败的形式出现。

| # | 原写 | 实测 | 影响 |
|---|---|---|---|
| 1 | `# domain/metrics.py` | ⭐ `backend/src/alphacouncil/metrics.py`（**包根下**） | 照写会创出假文件，里面第二份 `MetricStatus` |
| 2 | 「四个判据」 | ⭐ `CriterionVerdict` **五个**，而 `criterion_eval.py:63` 自己写着「Four」 | 数字错在规格里就已经在误 |
| 3 | `_VERDICT_FOR_STATUS` 是双射 | 4 → 后 4，`CROSSED` 由 `evaluate()` 的比较分支生成 | 保持双射本来就不是加成员的理由 |
| 4 | 「新状态自动被测」 | ⭐ **五处测试硬写了三元组**，加第四个后**不红且没被覆盖** | 只有另四处 `for state in CriterionVerdict:` 会自动扩展 |
| 5 | 新字段的形状 | ⭐ **`S-02 no_boolean_state`** 查 `is/has/was` 开头的 bool；而 `MetricFacts` 现在是 4 个可空值字段、**零 bool** | 加 `has_announced` 会**立刻红**。⇒ 字段按**事实**命名而不按**状态** |
| 6 | 「同步前端即可」 | ⭐ **`S-16` 会立刻红**，因为 `api.ts:533-538` 的 `MetricState` 是 `CriterionVerdict` 的乐观体与达 | ⇒ **两个月前那条门禁把它变成两分钟的修复**，而不是一个静默的不匹配 |

### ⚠️ 五处硬写三元组的测试（不会红，但会漏测）

| 位置 | 形式 | 加第四个「不知道」后 |
|---|---|---|
| `test_criterion_sentence.py:158-165` | parametrize **三元组** | ⚠️ 不红，新状态**未被覆盖** |
| `test_criterion_sentence.py:196-201` | **三元组** + `len(rendered) == 3` | ⭐ **不红，但语义已错** ——它本来在证「三个互不相同」，现在有四个 |
| `test_criterion_sentence.py:217-221` | 手写五行 `adjudicable[...]` | ⚠️ 不红，新状态**漏测** |
| `test_criterion_eval.py:212-220` | 2 个 True + **三元组** False | ⚠️ 不红，新状态**漏测** |
| `test_notify_webhook.py:480-486` | parametrize **三态** + 三句字面量 | ⚠️ 不红，「不发通知」这条路径**未被测** |

⇒ **会自动扩展的只有四处**：`test_criterion_sentence.py:214 / :226 / :240 / :294` 的
`for state in CriterionVerdict:`。⇒ **新状态必须把那五处改成遍历**，而不是再加一个三元组。
⭐ **第二行的 `len(rendered) == 3` 应该改成从枚举推导**：先定义「不知道」的集合
（就是非 `answerable` 的那些），再断言它们互不相同。

### ⭐ 一个不是修正、而是白拿的设计终带

`frontend/src/criterionVerdict.ts:62` 是前端对状态的**全部**行为：

```ts
crossed: metric?.state === 'crossed'
```

⭐ **没有 switch，没有 `Record<State, ...>` 映射表。**⇒ 新状态**自动落到中性样式**，而语义全部由
服务端下发的那句话承担 —— 这正是 `criterionVerdict.ts:59-61` 注里「**a state the server adds
cannot render as 「not crossed」 by omission**」的意思。⇒ **因此前端一个分支都不需要**。
---

## 十、接线前的实测盘点（2026-10-02 第二轮）

> 写代码之前派子代理把供给侧与存储侧读了一遍。⭐ **它推翻了六处我自己的说法，
> 并且找到了七个「已经落地却没有生产路径」的东西** —— 后者是本文件 `:3` 那句
> 「未动代码」漏掉的。

### 10.1 盘点推翻的六处

| # | 我写的 | 实测 | 代价 |
|---|---|---|---|
| 1 | `backend/migrations/` | ⭐ `backend/src/alphacouncil/storage/migrations/0011_financial_reports.{up,down}.sql` | 找错目录 |
| 2 | `_CatalogueEntry` 在 `:125` 附近 | ⭐ **`:138`**（`:119-132` 是四个 helper） | 行号错 |
| 3 | `today.py:254-355` 是 attention 构造 | ⭐ **`:264-365`**（`:254-261` 是 `MarketStatusRead` 的字段） | 行号错 |
| 4 | `criterion_eval.py:63` 写着「Four」 | ⭐ **已改成「Six」**（上一轮改的），本条已过时 | 沿用会改回去 |
| 5 | `financial_reports` 的约束数 | ⭐ **9**（8 具名 CHECK + 1 复合主键），`constraints.json` 登记 8 | 「12」无出处 |
| 6 | 财务指标在 `:436-443` | ✅ **完全正确**，八行一行一个 | — |

⚠️ **第 4 条是最危险的一类**：规格里的旧事实被下游当作现状引用，于是「按规格改」会把已经修好的东西改回去。

### 10.2 ⭐⭐ 七个「已落地但无生产路径」的东西（本文件 `:3` 漏掉的）

| 已存在 | 位置 | 差什么 |
|---|---|---|
| `MetricStatus.NOT_ANNOUNCED` | `metrics.py:97` | ⭐ **`read_metric()` 只有 4 个 return，永不返回它** |
| `CriterionVerdict.NOT_ANNOUNCED` | `criterion_eval.py:90` | ✅ 枚举有 |
| `_VERDICT_FOR_STATUS` 第五行 | `criterion_eval.py:142` | ✅ 有；**`evaluate()` 打不到它** |
| `MetricFacts.latest_announced_period_end` | `criterion_sentence.py:99` | ✅ 字段有；**`today.py` 从不填** |
| `sentence_for` 的 `not_announced` 支 | `criterion_sentence.py:213-247` | ✅ 两支文案齐全；**`today.py` 从不触发** |
| `MetricStateRead.latest_announced_period_end` | `today.py:139-147` | ✅ 模型有；**线上恒 `null`** |
| `_VERDICT_FOR_STATUS` 的测试 | — | ⚠️ **零**。全仓两处命中都在源码里 |

⇒ **上一轮写的那句「已声明、未可达」现在有了逐项清单，而不只是枚举上的一句注。**

### 10.3 ⭐ `period` 的单位被两处锁死为「根日线数」，而这决定了粒度方案

实测确认我上一轮的怀疑，且比怀疑的更强：

- `criterion_sentence.py:179` 把 `period` 与 `bars_available` 相减；
- **`:190` 把差值渲染成「N 根日线」**（中文字面量是硬证据）；
- `bars_available` 被 `today.py:329/337` 钉成 `len(bars)`，且 `today.py:130-138`
  与 `api.ts:558-564` 都写明它**故意由服务端算**（spec 038 的教训）。

⚠️ **给 `period` 一个季度数，`warming` 分支会说「还差 3 根日线」。**
而财务指标今天恰好会落进那一支（没有 reader）。

⇒ **`research.md` §八的判别式决定由此落地：** 加的不是「一个可空的 `period_end`」，
而是**一个说明这一行是哪种粒度的枚举字段**，按它分派属性。
⚠️ **判别式不能靠「哪个字段是 null」推断** —— 那正是产出撒谎句子的那一种推断。

### 10.4 ⭐ `today.py:315` 是那堵墙

```python
if bars is not None:          # :315
```

**判据求值入口被这一句把着。** 一条纯财务判据（`roe_avg < 0.2`）的标的完全可能没有
bars（停牌 / 新上市 / 退市整理）⇒ **今天它会被判成 `no_bars`，而真相是「这只票有财报，
只是那天没公告」。**

⚠️ **而 `no_bars` 那句话是「这个代码没有日线，这条判据没有被求值过」** ——
对一条财务判据来说这是**假话**，且是产品最不该说的那种假话。

最小改动集（盘点给出的六处，按依赖顺序）：

| # | 行 | 改什么 | 不改的后果 |
|---|---|---|---|
| 1 ⭐ | `today.py:315` | 闸门 2 从「有 bars」变成「有 bars 或有财务行」 | 财务判据被误判成 `no_bars` |
| 2 | `today.py:283-296` | 加 `financial_by_symbol` 缓存，照抄 `bars_for` 的形状（含 `:295` 的「None 也缓存」纪律 —— 财务源会封 IP） | 每条判据抓一次，32 次串行往返 |
| 3 | `today.py:316` | `evaluate()` 加第三个来源参数 | `read_metric` 看不到财务 |
| 4 | `today.py:317-338` | 补 `latest_announced_period_end`（**两处都要**） | ⭐ `sentence_for` 永远走「而这只股票我们从未记过报告」那一支，**说了一句假话** |
| 5 | `today.py:314` | 兜底 state 对财务判据不对 | 静默误判 |
| 6 | `today.py:106-147` + `api.ts:533-565` | 两边同步（`S-16` 会红） | 门禁红 |

### 10.5 `as_of()` 已经够用，不必新写查询

实测：`repositories/financial.py:146-162` 的 `as_of()` 返回的行里**已经含 `period_end`**
（`_COLUMNS` 第三项），SQL 是 `WHERE announced_at <= ? ORDER BY announced_at DESC LIMIT 1`。

⇒ **「最新已公告报告期」= `row["period_end"]`，零存储改动。**
（`history()`（`:165`）不接 `as_of`，所以「截至该日曾公告过的全部期」才是真的要新写的。）

⚠️ **但 `as_of` 是裸 `str` 且 fail open**（`:147`）—— docstring 说「schema 的 CHECK 保证它能解析」，
而**那个保证只覆盖表里的列，不覆盖传进来的参数**。`"2026-9-20"` 静默少取一段报告。
§3.5 第 2 条实测确认：**它今天还在。**

⚠️ 另有一条接线的暗坑：`BaostockFinancial` 抛的是 `ProviderIpBlockedError`（`financial.py:259`，
**裸异常**），不是 `DataResult`，**所以它永远进不了 `_record()`**，而
`_COOLDOWN_BY_CODE`（`router.py:76-80`）为 `DATA_SOURCE_IP_BLOCKED` 准备的 20 小时冷却对它无效。

### 10.6 ⭐⭐ 第二条「接线即达成」的谎言

`catalogue_labels()`（`metrics.py:225`）**全仓零调用者** —— 只在 `__all__` 与自己的定义里出现。

⇒ **8 个财务指标进 `CATALOGUE` 时，label 会自动进这张字典，而没有任何人读它。**
前端今天拿不到任何指标清单（`TodayPage.tsx` 不用它，也没有路由暴露它）。

⚠️ **这与 `TodayPage.tsx:144` 那句「公告与财务数据源尚未接入」是同一个形状**：
一句「加了目录项就能选」的推论，而接收端不存在。
⇒ 接线清单里要有一条：**指标选择器要么一起接，要么明确写下「没有选择器，判据只能手写指标名」。**

### 10.7 接下来的顺序（本轮之后的计划）

1. `FINANCIAL_CATALOGUE`（第二目录，**不动 24 个现有 reader**）+ 判别式字段
2. `repositories/financial.py` 加一个薄封装 + `as_of` 改 fail closed
3. `BaostockFinancial` 进 `default_router()`，并把 `ProviderIpBlockedError` 接进 `_record()`
4. `evaluate()` 第三来源参数（`_bars_as_of` 的对应物是按 `announced_at` 切）
5. ⭐ **那条 MUST-RED 变异**：重述一次后 `as_of(重述前的日期)` 必须返回旧值
6. `today.py` 的六处
7. `TodayPage.tsx:144` 改掉；指标选择器那条二选一写进本文件
8. `report_kind` 落库（迁移，**SQLite 的 CHECK 遇 NULL 判为通过，所以可空**）
