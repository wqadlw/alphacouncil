# Spec 021 · 任务清单

> 勾选 = 做过并**验证过**。状态：2026-09-28

---

## 一、动手前先查（不是形式）

- [x] 查 `/api/v1/review` 是否被占用 —— **已被 K3 卡片队列占用**（`routes/reviews.py:79`）
- [x] 因此**没有**命名为 `/api/v1/reviews` 或 `#/decision-review`
- [x] 查 `CODED_ERRORS` 的注册方式 —— **手工维护的基类元组**
- [x] 查 `decisions` 有无单条 GET —— **没有**，所以决定让复盘端点带上原话
- [x] 查 `ReviewPage.tsx` 怎么实现红线 13 的**缺席**（ADR-0028）

## 二、⭐ 可达性缺口

- [x] 发现 `repo.schedule()` **无任何调用方** —— 机制齐了却够不着
- [x] `POST /decisions` 增加可选 `review_due_at`
- [x] **同事务**开出槽位（`decisions` 落了而槽位没开 = 静默永不到期）
- [x] 有测试：给了就有槽位；不给就是 404，**不发明默认间隔**

## 三、后端

- [x] `routes/decision_reviews.py` + 接入 `app.py`
- [x] `GET /decision-reviews/due`（`as_of` 注入、按到期时间排、**不按任何分数排**）
- [x] `GET /decision-reviews/{id}` → `{state, decision, latest}`
- [x] `POST /decision-reviews`（两表同事务）
- [x] `GET /decision-reviews/schema/quadrants` —— 文案由**后端**下发
- [x] `decisions.get_by_id` + `DecisionNotFoundError`（**404**）
- [x] 错误码映射：`REVIEW_STATE_MISSING` 404 / `REVIEW_NOT_DUE` 409 / `DECISION_NOT_FOUND` 404
- [x] ⭐ `ReviewError` 注册进 `CODED_ERRORS`（**否则三个码全退化成 400**）
- [x] `.ai/error-codes.md` 登记（**S-05 第一次运行就抓到了漏登记**）

## 四、前端

- [x] `api.ts`：`getDueDecisionReviews` / `getDecisionReview` / `recordDecisionReview` + 类型
- [x] `DecisionInput.review_due_at`
- [x] `routing.ts`：`#/retrospective` + `RETROSPECTIVE_HREF` + 单测
- [x] `RetrospectivePage.tsx`
- [x] `App.tsx` 接入（**独立路由，不做成 review 页里的 tab**）
- [x] ⭐ 到期前**不渲染**结果分控件
- [x] ⭐ 渲染 `verdict.guidance`，**不自己拼句子**

## 五、测试

- [x] `test_decision_reviews_api.py` **25 条**
- [x] ⭐ `TestTheResponseCarriesNoFigure` —— 枚举字段名
- [x] ⭐ `TestTheTwoQueuesCannotBeConfused` —— 含 `/api/v1/reviews/due` 是 **404**
- [x] 迁移链断言 `5 → 6`（4 处，含我第一版只改了一半的那次）
- [x] 路由单测 62 → **65**
- [x] E2E **23 → 28**（新增 5 条，负向为主）

## 六、变异（4 个，全中，且确认是**对的那条**测试变红）

- [x] M1 渲染 `+18.2%` → `retrospective.spec.ts:96`「整页无数字」红
- [x] M2 到期前渲染结果分 → `retrospective.spec.ts:76` 红
- [x] M3 响应加回金额字段 → `TestTheResponseCarriesNoFigure` 红
- [x] M4 前端自己拼「干得漂亮」→ 红旗线 10 的美化
- [x] 四次恢复哈希全部一致
- [x] ⭐ **harness 的 `detail` 抓错了行**（Playwright 最后一行是通过数，不是失败）——
      补跑一遍逐条确认变红的是**预期那条**测试，而不是碰巧某条

## 七、门禁与评测

- [ ] `dev.py check` **10/10 + 退出码 0**（待最终跑）
- [ ] `dev.py eval` 红线 10 按**实测**更新（不许乐观）
- [ ] 变更日志 + `status.md`

---

## 八、明确未做

| 项 | 为什么 |
|---|---|
| 到期日**自动**算法 | 判据未定义。用户自己写（§二） |
| 盈利 / 收益率任何形式 | 红线 10 由数据模型保证 |
| 复盘页的导航入口 | **本轮没加**：今日页与标的页都没有指向 `#/retrospective` 的链接，页面目前只能手敲地址。**这是本轮最明显的缺口** |
| 「第 N 次该复盘」 | 会变成打卡 |
| J4 重复检测 / J5 教训转卡 | 各自独立 |
