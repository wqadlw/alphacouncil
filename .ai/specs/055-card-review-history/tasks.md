# 055 · 任务清单

> 勾选规则：**一个任务只在它的验证命令给出预期输出之后才勾。**
> 「代码写完了」不是完成，「测试绿了」也不是 —— 是**那条命令的输出**。

## T1 · `CARD_RATINGS` —— 唯一的那张表（**先做**）

- [ ] `ratings.ts` 加 `CARD_RATINGS`，取值逐字取自 `ReviewPage.tsx:250-261`
- [ ] hint 留空，不编（spec §五②）
- [ ] `ReviewPage.tsx` 改为 import，五个 `data-testid` 与字面量**全部保留**
- [ ] 验证：`frontend-test` 绿，且 `ReviewPage` 里搜不到第二个「有点难」

## T2 · T1 的测试（**测试与实现同一轮**）

- [ ] 四个 label 非空且互不相同
- [ ] ⭐ **`ReviewPage` 渲染的标签 === `CARD_RATINGS`** —— 从**模块** import，不从 DOM 读
- [ ] 验证：把 `ReviewPage` 的 label 改一个字 → 上面那条测试**必须红**

## T3 · 端点 `GET /api/v1/cards/{card_id}/reviews`

- [ ] `CardReviewRead`，字段与 `NoteReviewRead` 逐个相同
- [ ] `_review_read()` 适配器
- [ ] 路由挂 `card_router`，紧邻 `{card_id}/schedule`
- [ ] ⭐ **存在性先查 → 404 `CARD_NOT_FOUND`**，不是 200 `[]`
- [ ] ⚠️ `duration_ms` **有字段**（红线 11 禁显示，不禁存储）

## T4 · 端点测试（逐条对应 spec §七）

- [ ] 不存在 → 404，**不是** `[]`（失败 #3）
- [ ] 存在未复习 → 200 `[]`（失败 #5）
- [ ] 多行按 `reviewed_at` 升序
- [ ] `duration_ms` 出现在响应里
- [ ] ⭐ 响应**无** score 字段（AST 级）
- [ ] ⭐ 该路由出现在**已发布的** OpenAPI schema 里（失败 #2 的反测）

## T5 · 前端类型与调用

- [ ] `CardReview` + `listCardReviews` 放 `api.ts`（**不新建第四个 api 文件**）
- [ ] `frontend-typecheck` 绿

## T6 · `CardReviewTimeline`（第四个适配器）

- [ ] `CARD_OUTCOME_LABEL` **两行**（`reviewed` / `deferred`）
- [ ] `deferred` 沿用笔记侧的「我说以后再看」
- [ ] ⭐ **`tone` 两行都不标色** —— 卡片没有 `reset`，没有区别可承载（规则 7）
- [ ] `as="ol"`（顺序就是「我复习过 N 次」）
- [ ] 空的 `duration_ms` 理由抄笔记那一段，**不要重新发明**
- [ ] 既有三个适配器**一个字不动**

## T7 · 接进 `CardSection`

- [ ] 按 spec §2.5 三态取数
- [ ] 未入队 / 状态未知 ⇒ **不取**
- [ ] 空数组 ⇒ **不渲染**
- [ ] `useResource` 有 `describe`

## T8 · E2E

- [ ] 历史出现（入队 + 答过一次之后）
- [ ] 未入队 ⇒ **不出现**
- [ ] 状态取不到 ⇒ **不出现**（且**不**显示会失败的按钮）

## T9 · 变异检查（宪法 8.3）

每个靶点必须**先确认真的生效**，再记录结论。

- [ ] M1 去掉存在性检查 → T4 第一条必须红
- [ ] M2 排序改 `DESC` → 顺序测试必须红
- [ ] M3 `CARD_RATINGS` 改一个字 → T2 那条必须红
- [ ] M4 删掉 `CardReviewTimeline` 的挂载 → E2E 必须红
- [ ] M5 把 `tone: 'marked'` 加回 `deferred` → 规则 7 的断言必须红
- [ ] M6 在适配器里内联一份标签 → T2 那条必须红（**这条是本规格的命门**）
- [ ] ⚠️ 每条先确认变异真的改到了（spec 054 M1/M3/M4 三次没红，前因是 harness）

## T10 · 台账（**不许就地改 `memory/` 与 `logs/`**）

- [ ] `status.md` K3 行改写（**看板要跑，行改、记录不改**）
- [ ] `.ai/memory/2026-10-05.md` 新建（**今天是真实的一天，不回溯补造**）
- [ ] `.ai/logs/changes/2026-10-05-spec-055-card-review-history.md`
- [ ] `failure-modes.md` 加两条：
  - ⭐ **`app.routes` 给假答案**（我这一轮踩了，spec 050 已记根因）
  - ⭐ **`ratings.ts` 的「one home」曾漏掉卡片**
- [ ] `dev.py check` **12/12 + 退出码 0**

## T11 · 诚实清单

- [ ] 凡未验证的，写「未验证」，不写成结论
- [ ] 凡跑出来的数字，**一个命令可复算**