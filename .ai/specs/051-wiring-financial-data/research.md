# 051 调研 · 时点正确性与双时态数据

> 写给：`.ai/specs/051-wiring-financial-data/spec.md` 的两个设计决定
> 日期：2026-10-02 · **结论：设计是对的，术语可以对齐，有一处决定要改，一处缺口要记名**

⚠️ **这一份的价值有三块，顺序即重要性：**
① 证明 `financial_reports` 的形状不是发明，而是**双时态表的标准形态**；
② 给 spec 051 的第一个决定补上一个更好的形状（原来只有布尔，现在是带事实）；
③ 指出**回看偏差的第三种经典形式而本仓没有对应机制** —— 它此前不在任何待办里。

---

## 一、结论先行

| # | 问题 | 调研结论 |
|---|---|---|
| 1 | `announced_at` + `fetched_at` 都在主键里、两个 append-only 触发器 —— 这是自创的吗？ | ⭐ **不是。这是双时态表的标准形态**，本仓的命名与文献一致 |
| 2 | 「该指标有这个数据但那天没公告」要不要给时间预测？ | ⭐ **不要，而且文献给了更强的理由**（见 §四） |
| 3 | 新的判据状态该带什么？ | ⚠️ **我原来设计成布尔，调研说要带一个事实** —— 已改（§四） |
| 4 | 还有什么回看偏差的形态我们没防？ | ⭐ **有，第三种，而且它不在任何现有待办里**（§五） |

## 二、`financial_reports` 是双时态表，而本仓的命名已经对上了

三份独立来源给出同一套术语：

| 来源 | 术语 | 本仓的列 |
|---|---|---|
| Fowler / Wikipedia | **valid time**（事实何时为真）· **transaction time**（何时入库） | `period_end` · `announced_at` + `fetched_at` |
| IBM Db2 | **business time** · **system time** | 同上 |
| Financial Data API（⭐ **一家以 PIT 为卖点的数据商**） | **described period** · **knowledge time** · **vintage cutoff** | `period_end` · `announced_at` · `as_of` |

⭐ **三个来源的「知识时间」都等于本仓的 `announced_at`**，而 Financial Data API 的
`as_of` 定义逐字就是本仓 `as_of()` 在做的事：

> Vintage cutoff — `as_of` — **the latest vintage known on or before a timestamp**
> — *Use when you are reconstructing a point-in-time snapshot*

⚠️ ⭐⭐ **一处差异要说清**：标准双时态是**四个**时间列
（`VALID_FROM` / `VALID_TO` / `TRANSACTION_FROM` / `TRANSACTION_TO`），本仓只有三个、没有 `TO` 列。

**这不是缺陷，是一个范围更窄的声明**：本仓**从不算「在我们开始看之前，世界是什么样」** ——
它只回答「截至 X 日我们知道什么」。⇒ **半开区间换成「单点查询 + 开区间上界」**，
而这两件事在本仓的用法里是等价的。

⭐ **而这个更窄的声明是正确的**：`VALID_TO` 的存在是为了查询历史区间，
而本仓的产品形态是「一条决策 + 一个 as_of」，**不是一个时间旅行界面**。

### ⭐ 一个具体的同类实现

> For macro data, use point-in-time databases like **ALFRED** rather than the
> latest-revised series from FRED. For corporate fundamentals, use **as-reported data with
> filing date timestamps rather than as-restated data**.

⭐ **ALFRED 是 FRED 的时点版本** —— 本仓的 `financial_reports` 就是这个东西的 A 股版。
⇒ 「主键带 `announced_at` + 重述写成新行 + 不许 UPDATE」**不是本仓的发明，是这条路上的标准做法**。

## 三、回看偏差的量级，取决于它有没有跨过阈值 —— 而这正是本产品的形态

⭐⭐⭐ 文献里最有价值的一句：

> **A 0.1-point revision that nudges a value from just below a trigger to just above it
> doesn't change your data by 0.1. It changes your backtest's answer from no to yes.**

⚠️ **「trigger」这个词就是本产品的 `KillCriterion`。**

⇒ 所以「重述只有 0.1，可忽略吗」这个问题**在本产品里是错的问法**：
读者写下的是阈值，而**判据的结果就是二值的**。一次重述把 `roe_avg` 从 14.9 推到 15.1，
**判据从「没越过」变成「已越过」** —— 而 0.1 的修正被宣称是可忽略的。

⭐ **这给了 `announced_at` 进主键一个远比「严谨」更强的理由**：
**不是因为重述大，而是因为本产品只读阈值两侧，而阈值附近的任何移动都是一次翻转。**

### ⭐ 由此得到一个可测的要求（`as-of join` 的 `leak` 列）

一篇 2026-06 的文章给出了把「偏差」变成**一个数**的做法：对每个 `(决策日, 报告期)`，
同时算出

```
known_value   = series.as_of(period, decision_date)     <- 无回看偏差
latest_value  = 我们今天读到的值                          <- 回看偏差
leak          = latest_value - known_value                <- 偏差本身
```

⭐ **本仓可以照这个写测试**：把一条财报**重述**一次（同一 `period_end`，更晚的 `announced_at`），
然后断言 `as_of(重述前的日期)` 返回**旧值**。

⇒ **那就是一个 MUST-RED 的变异**：把 `announced_at <= ?` 换成 `period_end <= ?` 或去掉
这个条件，它必须变红。⭐ 而**只测「没有重述」的路径永远抓不到这个 bug** ——
**无重述时两条路径给出同一个答案**（`F-202` 的形状：只有重建缺陷的形状才能证明门禁理解形状）。

## 四、spec 051 第一个决定的形状要改：布尔 → 一个事实

我原来定的形状是「新状态 `NOT_ANNOUNCED`，不给任何时间预测」。**前半句对了，后半句不够。**

⭐ Financial Data API 的措辞给出了更好的形状：

> **Treat `period` as the x-axis of your chart and `as_of` as the lens you view it through.**
> The period tells you *which* point you are plotting; the cutoff tells you *which vintage*
> of that point you are allowed to see.

⇒ **读者需要的不是「还没公告」这四个字，是「你当时能看到的最新是哪一期」。**

| | 原来（布尔） | 改成（带事实） |
|---|---|---|
| 状态 | `NOT_ANNOUNCED` | `NOT_ANNOUNCED`（名字不变） |
| 携带 | 无 | ⭐ `latest_announced_period_end: date` |
| 句子 | 「这一期还没公告」 | 「2026 中报在 2026-09-20 之前没有公告；你当时最新能看到的是 2025 年报」 |

⚠️ **而这仍然不含任何时间预测** —— 它说的是**已经发生的事**，不是**将发生的事**。

⭐ **这一条正好用上 `providers/financial.py:372-377` 已有的实测**：公告滞后 25 / 46 / 93 天，
所以**任何「大约 N 天后」都是编的**（`spec 043:41-45` 已因此推翻官方文档的「约 2 个月」一次）。
⇒ **新句子里不出现任何时间量**，这不是谨慎，是有测量支撑的。

## 五、⚠️ 第三种经典回看偏差，本仓没有机制，而它此前不在任何待办里

CFA 的教材把回看偏差列成三种，其中两种本仓已防，**第三种没有**：

| # | 形态 | 本仓的机制 |
|---|---|---|
| 1 | **reporting lag**（报告有滞后） | ⭐ `announced_at` 独立一列 + `announced_at <= as_of` |
| 2 | **data revisions**（数据被重述） | ⭐ 主键含 `announced_at` + 两个 append-only 触发器 + 重述写成新行 |
| 3 | ⭐ **index additions**（指数成分被事后补进数据库） | ❌ **没有成分变更历史表** |

第 3 种的机制描述：

> Data vendors often add new companies to their database. When they do so, they also include
> past financial statements dating back to several years. An analyst backtesting with the
> updated database would use information on firms that were not originally in the database
> during the period.

⚠️ **本仓今天不做「指数成分」这个概念**（没有指数页、没有成分表），所以**现在没有这个 bug**。

⭐ **但它必须被记名**，因为 `status.md` 的 D4 行写着「**行业/成分变更历史表（仍未开始）**」，
而这一行的原因**此前没有写**。⇒ 现在它有了一个名字、一个来源、和一个判断：
**它是一个真实缺口，但缺口的原因是「产品里还没有那个概念」，不是「漏做了」。**

## 六、另外两条可借鉴的实践

### ⭐ 时间参数写错要**报错**，不能忽略

> Unknown query parameters fail closed with `bad_request`, so **a typo in a time parameter is
> rejected rather than silently ignored**.

⚠️ 本仓的 `as_of` 是读者自己写的字符串（`api.ts:177` 注释：「Point-in-time cutoff (YYYY-MM-DD),
not a deadline」）。⇒ **`2026-9-20`（一位月份）今天是静默通过的**，而它比 `2026-09-20` 小，
会让 `announced_at <= as_of` 少取一段报告。⚠️ **一个时间参数写错，让判据少看一期数据，而没有任何报错。**

⇒ 这条已记进 spec 051 的「明确不做」旁边的待办：**接线时顺带把 `as_of` 的解析改成 fail closed。**

### 特征库里的同一件事

> Feature stores call it **point-in-time correctness**. Tecton, Feast, and friends do an
> **as-of join** between feature values and their labels precisely so a model never trains on
> a feature value that postdates the label.

⇒ 判据就是 label，财务指标就是 feature value，而**本仓要做的是同一个 as-of join**。
⇒ **本仓的领域词汇（`as_of` / `announced_at` / 判据）与这条行业实践可以对上**，
这也是 spec 051 值得照着做的理由。

## 七、这一份改变了什么，没改变什么

| | |
|---|---|
| ⭐ **改了** | `CriterionVerdict.NOT_ANNOUNCED` 要**携带 `latest_announced_period_end`**，不是一个孤立的布尔 |
| ⭐ **确认了** | 双时态表 + append-only + `announced_at` 进主键 —— 是标准做法，不必再论证 |
| ⭐ **新增了一条可测的变异** | 「重述一次，断言 `as_of` 返回旧值」—— **只测无重述的路径永远抓不到** |
| ⭐ **记名了一个缺口** | 指数成分历史 —— 现在它有来源、有原因、有判断 |
| ⭐ **新增一条待办** | `as_of` 的解析要 fail closed（一个错字 = 少看一期，无报错） |
| ⚠️ **没改** | 不给时间预测 —— 调研把这条从「谨慎」升级为「有测量支撑」 |
---

## 八、第二轮调研 · 一个目录里指标的「粒度」不同，而行业有一条我正要违反的规矩

> 写给：spec 051 的接线部分（`MetricReading` 怎么加字段）
> 日期：2026-10-02 · **结论：我要做的事违反了一条标准建模规矩，而那条规矩给了正确的形状**

### 8.1 我要做什么，为什么它是错的

`MetricReading` 是一个平铺的 frozen dataclass：`value` / `as_of` / `period: int | None` /
`bars_available: int | None`。**24 个行情指标的 `period` 是「根日线数」**，
而 `criterion_sentence.py` 拿它算 `period - bars_available`。

⚠️ **而 8 个财务指标的「period」是报告期。** 名字一样，单位不同。

> 2. Declare the grain – define exactly what a single fact-table row represents;
>    **different grains must not be mixed in one table.**
> — *Fact table (Wikipedia), the second of the seven design steps*

⚠️ **`MetricReading` 就是一张读数的事实表，而「把 24 个瞬时读数和 8 个期间读数放进同一张表」正是那一条禁止的事。**

### 8.2 为什么财务指标是另一个粒度（不是「多一个字段」的琐事）

> The **periodic snapshot grain** corresponds to a predefined span of time,
> **often a financial reporting period**. The measured facts summarize activity
> **during** or at the end of the time span.
> — *Kimball Group, Fact Tables*

⭐ **逐字就是本产品的情形**，而且最后半句给出了实质理由：

> **`roe_avg` 的 2025 年报值和 2026 中报值是两个不同的数，而每一个都只在它所属的那段时间里成立。**

⚠️ 这不是「顺手把期号也带上」。⭐ **值与它的期间是同一个东西的两半** ——
`as_of`（哪天知道）**不能**替代 `period_end`（说的是哪一段）。两个日期轴都在 `financial_reports` 里，
是因为它们回答两个不同的问题，不是同一个问题的两次采样。

### 8.3 ⭐ 标准做法里有一样东西，这个产品必须**拒绝**

> Periodic snapshot fact tables are uniformly dense … **even if no activity takes place
> during the period, a row is typically inserted in the fact table containing a zero or null
> for each fact.**

⚠️ **这正是 `S-08` 存在的理由。** 行业标准做法是「这一期没数据也插一行零」，
而这个仓库刚刚把 `roe_avg ?? 0` / `revenue ?? 0` / `net_profit ?? 0` 三行判成 RED（`005e82d`）。

⇒ **「那一期没有公告」必须是「没有这一行」，不是「有一行全是 null」。** 这不是风格差异，
是本产品的红线与行业默认做法正面冲突，而冲突已经发生过一次、代价是三行假绿。

⭐ **而这正好也是为什么 `NOT_ANNOUNCED` 要携带「最新已公告期」而不是一个布尔**（§四）：
在密集化的标准做法下，缺的那行什么都不告诉你；而在 append-only + 稀疏的本仓里，
「没有行」是沉默，「最后一行是哪期」才是事实。

### 8.4 ⭐ 顺带确认了 append-only 的代价，而代价是文献明说的

> If an average claim is changed on twenty days during its life,
> **the time-stamped snapshot will be twenty times bigger** than the standard accumulating snapshot.

⚠️ **这是本仓「主键带 `announced_at` + 重述写成新行」的直接成本，文献把它算出来了。**
⇒ 它现在有名字、有数字、有出处，而不再只是一句「严谨一点」。
（`financial_reports` 的行数会随重述次数线性增长，**这个仓每只股票一年只有个位数行，
所以这个交换在本仓是划算的** —— 结论靠量级，不靠品味。）

### 8.5 由此得到的形状：一个类型，但**必须自带判别式**

| | 做法 | 判定 |
|---|---|---|
| A | 保持平铺，`period_end: date \| None` 加进去 | ⚠️ **违反 §8.1** —— 读者无法从一行说出它是哪个粒度 |
| B | 拆成 `PriceReading` / `FinancialReading` 两个类型 | 守规矩，但 `MetricReading` 构造点与消费点都要改 |
| C | ⭐ **一个类型 + 一个判别式**，且**判别式在类型上，不靠「哪个字段是 null」推断** | 守规矩的实质 |

⭐ **为什么 C 而不是 A**：§8.1 那条禁令的实质是
「同一张表里不同粒度的行**无法区分**」——而文档化的例外正是
「行**自带**区分手段时，那张表是退化的（degenerate）」。

⚠️ **而 A 恰好落在禁令里**：一个 `period_end` 可空、其余字段可空的平铺记录，
它的粒度要靠「哪个字段非空」来猜。⭐ **而这正是会产出撒谎句子的那一种推断** ——
`criterion_sentence.py` 的 `warming` 支已经在用 `period - bars_available` 猜单位了，
加一个财务分支进去就会说「还差 -8 根日线」。

⇒ **判别式必须是一个具名字段（枚举），而不是空值模式。** 「这一行是哪种粒度」是事实，
「这一行有哪些空字段」是偶然。

### 8.6 这一份改变了什么

| | |
|---|---|
| ⭐ **改了** | 加字段的方式从「加一个可空字段」改成「加一个判别式 + 按它分派的属性」 |
| ⭐ **确认了** | `financial_reports` 的形状是 **periodic snapshot grain**，而这个术语以后可以在规格里直接用 |
| ⭐ **拒绝了行业默认做法** | 缺的那期**没有行**，而不是「一行全 null」—— 冲突已发生过一次（`S-08`） |
| ⭐ **给 append-only 记了代价** | 文献说重述 20 次 = 20 倍行数；本仓量级下这个交换划算，**结论是量出来的** |
