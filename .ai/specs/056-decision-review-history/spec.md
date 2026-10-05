# 056 · 决策的复盘历史：⭐⭐ 而它**不能**放在复盘页上

> 宪法 2.2 要求的三问在 §〇。规格与计划分离；**计划推翻了规格自己的一处放置决定**（§七）。
> ⚠️ 本规格有一处**需要主人点头**（§六），而我按保守的一边做了并标出来。

---

## 〇 · 想做什么

**目标**：让一条决策**被复盘过的每一次**都能被读者看到 —— 一条读端点 + 一个界面。

**具体故障**：`reviews.reviews_for()` 在 `storage/repositories/reviews.py:198` 实现、
在 `__all__` 里导出，**而没有任何路由调用它**。
`GET /api/v1/decision-reviews/{id}` 只返回 `latest`（`decision_reviews.py:320,328`），
⇒ **第二次及以后的复盘在界面上不留任何痕迹** ——
读者在复盘页改一次分数，上一次的那次就消失了。

**既有机制为何不行**

| 机制 | 为何不行 |
|---|---|
| `GET /decision-reviews/{id}` | 只给 `latest`。**而复盘是可重复的**（§一 之二实测） |
| `ReviewStateRead.reviews: int` | ⭐ **它已经是「复盘了几次」的计数**，而 `RetrospectivePage` 从不读它 —— 一个已经算出来、已经传出去、**零消费方**的数字 |
| 复盘页的四象限判语 | ⭐ **只服务当前那一次**，且由 `domain/review.py::QuadrantJudgement.guidance()` 下发 |

---

## 一 · 量：现状（全部实测）

### 1.1 B3 的第二半属实

`reviews_for()` 存在、导出、有测试、**零路由调用**。

### 1.2 ⭐ 复盘是可重复的 —— 而这条决定了整个功能不是空的

实测（真迁移 · 真仓储 · 真领域对象）：

```
schedule(due_at=+90d)                      reviewed_at=None
record(process_score=3, outcome=None)      ACCEPTED
record(process_score=5, outcome=None)      ⭐ ACCEPTED   ← 第二次，没有任何东西挡着
record(process_score=4, outcome=good)      ACCEPTED（到期后）
record(outcome=good, 未到期)                REFUSED: ReviewNotDueError  ← 这道闸是真的

reviews_for() -> 3 行，最旧在前
count_reviews() = 3        latest_review() 只返回最后一行
```

⭐⭐ **闸门只管 outcome，不管 process_score**（`reviews.py:340`：
`if review.outcome is not None and state.due_at > moment`）⇒ **「只写过程分」可以无限次写。**
⇒ 而这正是 **红线 5「过程分与结果分独立」** 被写出来的原因：
**一行只有过程分、没有结果，是这张表本来的样子，不是一条残缺记录。**

### 1.3 ⭐⭐⭐ 「不能放在复盘页」—— 一条比红线更严的既有断言

`e2e/retrospective.spec.ts:23-27`，原文：

> **In the dangerous quadrant the whole page contains no number.** Not "no profit
> number" — no digits at all, and none of the words that would smuggle one back in.
> **That is deliberately stricter than the red line**, because a percentage and a
> currency amount are the same violation wearing different clothes.

断言在 `:120`：`expect(text).not.toMatch(/[0-9]/)`，**对象是整个正文的 innerText**。

⚠️⭐ **而复盘历史必然含数字** —— 过程分是数字，日期也是数字。
⇒ **把历史放进复盘页，与这条既有断言直接冲突。**
⭐ 而这条断言是 spec 021 有意写得比红线更严的（§三），**不是为了给新功能让路的**。

⚠️ **顺带查到一处矛盾**（**只记录，不修**）：`ReviewStateRead.reviews` 的 docstring
（`decision_reviews.py:123-127`）写着
「**No "you have reviewed 4 of 7". No completion rate.**」，
而**紧跟着第 146 行就是一个 `reviews: int`**。
⇒ 那句 docstring 描述的是「不把计数**显示出来**」，而字段是在**传输**计数。
两件事，但**写在同一个 docstring 里容易被读成同一件事** —— 见 §五。

### 1.4 前端：两个地方都看不到历史

| 事实 | 出处 |
|---|---|
| `RetrospectivePage` 只把 `latest` 拿来做**一个布尔** `graded` | `RetrospectivePage.tsx:154,168` |
| 全仓渲染的 `reviews` 计数**只有两处**，且都是**队列深度**（今日 / 开屏的「N 条复盘」），**不是「我复盘了几次」** | `TodayPage.tsx:309` · `StartupPage.tsx:111` |
| 标的页的决策区已有 `DecisionSection`，**有一条 append-only 时间线** | `InstrumentPage.tsx` · `RecordTimeline` |

---

## 二 · 放置：⭐ 标的页，不是复盘页

| | 复盘页 `#/retrospective` | **标的页 `#/i/{m}/{c}`** |
|---|---|---|
| 危险象限「整页无数字」 | ⛔ **直接冲突**（§1.3） | ✅ 不受约束 |
| 读者的问句 | 「哪条到期了」—— 一个**队列** | 「我对这只票下过什么判断、后来怎么评的」—— **一条记录的来龙去脉** |
| 已有的 append-only 时间线 | 无 | ✅ 决策区已有一条 |
| 与卡片历史的位置一致性 | — | ⭐ **卡片复习历史就在这一页**（spec 055）⇒ **「一条判断的复盘」与「一张卡片的复习」放在同一个地方，是同一个理由** |

⇒ **决定：标的页的决策区。**

---

## 三 · 红线落点

| 红线 | 本轮怎么落 |
|---|---|
| **5** 过程分与结果分独立 | ⭐ **本轮把这条红线变得可见**：`outcome` 为空的行**照常渲染**，标成「只写了过程分」。**藏掉它才是违反这条红线** |
| **9** 不展示成绩 | ⭐ **每行是一个独立事实，不是一条趋势**：无箭头、无差值、无「进步了」。且**不给「你一共复盘了 N 次」的合计** |
| **10** 必须让用户面对不舒服的数据 | ⭐ 象限名照实显示（含「危险象限」）。`DecisionReviewRead` 的 docstring 已说明**没有存过盈利数字**，所以历史也不可能泄漏一个 |
| **11** 不鼓励频繁操作 | ⚠️ **见 §六 —— 这是需要主人点头的那一条** |
| **6** 未成熟结果留空 | `outcome=None` 渲染成一句话，**不是 `0` 也不是 `—`** |

---

## 四 · 不做什么

| 不做 | 为什么 |
|---|---|
| ⭐ **在复盘页显示任何形式的复盘历史** | §1.3 —— 与一条**刻意比红线更严**的既有断言冲突 |
| **「共复盘 N 次」的合计** | 红线 11。且 `ReviewStateRead.reviews` 已经传了，**界面不显示它**就够了 |
| **分数趋势 / 差值 / 「进步了」** | 红线 9。一行一个事实，不是成绩曲线 |
| **把 `ReviewStateRead.reviews` 从 API 删掉** | 它有用（`graded` 判定、测试断言），**且它不是显示**。§五 |
| **改复盘页那条 E2E 断言** | ⭐ **它是 spec 021 有意加严的**，为了让新功能给它让路而放松它，是本项目反复记录的那种失败 |
| **J2 论点表 / `thesis_id`** | 另一笔欠账，仍等主人 |

---

## 五 · 明确记录、不修的一处矛盾

`ReviewStateRead.reviews` 的 docstring 说「No "you have reviewed 4 of 7"」，
而字段就在下面 20 行。⇒ **那句话应该说的是「不把它显示出来」，而不是「不存在」。**
⚠️ **本轮不改它** —— 改一个既有 docstring 会掩盖「这句话当初是怎么写的」，
而 `F-235` 记的正是**一个无法被证伪的陈述就是一个没人核对过的陈述**。
⇒ **本规格的立场是：那句话指的是显示，而字段是传输；两者都对，但挨得太近。**

---

## 六 · ⚠️ 需要主人点头的一条（红线 11 的边界）

**问题**：把读者**自己给的过程分**按时间顺序列出来，是不是红线 11
（禁止任何促使用户「动起来」的设计）范围内的「成绩」？

**我按保守的一边做了**，并把理由摆出来：

| | |
|---|---|
| 允许的理由 | ⭐ 红线 2 明确说评分字段只描述**决策过程**；⭐ **复盘页今天已经显示了一个过程分**，历史只是把已经存在的事实按时间排开；⭐ **每行是独立事实**，没有趋势、没有合计、没有「变好了」 |
| 收紧的理由 | ⚠️ 这是产品**第一次**把读者自己的分数**重复**呈现；⚠️ 一个可见的分数序列会邀请「把分数提上去」，而那正是红线 11 的形状 |

⇒ **我做的**：行里**照实写过程分**（它是读者写下的一部分），但
**不做趋势、不做差值、不做合计、不加任何评价**。
⇒ **若主人认为该收紧**：改动只在适配器一行（去掉分数字样），
⭐ **而端点与测试都不必动** —— 这是我把「显示」与「传输」分开的原因。

---

## 七 · 计划会推翻的地方（由 `plan.md` 回填）

> ⚠️ 待回填。

---

## 八 · 已知的失败（不假装覆盖）

| # | 会以什么形状骗过我 |
|---|---|
| 1 | ⭐ **照抄 spec 055 的卡片历史。** 那个 `ReviewRow` 带**四个**字段，而这里带**过程分与象限**；⭐ **而复盘页有一条「整页无数字」的断言是我在写完规格之前没读的** |
| 2 | ⭐ **把 `outcome=None` 的行藏起来**，理由是「它不完整」⇒ 而那**正是红线 5 的形状被反过来违反** |
| 3 | ⭐ **给 `RecordTimeline` 加第五个适配器却把 V-14 的数字忘了改** ⇒ 那个门禁**上轮刚被我修好**，而它只在名字白名单里才瞎（`F-248`） |
| 4 | 在 `api.ts` 里手抄 `DecisionReview`，而 `S-18` 门禁就是干这个的 ⇒ 让它当场报 |
| 5 | ⭐ **把「象限名」当成 `outcome` 的翻译** —— `Quadrant` 有 5 个值而 `Outcome` 只有 3 个（实测 `['GOOD','BAD','FAILED']` vs `['REPEAT','ACCEPTABLE','DANGEROUS','FIX','UNKNOWN']`），⭐ **两者不是同一个概念的两套说法** |
| 6 | 在复盘页加一个「历次复盘」折叠区 ⇒ §1.3 |