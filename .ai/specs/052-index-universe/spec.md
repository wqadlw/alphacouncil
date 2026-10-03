# 052 · universe：沪深300 成分史

> 主人的原话：「做一个板块把沪深300 的所有股票信息导入到一个股票池里面」，
> 随后两轮收窄：「**只要是在沪深300 的榜单出现的**，把K线成交量，等等拉过来」，
> 第三轮是执行令：「把历史数据拉过来」。
>
> **「出现过的」这三个字把范围从 300 变成了并集**，而这一条决定了下面几乎所有设计。

---

## §〇 这个板块要解决的那个缺口

`.ai/specs/008-capability-matrix/spec.md:22` 用一句实测结论写下了现状：

> **`instruments` 数据集当前无人声明也是事实——标的清单目前来自用户手工输入，矩阵如实反映。**

⇒ 本板块就是去把它填上。`Dataset.INSTRUMENTS`（`providers/base.py:41`）占能力矩阵 15 格中的 3 格
（sh/sz/bj），三格都是 `pending`，因为**四个 provider 没有一个声明它**。

而 `tests/unit/test_capability_matrix.py:49-51` 把那三格写死成 `pending`——
**那份写死的表会因本板块变红，而它是故意的**（同一个文件 `:34-38` 记着 `BaostockFinancial` 接入时它变过一次红）。

⚠️ 同时这个板块会填上第二个洞，而这个洞是别人实测出来的：

```
frontend/e2e/pool-ambiguity.spec.ts:88-90
  ⭐ InstrumentDetailRead.name 对每个标的都是 None（实测 sh/000001、sz/000001、sh/600519）
```

⚠️ 而 `frontend/src/PoolPage.tsx:63-64` 把原因写得很清楚：

> A version of this map that carried instrument names would be a different table with a
> different contract, and it would need a name source this product does not have.

⇒ **本板块就是那个 name source。**

---

## §一 三处必须先纠正的假设（子代理盘点 + 我的实测）

### 1.1 ⚠️「池」已经被占了，而且不是这个东西

全仓盘点（`explore` 子代理，2026-10-03）：

| 事实 | 位置 |
|---|---|
| 路由 `#/pool`，中文标签「关注池」 | `frontend/src/routing.ts:54,95` |
| 页面 | `frontend/src/PoolPage.tsx:72` |
| 后端前缀 | `/api/v1/watchlist`（`api/routes/watchlist.py:41`，5 个端点，**无 DELETE**） |
| 表 | `watchlist_events`（`0001_initial.up.sql:73`，append-only 事件日志） |
| 视图 | `watchlist_current`（`0001_initial.up.sql:103`） |
| 领域模块 | `domain/watchlist.py`（docstring 标题就是「why the pool is an event log, not a table with a column」） |

⚠️ **两个「池」不是同一个东西**，四个维度都不同：

| | 关注池（watchlist） | 本板块（universe） |
|---|---|---|
| 成员由谁定 | **读者**手输 ticker | **数据源** |
| 每行必须有理由吗 | **强制**（`WATCHLIST_REASON_REQUIRED`，`domain/watchlist.py:225-250`） | 没有「理由」这回事 |
| 时点性 | 无（只有用户动作时刻 `occurred_at`） | ⚠️ **成员资格本身是时点事实** |
| 目的是什么 | 逼读者写下**为什么**关注 | 提供一个可检索的客观集合 |

⇒ **本板块命名为 `universe`，不用 `pool`。** 理由不只是避免混淆：
`routing.ts:70-83` 已经写死了「`ROUTES` is already the **single declaration of what a view is**」——
一个概念两个名字是这仓库明令禁止的形状。

### 1.2 ⚠️ 12 个迁移、25 张表，**零**张与「一堆标的的集合」有关

盘点逐张列了全部表（`instruments` / `watchlist_events` / `watchlist_current` / `decisions` /
`audit_log` / `market_cache` / `cards` / `card_symbols` / `card_events` / `card_schedule` /
`card_reviews` / `decision_review_state` / `reviews` / `notes` / `note_note_symbols` / `note_tags` /
`note_links` / `note_schedule` / `note_reviews` / `lessons` / `lesson_schedule` / `lesson_reviews` /
`lesson_promotions` / `financial_reports` / `notifications_sent`）。

⚠️ 最接近的两个先例是 `card_symbols`（`0003:62`）和 `note_note_symbols`（`0007:73`），
但它们是「**一张内容卡指向若干标的**」，语义是**归属**不是**成员资格**。

⇒ **本表是新东西，不是第二份。**

### 1.3 ⚠️ `instruments.name` / `name_source` / `name_fetched_at` 三列存在但**从未被写过**

`0001_initial.up.sql:31-56` 的表里已经有这三列，还带一条 provenance rule：

```sql
CONSTRAINT instruments_name_provenance_check
    CHECK (name IS NULL OR (name_source IS NOT NULL AND name_fetched_at IS NOT NULL))
```

而 `repositories/instruments.py:114-118` 的 INSERT 只写 4 个值，`InstrumentRow`（`:35-43`）也不暴露它们。

⚠️ **但本板块仍然不改 `instruments`。** 理由不是「怕破坏 append-only」，是更强的一条：

> **⭐ 名字本身是时点事实。** 一只票被判 ST 时名字会变（`闻泰科技` → `ST闻泰`），
> 摘帽又变回来。而 `instruments.name` 是**一列永不改写的字**——
> `repositories/instruments.py:7-12`：「**A row is never amended.**」

⇒ **把一个会变的事实放进一个不许变的列，它进去那天就开始撒谎。**
⇒ 名字存本板块自己的表，带自己的 provenance（§四）。

---

## §二 实测：这个接口到底是什么

### 2.1 ⚠️ 官方更新日志说的限制是错的，我上一轮据此给你报的「缺口」不存在

⚠️ **我自己的错，记录在此**（`F-223`）：baostock 帮助文档的更新日志有一句
「新增2006年01月-2018年09月指数成分股数据」。我据此推断「成分股数据只到 2018-09」，
并把这个缺口作为一个待决问题报给了主人。

**实测否证**（`2026-10-03`，已装 baostock `0.9.4`）：

| 探针日 | 行数 | vendor `updateDate` |
|---|---|---|
| `2015-06-30` | 300 | `2015-06-29` |
| `2018-09-28` | 300 | `2018-09-24` |
| `2018-10-31` | 300 | `2018-10-29` |
| `2024-03-15` | 300 | `2024-03-11` |
| （今天） | 300 | `2026-09-28` |

⇒ **2018-09 之后的数据完整。历史是全的。**
⭐ 而那条更新日志说的是**指数成分股数据**这个大类的起始，**不是这个端点的截止**。
**一个 changelog 的一句话被我读成了端点的边界——这与 `data-sources.md:138` 记的
「已知骗人方式」是同一族错误：我拿一个二手描述当一手事实，而端点就在本机。**

### 2.2 ✅ 时点性成立，且被两次定期调整夹测证实

依据是中证指数官方《沪深300 指数编制方案》6.1：「样本调整实施时间分别为每年 6 月和 12 月的
**第二个星期五的下一交易日**」。

| 探针 | `updateDate` | 结论 |
|---|---|---|
| `2025-06-11/12/13` | `2025-06-09` | 调整前 |
| `2025-06-16/17` | `2025-06-16` | ✅ 生效（6月第二个周五=6/13，下一交易日=6/16） |
| `2025-06-13` vs `2025-06-16` | — | **-7 / +7**：闻泰科技、璞泰来、华兰生物、东方雨虹、三七互娱、恩捷股份 出；渝农商行、沪农商行、龙芯中科、国货之宝、领益智算、软通动力 入 |
| `2025-12-11/12` | `2025-12-08` | 调整前 |
| `2025-12-15/16` | `2025-12-15` | ✅ 生效（12月第二个周五=12/12，下一交易日=12/15） |
| `2025-12-12` vs `2025-12-15` | — | **-11 / +11** |

⇒ **不是「无论查哪天都回今天这份名单」。** 探针脚本报的是 `error_code='0'` + 300 行 + 不同的集合。

### 2.3 ⚠️ 但 `updateDate` **不能**当生效日用——五个值全是周一

| 探针日 | `updateDate` | 那天是 |
|---|---|---|
| `2015-06-30` | `2015-06-29` | 周日 |
| `2018-09-28` | `2018-09-24` | 周一 |
| `2024-03-15` | `2024-03-11` | 周一 |
| `2025-06-16` | `2025-06-16` | 周一 |
| `2025-07-11` | `2025-07-07` | 周一 |

⚠️ **⇒ 它是每周一批的入库戳，不是生效日。**
而 §2.2 里 `2025-06-16` 与 `2025-12-15` 恰好同时是编制方案的生效日，
**只因为那两天的生效日本身落在周一**。任何一次生效日落在周二的调整，两者就会错开。

⇒ **本规格不用 `updateDate` 推算任何日期。** 它只作为一列
`vendor_update_date` 原样存下来，含义写成「源自己说的那一句，不解释」（§四）。

### 2.4 ⚠️ 这个源的诚实描述是「周分辨率、至多 7 天滞后」，不是「时点」

实测 `2025-07-07`（周一，非调整日）到 `2025-07-11`（周五）四个工作日的
`updateDate` 全是 `2025-07-07`，集合完全相同。

⇒ **答案是一个阶跃函数，台阶落在周一。**
⇒ ⚠️ **周三的一次临时调整（退市/合并/ST）对任何调用者都不可见，直到下周一。**
**所以更细的网格救不了它**——按天探会返回按周探已经返回的东西，只是多花 5 倍出网量。

⇒ 这句必须写进数据源文档和界面，**因为它是这个源的能力上限，不是我们的实现取舍**。

### 2.5 ⚠️ 探针过程中实测到的两个失败模式

| 现象 | 处理 |
|---|---|
| `[WinError 10053]` 连接被中止（连续出网约 45 次后） | 重试 + 换连接 |
| `query_hs300_stocks('2025-06-31')` 返回 `error_code='10004010'`「日期格式不正确」 | ⭐ **非法日期不是「那天没有成分」** |
| `2025-06-22` 返回 `error_code='10002007'` | 同上 |

⚠️ **把一次失败读成「300 只全退了」会写进一条自信的错记录，而且任何地方都不报错。**
这正是 `S-08` 的形状，摄取命令的契约必须写在类型上（§六）。

---

## §三 成分股变动的节奏有三种，不是一种

从中证指数官方《编制方案》核对：

| 变动类型 | 何时 | 出处 |
|---|---|---|
| **定期调整** | 每年 **6 月和 12 月**第二个星期五的**下一交易日** | §6.1 |
| **临时调整** | 退市（§7.5）、分立（§7.3）、破产（§7.6）、长期停牌（§7.4）—— **任何时候** | §7 |
| **风险警示剔除** | **每月**第二个星期五的下一交易日 | §7.7 |

⚠️ 所以成分集合的边界**不由日历决定，由事件决定**，而 `effective_to` 可能是月中某一天。
⚠️ 缓冲区规则（§6.5，前 240 名候选 / 前 360 名老样本）解释了为什么单次换入换出是个位数
（实测 7 与 11），但它也意味着**同一次调整里有进有出，而这个「进」和「出」是两件事**——
一张只有「当前 300 只」的表无法表达「它 2019 年在里面、2023 年被摘出去了」。

⇒ **本表是区间式的，且最后一行的区间右端是开放的**（§四）。

---

## §四 表：两张，不是三张

### 4.1 ⭐ `index_constituents` —— 粒度是「一段被观察到的成员资格」

```sql
CREATE TABLE index_constituents (
    index_code         TEXT NOT NULL,
    market             TEXT NOT NULL,
    code               TEXT NOT NULL,
    -- ⚠️ 第一天可能早于本产品开始问，所以**可空**
    -- ⚠️⚠️ 最后一行的右端是开放的：这只票**现在还在指数里**
    name_as_observed   TEXT NOT NULL,
    source             TEXT NOT NULL,
    vendor_update_date TEXT,
    fetched_at         TEXT NOT NULL,
    PRIMARY KEY (index_code, market, code, first_observed_on, source, fetched_at)
) STRICT;
```

⚠️ **`PRIMARY KEY` 含 `first_observed_on`** —— 否则一只票 2019 进、2023 出、2025 又进
会在第二次进的时候撞主键，而那**是三个不同的区间**（`0011_financial_reports.up.sql:112-120`
为同一件事留过一整段注释：`fetched_at` 进主键是「被一个测试逼出来的」，因为
「再抓一次」是一次**新的观察**，该有自己的主键位置）。

### 4.3 ⭐⭐ 为什么**没有** `effective_from` / `effective_to`

⚠️ **这是本规格最重要的一条，而且它是一次否定。**

我们观察得到的是**一个窗口**：`first_observed_on`（第一次在周一网格里看见它）
到 `last_observed_on`（最后一次看见它）。而**生效日落在这两个日期之间的某一天，我们不知道是哪一天**
——§2.3 已经证明 vendor 的 `updateDate` 是周一入库戳，不能用。

⇒ 写 `effective_from = first_observed_on` 会让读者以为「它是这天进的指数」。
**而那一天只是「我们第一次问，它在里面」。** 真实生效日在 `[first_observed_on - 7d, first_observed_on]` 里。

⭐ 这个决定的一般形式，就是 `0011_financial_reports` 已经做过的那件事的反面：
那里是把**合成**的日期**拆开**（`period_end` 与 `announced_at` 分两列，`0011:18-19`）；
这里是把**推算**的日期**拿掉**。⚠️ 合成会丢信息，推算会**造信息**——后者更坏，因为它不可见。

### 4.2 ⭐ `index_universe_sweeps` —— 「这份数据有多新」也是一张表

```sql
CREATE TABLE index_universe_sweeps (
    index_code  TEXT NOT NULL,
    -- grid 覆盖到的最晚一天，也就是「我们知道的最后一天」
    fetched_at  TEXT NOT NULL,
    -- 一**周**一个，所以两次扫描之间没有第四种粒度
    -- 本次扫描**失败**的网格点数。⭐ 存下来而不是只打日志：
    -- 一个不完整的扫描如果看起来完整，读者无法分辨
    failures    INTEGER NOT NULL,
    PRIMARY KEY (index_code, grid_point)
) STRICT;
```

⇒ 「当前成分」定义为 `last_observed_on = (SELECT max(grid_point) FROM index_universe_sweeps)`。
⚠️ **而这个查询必须同时显示 `grid_point`**——
`.ai/data-sources.md:137` 记着「僵尸报价」的成因是「成交价 0、价格定格在迁移日，
**不报错、不崩溃，只是安静地骗人**」。一个不说自己多旧的池子，是它的同族。

---

## §五 provider：第三个协议

⚠️ 「沪深300 成分股」既不是行情也不是财务。`providers/router.py:159-165` 已经把这个道理写成
`financial` 独立列表的理由：

> `financial` is a **second protocol**, and it is a separate list on purpose.
> `providers/financial.py:160-164` is why: a financial source cannot serve `get_daily`,
> and folding it into one list would force it to declare a capability it does not have.

⚠️ 而成分源同样不能服务 `get_daily`，**所以它是第三个同样的理由**，不是第三种借口。

⇒ **新增 `providers/universe.py`，定义 `UniverseDataProvider`。**
⇒ 路由改动三处，缺任何一处都会说谎或编不过类型检查：

| 位置 | 动作 | 漏了会怎样 |
|---|---|---|
| `providers/router.py:150-158` | 加 `universe: Sequence[UniverseDataProvider] = ()` | ⚠️ 直接加进 `providers=[...]` 会 **mypy 失败**（`.ai/README.md:82` 记着这个坑） |
| `providers/router.py:386-395` `_declarations()` | 并入 `[*self._providers, *self._financial, *self._universe]` | ⭐ **`/api/v1/capabilities` 会一直说 `instruments` 是 `pending`，而那句话在 provider 存在的前提下是假的**（`spec 051/spec.md:34` 踩过一模一样的坑） |
| `checks/rules/no_raw_http.py:215-228` `CONSTRUCTION_SITES` | 加 `Path("providers/universe.py")` | ⚠️ 新文件 `import baostock` 会被 **S-01** 报 import 违规（`baostock` 已在 `NETWORK_MODULES:97-125`，理由写在 `:104-108`：它不是一个传输层，是一个**自己开 socket 的库**，10030 端口） |

⭐ **替代方案：把成分代码写进已有的 `providers/financial.py`，那已在 `CONSTRUCTION_SITES` 里，零改动。**
⚠️ 但它违反该文件 `:362-366` 自己的声明纪律（「`FINANCIAL` and nothing else」）。
⇒ **选新文件，并把那个纪律的边界一起改写**——比让它悄悄破例好。

### 5.1 ⚠️ `vendor_update_date` 必须原样透传

⇒ 与 `financial.py` 一致：`notes` 必填（`providers/base.py:72`），且
**对单源数据集，诚实的 note 是「没有主源可降级」**（`financial.py:364-366`）。
⚠️ 所以本 provider 的 `notes` 要说清**它与主源的差别**，而它的差别就是 §2.4 那句：
**周分辨率、至多 7 天滞后**。

---

## §六 摄取：配额、排序、断点续传

### 6.1 ⚠️ 这不是一次导入，是一条命令，而它的形状是被宪法决定的

- `constitution.md:790`：「**不做选股 / 因子 / 回测**」是永久非目标。
- `constitution.md:805`：「**任何让"判断"变轻松的改动，方向都错了**」。
- `.ai/specs/043-financial-data-source/spec.md:133`：「**不自动拉取**——全市场定时拉取是招来 IP 封禁的做法」。
- 实测：连续出网约 45 次后 baostock 开始 `WinError 10053`（§2.5）。

⇒ **本规格据此定三条，全部是为了让违规的那件事跑不出来：**

| 规矩 | 为什么 |
|---|---|
| **① 每次运行有配额上限** | ⭐ 一个「全池回填」命令如果没有上限，它就是 `spec 043:133` 禁止的那件事，只是被人手动跑了一次 |
| **② 按最近在指数里的优先** | ⭐ **部分完成仍然有用**。一个从头跑到尾 8 小时然后被掐断的命令，等于没有结果 |
| **③ 断点续传，失败不写行** | ⚠️ §2.5：不写是唯一安全的选项。写一条「那天没成分」比不写坏得多 |
| **④ 不做调度器** | ⚠️ 「定时」是把 ① 绕过去的唯一办法 |

### 6.2 K 线与「等等」——⚠️ 一处我还没解决的分叉

主人在第二轮把范围定成「把 K 线成交量，等等拉过来」。实测 baostock 的日线字段一次带齐：

```
date, code, open, high, low, close, preclose, volume, amount,
adjustflag, turn, tradestatus, pctChg, isST
```

⭐ 其中 **`turn`（换手率）、`tradestatus`（交易状态）、`isST`（是否 ST）** 都是「等等」里
「等等」的部分，**不要钱**。
⚠️ 而 `isST` 按每根 bar 的日期给出，所以「这只票被判 ST 之前」自动就是时点正确的——
而 ST 剔除是**每月**发生的（§3），正是最容易记错的那一种变动。

⚠️ **但并集规模未知，且分叉是产品级的**：

| 路线 | 出网对象 | 风险 |
|---|---|---|
| **A · baostock `query_history_k_data_plus`** | baostock（§2.5 实测会断连） | 一个池子的历史 ≈ 1500+ 只 × 数年 |
| **B · 经现有 router**（Eastmoney/Tencent） | 本仓已有 provider | ⚠️ Eastmoney `supports_batch=False`，文档原文「never ask it for a batch」「the most rate-limit-prone source」；⭐ Tencent 日线**无成交额**（`sources.py:154-156` 已验证） |

⚠️ **并集规模是决定性的数字，而它由 §六这次扫描给出。** 在那个数字出来之前不定线。

---

## §七 宪法边界：本板块是**只读参考**

⚠️ `constitution.md:802-803` 划了线：

> ✅ 降低：找数据的时间 · 记录决策的摩擦 · 想起来要复盘的难度 · 跨来源信息对齐的成本
> ❌ 不降低：判断一家公司值不值这个价 · 判断该不该卖 · **承担后果的责任**

⇒ **导入一份可检索的清单在 ✅ 这边**（那是「找数据的时间」）。
⚠️ **一旦它变成「今天该看哪 87 只」，就越到 ❌ 那边**——因为那降低的是判断的成本，
而 `constitution.md:805` 说那会让它变成红线 1（讨好用户）。

⭐ **本规格定的边界（主人 2026-10-03「可以」批准）：**

| 允许 | 禁止 |
|---|---|
| 按代码/市场/名称**检索**池子 | ⭐ **任何排序、打分、筛选出「候选」的功能** |
| 回答「它**是不是**在沪深300里」，带观察窗口与新鲜度 | ⭐ 任何「它值不值得买」的字段或措辞 |
| 成分变动史（进/出，带观察窗口） | ⭐ 把成分变动接到判据上（那会让判据依赖一个与价格无关的事实） |
| 从池子跳到该标的已有的决策/卡片/笔记 | ⭐ **池子成员身份不产生任何提醒**（`notifications_sent` 那套是「关于一件事我已经说过了」，不是「新的候选」） |

⚠️ **这条边界要写进界面，不只写进文档**——`pool.spec.ts:77` 已经在页脚放了一条红线文案
（「它不显示收益率，也不给你推荐。」），说明这个仓库认为**边界必须能被读者看见**。

---

## §八 与既有立场的关系：`data-sources.md:138` **改，不删**

⚠️ `.ai/data-sources.md:138` 有一条针对指数成分的负面立场：

> 「**当前快照**」当「历史数据」 | 指数成分 / 权重只有当前快照，用它做历史研究就是**前视偏差** |
> **没有历史时点数据时必须显式报错**，不能用当前快照代替

⚠️ **这条对东财/腾讯的端点成立**（那是本项目实测过的，`:136-137` 的僵尸报价也是实测的）。
⚠️ **但它对本板块要用的这个接口不成立**——§2.2 的夹测就是那份实测。

⇒ **处理：加一列「对 baostock `query_hs300_stocks` 不适用，附实测」，
不删原文。** 理由是这条警告本身是对的，
⚠️ 而**删掉一条对的警告比留着它更坏**——它下次会拦住一个真的只能给快照的源。

同时按 `data-sources.md:186`「新增数据源或新增端点时，必须同步更新本文件的对应表格」：

| 待更新 | 内容 |
|---|---|
| `:120` 的 `SH_INDEX` 白名单 | ⭐ **该白名单全仓零引用**（只有那一行）。⭐ 而 baostock 只服务 3 个指数（`query_hs300_stocks` / `query_sz50_stocks` / `query_zz500_stocks`，`sectorinfo.py:97/162/227`），**白名单列的 6 个里有 3 个没有源**。⇒ 要写清哪个有哪些 |
| `:174-182` 的未验证清单 | 本板块的实测结论写进去 |
| 数据源总表 | 新增 baostock 成分端点，并标它的**周分辨率**（§2.4） |

⚠️ 另记：`sectorinfo.py` 里另有 9 个未导出的 `query_*`（`query_st_stocks` / `query_terminated_stocks` /
`query_all_stock` 等），**全部 `print()` 到 stdout**，会被 **S-10 `no_print`** 拦。**不用它们。**

---

## §九 门禁与测试

| 项 | 内容 |
|---|---|
| `S-01 no-raw-http` | `providers/universe.py` 进 `CONSTRUCTION_SITES` |
| `S-04 append-only` | 两张表都要 `no_update` / `no_delete` 触发器（`0011:150-154` 是模板，理由是「一次 UPDATE 就是一次静默的重写历史」） |
| `storage/constraints.json` | 两张表的 CHECK 逐条登记 |
| `test_capability_matrix.py:49-51` | ⚠️ 三格从 `pending` 改 `usable`（或见 §十的开放问题） |
| `manifest.json` | 登记迁移 13，`$comment` 按现有体例写清「为什么这张表存在」 |
| **新测试** | ⚠️ **网格粒度**（周一探与非周一探同答）、**失败不写行**、**区间不重叠**、**并集 ≠ 当前 300**、**名字与 market/code 一致** |
| **变异** | ⭐ 至少三条：把 `first_observed_on` 换成 `effective_from` 用（应红）、把失败当空集写（应红）、把周一换成每天（应红且**测不出浪费**，所以测「同一天两次探同答」） |

---

## §十 开放问题（留给下一轮，不在这里假装已决）

| # | 问题 | 为什么还没决 |
|---|---|---|
| 1 | ⭐ **并集规模**，以及「K线成交量」走 baostock 还是现有 router | 扫描还在跑（`1083` 个周一网格）。⚠️ 在这个数字出来之前选线就是凭印象 |
| 2 | ⚠️ `("instruments","bj")` 怎么变 | ⚠️ **`bj` 之所以 `pending` 不是因为没源，是因为沪深300 没有北交所成分**——这是**关于世界的事实**，与 sh/sz 那两格「有源可用」不是同一回事。⚠️ 但 `router.py` 里 `PENDING` 的 reason 字符串是写死的（`:235-250`），要区分「无源」与「此指数不含该市场」得改 reason 的形状 ⇒ 属于产品决定 |
| 3 | ⚠️ 名字改名要不要单独一张表 | §4.1 只存**区间末端**观察到的名字。⚠️ 一只票在区间中途被 ST 又摘帽，本表表达不了。**这是已知缺口**，不是遗漏 |
| 4 | ⚠️ `pyproject.toml` 的 `dependencies` 里没有 `baostock` | ⚠️ 它是 `spec 043` 当时手工装进 `.venv` 的，而 `providers/financial.py` 已经把它用在**出厂代码**里。⇒ 这是既成事实的漏洞，补上是记录事实而非新增依赖；但按 `constitution.md` §3.2.1 仍需主人知情（已报）。⭐ **不引入 `pandas`**——`ResultData` 可逐行迭代，用不到 |

---

## §十一 记录

- ⭐ **`F-223`（新增）**：一个 changelog 的一句话被我读成了端点的边界，
  而端点就在本机可测。**症状**：我把一个不存在的缺口报给主人，并据此提出过三个选项。
  **病因**：二手描述 vs 一手实测。**与 `data-sources.md:138` 同族**——
  都是「未测量的能力被当成已知的限制或已知的许可」。
- ⭐ **`F-224`（新增）**：**五个值全是周一**这件事，第一次看时我只注意到「它和已知生效日吻合」，
  于是差点把它当生效日用。**症状**：一个意思是我推断出来的数据源字段即将变成一列日期。
  **病因**：⭐ **「吻合」不是「定义」。** 一个字段在 N 个已知真值上都吻合，
  只说明它可能是那个量的一个代理；第 N+1 个样本（`2025-07-07`，一个非调整日）就推翻了它。
  ⇒ 判据从此是：⭐ **用来定量的字段，必须有一个样本能证伪它的定义，而不只是吻合。**