# 055 · 卡片的复习历史：把一个能用的函数接到读者够得着的地方

> 宪法 2.2 要求的三问在 §〇。**规格与计划分离**：本文件写「做什么、为什么」，
> `plan.md` 写「怎么做、顺序是什么」，`tasks.md` 是可勾选清单。
> ⚠️ 计划**推翻了本规格自己的一处次序**（§六），那一节记录推翻了什么。

---

## 〇 · 想做什么

**目标**：让一张卡片被复习过的每一次都能被读者看到 —— 一条 HTTP 读端点 + 一个界面。

**具体故障**：`scheduling.list_reviews()` 在 `storage/repositories/scheduling.py:402` 实现、
在 `__all__` 里导出、有测试，而**没有任何路由调用它**。⇒ 读者在复习页答完一张卡，
排程动了、`card_reviews` 多了一行，而**页面上没有任何地方能看见这一行**。

**既有机制为何不行**：
| 机制 | 为何不行 |
|---|---|
| `GET /notes/{id}/reviews` | ⭐ **存在，而且完全够用 —— 但那是笔记的。** 卡片的 `ReviewRow` 与笔记的**字段逐个相同**，只差 `card_id` / `note_id`。这套机制缺的只是「被卡片那条路调用」 |
| `GET /cards/{id}/schedule` | 只给**下一次什么时候到期**。spec 048 已经证明它不足以让界面判断状态，而它**一个字都不说过去发生过什么** |
| `GET /review/due` | ⭐ **不能推断**，理由是 spec 048 已经写下的：它只给**到期**的。排在下周三的卡不在里面，于是「已复习 4 次」永远问不出来 |
| `GET /cards/{id}` | 返回卡片本身，`CardRead` 里没有复习流水 |
| **必需还是可选** | **必需**。spec 028 提出的问题「**我复习过 5 次，为什么今天又来了**」在笔记那边被修好了，在卡片这边一个字都没修 —— 而卡片是 K3 的**主体**，笔记复习只是后来加的 |

⭐ **而这一轮量出来的不是「少一条端点」，是「少一张词汇表」。** 见 §一 之三。

---

## 一 · 量：现状（全部实测，无一推断）

> 探针跑在临时库上，用产品自己的仓储与 FSRS，不碰主人的真实数据库。
> 全部数字来自执行，**没有一个是读出来的**。

### 1.1 仓储层是好的

```
cards.create             (connection, draft: CardDraft, *, now=None) -> CardRow
sched.enroll             (connection, card_id, *, now=None) -> ScheduleRow
sched.record_review      (connection, card_id, rating, *, now=None, duration_ms=None) -> ReviewRow
sched.defer              (connection, card_id, *, now=None, days=7) -> ReviewRow
sched.list_reviews       (connection, card_id) -> tuple[ReviewRow, ...]     ← 存在、导出、有测试
```

实测（真迁移 · 真 SQLite · 真 `fsrs`）：

```
list_reviews before enrolling   -> 0 rows
list_reviews after enrolling    -> 0 rows          ⭐ 入队本身不产生历史
list_reviews after 2 interactions -> 2 rows
   outcome=reviewed  rating=good  from_state=learning  to_state=learning
   outcome=deferred  rating=-     from_state=learning  to_state=deferred
```

⇒ **要接的是 HTTP 边界，不是数据。**

### 1.2 边界层确实没有

从**服务端自己发布的 OpenAPI 表**读（45 条 path）：

```
POST  /api/v1/decision-reviews          POST  /api/v1/lessons/{lesson_id}/review
GET   /api/v1/decision-reviews/due      POST  /api/v1/notes/{note_id}/review
GET   /api/v1/decision-reviews/recent   GET   /api/v1/notes/{note_id}/reviews    ← 笔记有
GET   /api/v1/decision-reviews/schema/quadrants
GET   /api/v1/decision-reviews/{decision_id}
GET   /api/v1/review/due                POST  /api/v1/reviews/{decision_id}/lesson
POST  /api/v1/review/{card_id}

/api/v1/cards/ 下面实际有的四条：
   {card_id}   {card_id}/converge   {card_id}/schedule   {card_id}/verify
   ⭐ 没有 reviews。
```

⚠️⚠️ **量这一节的时候我自己坏了一次，值得单独记**（`F-249`）：
第一版探针走 `app.routes`，报「零条 review 路由」—— 而这个应用明明有十一条。
根因与 **spec 050 记录的根因逐字相同**：`app.routes` 上有 12 项 `_IncludedRouter`，
它们的 `.path` 是**空串**，于是 `getattr(r, "path", "")` 把 12 条**全部**变成跳过。
⇒ `.ai/failure-modes.md` **F-213** 说的正是这件事：「找不到东西」与
「找不到东西是因为我坏了」**从输出上分不开**。
⭐ **我在一支专门用来量路由的探针里，第二次踩了同一个坑。**
⇒ 正解是读**已发布的 schema**：它不可能有这个失效模式。

### 1.3 ⭐⭐ 真正的缺陷比「少一条端点」更深一层

`components/knowledge/ratings.ts` 的第 2 行写着：

> ⭐⭐⭐ **The four FSRS grades, in the reader's own words, and this is their one home.**

而 spec 049 量出来的三行是：

```
RecallView.tsx        again 我的想法变了   hard 想得起来，但有点犹豫  good 还是我的想法  easy 太熟了
LessonRecallView.tsx  again 我的想法变了   hard 想得起来，但吃力      good 想得起来      easy 张口就来
timelineAdapters.tsx  again 我的想法变了   hard 想起来了，但慢        good 记得          easy 不用想   ← 缺陷
```

⭐ **第四行量出来了，而它没被记在那份文件的顶部**：

```
ReviewPage.tsx:250-261  again 忘了   hard 有点难   good 记得   easy 太简单   + 现在不是时候
                      ^^^^^^^ 硬编码在一个页面里，五个 <Button> 的字面量
```

⇒ **`ratings.ts` 有 `NOTE_RATINGS` 与 `LESSON_RATINGS`，没有 `CARD_RATINGS`。**
spec 049 把三处收敛成两张表，**卡片是漏掉的那一处**。

⚠️ **这决定了本规格的形状。** 一张复习历史行要说「复习过 · 记得」，
那个「记得」**必须和读者在队列里按下的那个按钮是同一个词**——
不然历史就回答不了「**我当时按的是哪个**」，而那正是 spec 049 开这个轮的同一个问题。
⇒ 若在适配器里再抄一份标签，**就是亲手重建 spec 049 刚删掉的那个 bug**（回归 0021「一个概念三个家」）。
⇒ **所以「把 `CARD_RATINGS` 收进 `ratings.ts`」不是顺手重构，是本规格的必要条件。**

### 1.4 卡片没有 `reset`，这是结构性的

`0005_card_scheduling.up.sql`：

```
CHECK (outcome IN ('reviewed', 'deferred'))            ← 只有两态
CHECK (rating  IS NULL OR rating IN ('again','hard','good','easy'))
```

⭐ 与 spec 028 / spec 030 的推理一致：**卡片不可变 ⇒ 不需要 `reset`**，
所以笔记那张 `OUTCOME_LABEL` 的第三行（「这条被我改过，排程从头开始」）**对卡片不适用**，
而**适配器不能因此少一行** —— 少的那一行会让 `Record` 少一个键，
而那正是 `ratings.ts` 存在的理由。

### 1.5 「已入队」推不出「有历史」

实测：入队后、第一次作答前，`list_reviews` 仍是 **0 行**。

⚠️ 而 `card_reviews` 的外键指向 **`cards(id)`，不是 `card_schedule(id)`** ——
所以「未入队 ⇒ 无历史」**不是数据库保证的**，它是 `record_review()` 第 284 行
先调 `get_schedule()` 抛 `CardNotScheduledError` 的**代码**结果。
⇒ 按宪法 §0.2，这一条现在落在**第 ② 层**，而它**能**移到第 ④ 层（见 §五）。

---

## 二 · 设计决策

### 2.1 端点：`GET /api/v1/cards/{card_id}/reviews`

放在 `card_router`（prefix `/api/v1/cards`），与 `{card_id}/schedule` 并列。

**为什么不是第二个前缀**：卡片队列当初用 `/api/v1/card-reviews` 是因为
`GET /cards/due` 会被 `GET /cards/{card_id}` 吞掉（`routes/reviews.py:14-20`）。
本路径是**两段**（`/{card_id}/reviews`），与已存在的 `/{card_id}/schedule` 同形，
**那个吞路由的问题在这里不存在** ⇒ 不需要新前缀，也不需要注册顺序的隐式耦合。

### 2.2 ⭐ 状态码与笔记那侧**故意不同**

| 情况 | 本端点 | `GET /notes/{id}/reviews` 现状 |
|---|---|---|
| 卡片不存在 | **404** `CARD_NOT_FOUND` | ⚠️ **200 `[]`** |
| 卡片存在、没有复习 | **200 `[]`** | 200 `[]` |

实测笔记那条路由（`routes/notes.py:540-547`）**完全不做存在性检查**，
所以不存在的笔记会得到一个空列表。

⇒ **本端点不照抄它。** 「这张卡片不存在」与「这张卡片还没被复习过」
在界面上是两件完全不同的事：前者是坏了，后者是一个普通的空状态。
⇒ 而这正是 `routes/reviews.py:208-222` 已经为 `{card_id}/schedule` 论证过的
**同一个区分**（409 vs 404「冲突」与「不存在」）。**沿用卡片那条契约，不沿用笔记那条。**
⚠️ 笔记那侧的不一致**本轮记录、不修** —— 那是 spec 028/026 的地盘。

### 2.3 词汇表：`CARD_RATINGS` 收进 `ratings.ts`

**取值与 `ReviewPage.tsx:250-261` 逐字相同**（忘了 / 有点难 / 记得 / 太简单），
**一个字都不改** —— 因为那五个字就是读者已经按下过的按钮，
改它等于让历史回答不了「我当时按的是哪个」。
⇒ `ReviewPage.tsx` 改为 import，**硬编码的那五处消失**。
⚠️ `现在不是时候` **不是评分**，它是 `outcome: 'deferred'`，不在这张表里
（与 `OUTCOME_LABEL` 的分工相同）。

### 2.4 ⭐ 两个时间线，不合并

卡片将有两条 append-only 记录：生命周期（`已对照出处` / `已收敛`，`CardTimeline`）
与复习历史（本轮）。**本规格不把它们合成一条。**

| | 生命周期 | 复习历史 |
|---|---|---|
| 读者的问题 | 「这条卡片被谁动过」 | 「我复习过几次、为什么今天又来了」 |
| 量级 | 0–3 行 | 0–50 行 |
| 空状态的含义 | 「它从没被动过」 | 「它从没回来过」 |

⭐ 合并会把两个词汇表按时间混在一个有序列表里，读者无法分辨哪一行是哪一种事；
而 `timelineAdapters.tsx:123-127` 已经写过理由：
**「没有留下说明」与「不可能留下说明」是关于一行的两个不同事实**，
空状态句子同理 —— 一句话盖不住两种缺席。

### 2.5 渲染位置与取数条件

**位置**：`CardSection.tsx`，与 `CardTimeline` 相邻。

**取数条件**：**只在「已入队」时取**，其余两态不取。

| spec 048 的三态 | 有可能存在历史？ | 取不取 |
|---|---|---|
| 「加入复习」（确定未入队） | **否** | **不取** |
| 「复习状态取不到。」（不知道） | 不知道 | **不取** —— 不显示一个点了会失败的读操作 |
| 「已加入复习 · 下次 …」 | 可能（§1.5：可能仍是 0 行） | 取 |

⇒ 绝大多数卡片（从没入队）**零请求**，而这不是性能优化，
是「未入队 ⇒ 无历史」这条**已推导**的事实（§1.5）。
⚠️ 拿到空数组时**不渲染时间线**：入队未作答是一个**空状态**，不是一段历史。

---

## 三 · 红线落点

| 红线 | 本轮怎么落 |
|---|---|
| **9** 不展示成绩 | ⭐ **`duration_ms` 存着、不显示** —— 理由与笔记适配器逐字相同（`timelineAdapters.tsx:190-198`）：「你复习了 3 秒」是在邀请读者优化自己的记忆而不是读下去。一个读者无法据以行动的数字，是带小数点的噪声 |
| **9** | 响应模型里**没有** `retrievability` / `stability` / `due_in_days` / `mastery`，与 `ScheduleRead` 一致 |
| **11** 不鼓励频繁操作 | ⭐ **不渲染「已复习 N 次」**。历史是**一列行**，不是一个可以被爬的数字 |
| **13** 不讨好 | 历史行只说「发生了什么」，无评语、无鼓励、无失败计数 |
| **8/14** | 无推送、无徽标。历史只在读者打开卡片时在那里 |

---

## 四 · 不做什么（Out of Scope）

| 不做 | 为什么 |
|---|---|
| ⭐ **决策侧（J3）** | **另一份规格。** `reviews.reviews_for()` 同样零路由调用，但它的 `ReviewRow` 带 `process_score` 与 `outcome`（四象限），词汇表、空状态与红线 5 全部不同。**一个概念两个领域 ⇒ 两份规格**，见 §五 |
| **`duration_ms`** | §三 |
| **「已复习 N 次」计数** | 红线 11 |
| **`card_reviews` 加指向 `card_schedule` 的外键** | §五 —— 要走迁移与 ADR，不夹带 |
| **修笔记侧「不存在的笔记返回 200 []」** | §2.2 —— 记录，不夹带 |
| **`reset` 档** | §1.4 —— 卡片不可变，结构上不存在 |
| **把 `list_reviews` 改名或搬家** | 它有测试、有导出、名字准确。**缺的不是一个函数的名字** |

---

## 五 · 明确不做的两件，与它们各自的理由

**① `card_reviews` 的外键仍指向 `cards` 而不是 `card_schedule`。**
「未入队 ⇒ 无历史」现在靠 `record_review()` 的代码保证（第 ② 层）。
宪法 §0.2 说「能移到 ③/④ 就必须移」⇒ **这是一个已登记的欠账，不是「已解决」**。
⚠️ 但加外键要动已发布迁移，且这是**结构性**改动 ⇒ 走 ADR，不在本轮夹带。

**② `CARD_RATINGS` 的 hint 一律留空。**
`recallContract.test.ts` 断言 hint 长于两个字，而它断言的是**笔记**那套。
卡片现在也没有 hint（`ReviewPage` 从来没有过）⇒ **不给它编一句**。
理由与 `LESSON_RATINGS` 的空 hint 相同：**一句没人选过的说明比没有说明更糟。**

---

## 六 · 计划推翻本规格的地方（由 `plan.md` 回填）

> ⚠️ 本规格假设的次序是「先端点，后界面」。
> ⭐ **`plan.md` 第二步推翻了它**，因为 §1.3 的量出现在写规格**之后**：
> **先做 `CARD_RATINGS`，再做端点。**
> 理由：端点一旦落地，第一件会被写的东西就是适配器里的标签，
> 而那正是重建 spec 049 的缺陷。**顺序反过来，先把唯一的那张表建好。**

---

## 七 · 已知的失败（不假装覆盖）

| # | 会以什么形状骗过我 |
|---|---|
| 1 | ⭐ **「有测试」被当成「够得着」。** `list_reviews` 有测试、有 `__all__` 导出、有 docstring —— 而 HTTP 上零条路由。测试证明的是它走过的路径是对的（宪法 8.3），**证明不了有人能走到它** |
| 2 | ⭐ **`app.routes` 一定给出假答案。** 见 §1.2。**只读已发布的 schema** |
| 3 | ⭐ **照抄笔记那条的状态码，把 404 变成 `[]`。** 见 §2.2 |
| 4 | ⭐ **在适配器里写第四份标签表。** §1.3 / §2.3。这会让 spec 049 的修复回退，且**没有任何门禁会红** |
| 5 | ⭐ **把入队当成有历史。** §1.5 实测：入队后 0 行 |
| 6 | `CardRead` 加一个 `reviews` 字段并每次全量带上 —— **列表页会 N+1**，而 `CardRead` 是列表响应 |
| 7 | 把 `duration_ms` 显示出来 —— 它「已经存着了」，所以看起来只差一个渲染。§三 |