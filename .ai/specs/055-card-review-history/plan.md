# 055 · 计划

> ⚠️ **审查者不要读本文件。** 理由写在 `.ai/agent-guide.md` §一：
> **知道意图的审查者会「拿代码对照计划」，而不是「判断代码对不对」。**
>
> 本计划的次序与 `spec.md` §〇假设的**相反**，推翻了什么写在 §三。

---

## 一 · 原始问题

一张卡片被复习过，**这件事没有任何人看得见**。
`scheduling.list_reviews()` 写好了、有测试、有导出，
而从已发布的 OpenAPI 表实测：**`/api/v1/cards/` 下面没有 `reviews`**，
而笔记那条**存在**。

---

## 二 · 步骤（次序被 §三 推翻过一次）

### T1 · 先把唯一的那张标签表建起来 —— **不是端点**

1. `components/knowledge/ratings.ts` 加 `CARD_RATINGS`，取值**逐字**取自
   `ReviewPage.tsx:250-261`（忘了 / 有点难 / 记得 / 太简单），hint 留空。
2. `ReviewPage.tsx` 改为 import，`data-testid` 与字面量**全部保留**
   （E2E 按 `data-testid` 找按钮，改文案会让 8 条既有测试红 —— 那是对的，
   它们本来就在钉这些字）。
3. `ratings.test.ts` 加一条：**`ReviewPage` 渲染的四个评分标签 === `CARD_RATINGS` 的 label**。
   ⭐ 这条断言的作用是**让 §1.3 那个缺陷不可再犯**：将来谁再硬编码，它就红。

**为什么这是第一步**：见 §三。

### T2 · `CARD_RATINGS` 的两个测试先写

`ratings.test.ts` 现有两条断言是关于笔记与教训的。新增：

- 四个 label 逐个非空、互不相同（抄错的典型形态是两个相同）
- **`ReviewPage` 用的是这张表**（从源码里 import 的同一个符号，不是从 DOM 里读的文案）

⚠️ 第二条的形态很重要：**从模块读，不是从 DOM 读。**
从 DOM 读会把「文案一致」与「同一个家」混为一谈 ——
而 §1.3 的缺陷正是**两边字面量相同、来源不同**。
⚠️ `ratings.test.ts` 里已经有一个前车之鉴（`.ai/memory/2026-10-04.md` §三②
记录的 `DECLARATION` 正则与 `api.ts:621` 注释里的一个「挒号」），
所以这里**不用正则去源码里扫**，**直接 import 常量**。

### T3 · 端点：`GET /api/v1/cards/{card_id}/reviews`

1. `CardReviewRead` 模型 —— 字段与 `NoteReviewRead` **逐个相同**
   （`id` / `card_id` / `outcome` / `rating` / `reviewed_at` / `duration_ms` /
   `from_due_at` / `to_due_at` / `from_state` / `to_state`）。
   ⚠️ `duration_ms` **照抄笔记那侧也要有** —— 它在表里、它被存着，
   **而「有字段」与「显示它」是两件事**（§三 / spec §三）。
2. `_review_read(row)` 适配器。
3. 路由挂在 `card_router`，**紧邻** `{card_id}/schedule`。
4. ⚠️ **存在性先查**：404 `CARD_NOT_FOUND`，**不是** 200 `[]`（spec §2.2）。

### T4 · 端点的测试 —— 逐条对应 spec 的「已知的失败」

| 测试 | 钉住 |
|---|---|
| 不存在的卡片 → **404**，且**不是** `[]` | 失败 #3 |
| 存在但没复习 → **200 `[]`** | 失败 #5 |
| 两行历史按时间升序 | 顺序是「我复习过 N 次」的前提（与笔记同） |
| `duration_ms` 在**响应里** | 它被存着（红线 11 禁的是**显示**，不是**存储**） |
| 响应里**没有** score 字段 | AST 级，抄 `test_reviews_api.py::TestTheResponseCarriesNoScore` |
| 路由出现在已发布的 schema 里 | ⭐ **失败 #2 的直接反测** |

### T5 · 前端：`api.ts` 加 `listCardReviews` 与 `CardReview`

⚠️ `api.ts` 已 1179 行，`notes.ts:5` 的注释抱怨过它太大。
⇒ **`CardReview` 与 `listCardReviews` 放 `api.ts`**（卡片的一切都在那里，
`Schedule` / `ReviewReceipt` 已经在里面），**不新建第四个 api 文件**。

### T6 · 第四个适配器 `CardReviewTimeline`

`timelineAdapters.tsx` 追加，**不动**既有的三个。
- `CARD_OUTCOME_LABEL` 只有两行（§1.4：`reviewed` / `deferred`），
  **`deferred` 沿用笔记那侧的措辞「我说以后再看」** —— 同一种动作，
  两种读者不该看到两个词。
- `tone`：⭐ **两行都不标色。** 笔记那侧标 `reset` 是因为改写抹掉了排程；
  卡片**没有这一档**（§1.4），而 `deferred` 的后果是「往后挪」，
  与 `reviewed` 的后果「记忆强度变了」**性质相同** ——
  规则 7 只允许颜色承载**区别**，而这里没有区别可承载。
  ⇒ 与 `CardTimeline` 的 `verified` 同样处理（不标色），**不是**编一个。

### T7 · 接进 `CardSection`

按 spec §2.5 的三态表取数。三处都要有：
- `useResource` 的 `describe`（错误句）
- **未入队 / 不知道 ⇒ 不取**
- 拿到空数组 ⇒ **不渲染**

### T8 · E2E

改一个页面 ⇒ 必须有 E2E（spec 025 的教训：「做完了但没测」）。
至少三条：历史出现 / 未入队时不出现 / 拿不到状态时不出现。

---

## 三 · 计划的意外发现：次序被推翻

### 原计划：先端点，后界面

### 改后：先 `CARD_RATINGS`，后端点

**为什么**：`spec.md` §一 之三是**写规格时**才量出来的 ——
`ratings.ts` 缺 `CARD_RATINGS`，卡片的四个评分标签**硬编码在 `ReviewPage` 里**。

⇒ 如果按原次序做：T3 端点落地 → T6 适配器要写标签 →
**最省事的写法是在适配器里再抄一份**，而那**正是 spec 049 花一整轮删掉的缺陷**
（`timelineAdapters.tsx:109` 那一行硬编码，回归 0021「一个概念三个家」）。

⭐ **而那个缺陷当初是怎么被发现的？** 因为有人把三处并排看了一眼。
⇒ **所以「先建表」不是洁癖，是让 T6 在写出来的那一秒就没有捷径可走。**
⇒ 这也是本计划**唯一**一次改序，改的理由是量到的，不是想到的。

### 第二个意外：`ReviewPage` 的五个按钮不能改成 map

原以为「四档评分 + 一个延期」可以统一成一次 `.map()`。
⚠️ **不行** —— `现在不是时候` 不是评分（§2.3），它的 `data-testid`
是 `rate-defer` 而其余四个是 `rate-<档位>`。
⇒ 只能让**四个**走 `CARD_RATINGS`，第五个仍是一个独立 `Button`。
⭐ 这次是**先写步骤时发现的**，不是写代码时 —— 记在这里，
因为它证明了「把评分表变成数据」这件事**有边界**，而边界在 `outcome` 上。

---

## 四 · 计划没有回答的

| 问题 | 留给 |
|---|---|
| `card_reviews` → `card_schedule` 外键（spec §五①） | 一份 ADR |
| 决策侧历史（J3） | 另一份规格 |
| 笔记侧「不存在的笔记返回 200 []」（spec §2.2） | 不夹带 |
| `retrievability` 依旧零调用 | 已有 AST 测试守着 |