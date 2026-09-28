# Tasks 018 · K3 复习队列（FSRS 排程机制，切片 1）

## T0 · 先问库，不先设计
- [x] 上一位 agent 的探针脚本问过 `fsrs` 五个问题但结论没落库 → **重做一遍**并写进 spec §1
- [x] Q1 不就地改传入对象 / Q2 关 fuzz 确定 / Q3 往返无损 / Q4 拒绝朴素 datetime / Q5 **只有三态**
- [x] 追加实测：`card_id` 是 int（我们的主键是 TEXT）· 四档评分 · `reschedule_card` **不是**推迟
- [x] 结论直接改变设计：**推迟必须自建**

## T1 · 迁移 0005
- [x] `card_schedule`（每卡一行当前排程，**可变**；`state_json` 存 fsrs 原文）
- [x] `card_reviews`（append-only 流水，条件必填 3 条 CHECK）
- [x] 两表分开的理由写进 SQL 注释（ADR-0014 先例：分开不合并）
- [x] `card_reviews` 两条 append-only 触发器 + 索引
- [x] `manifest.json` 登记 version 5（`destructive_down` + 理由）
- [x] `constraints.json` 登记两表全部约束
- [x] `APPEND_ONLY_TABLES` 加 `card_reviews`（S-04 因此真的检查了它）
- [x] `down.sql` 可执行
- [x] `comparison` 是**新增的约束类别**（旧的六种形状都装不下 `fsrs_card_id > 0`）

## T2 · 领域层
- [x] `ReviewRating`（四档）/ `ScheduleState`（**四态**，多一个 `deferred`）/ `ReviewOutcome`
- [x] 错误：`CardNotScheduledError` / `CardAlreadyScheduledError` / `TimestampNotUtcError`
- [x] `decode_payload` 单一解码定义（domain 与 repository 共用，不写第二遍）
- [x] `defer_due` 带上限 90 天

## T3 · 仓储
- [x] `enroll` / `due_cards` / `record_review` / `defer` / `get_schedule` / `list_reviews`
- [x] **新卡 `due` 取注入的 `now`，不取墙钟**（否则"到期了吗"取决于测试何时跑）
- [x] `fsrs_card_id` 每卡不同（否则复习日志里全是 `card_id=1`）
- [x] 队列排序只按 `due_at`，`card_id` 破平 —— **不按稳定性/优先级**（那是给用户的积压打分）

## T4 · 事务归属（回归 0006 的顺带产出）
- [x] `db.require_open_transaction()`：仓储**不开**事务也**不静默继续**，而是检查
- [x] 接入 `cards.verify` / `cards.converge` / `scheduling.record_review` / `scheduling.defer`
- [x] 七个写路由**一个字未改**
- [x] 回归测试 10 项

## T5 · 测试与变异
- [x] `test_scheduling.py` 46 项（含"推迟不污染记忆"逐字节比对）
- [x] `test_card_lifecycle_atomicity.py` 10 项
- [x] 变异 6 / 6 变红（M1~M6）
- [x] 恢复经 SHA-256 校验（含 `newline=""` 的修正）

## T6 · 诚实收口
- [x] `dev.py check` 10 道全过 + 退出码 0
- [x] `dev.py eval`：**红线 7 `none` → `partial`**，通过率**仍是 5/15**（`partial` 不算通过）
- [x] `gap` 写明：**机制有了，「每条教训自动生成」还没有**，J5 未开工

## 明确不做
- [x] 不用 `get_card_retrievability`（**它是成绩**）—— 有测试用 AST 钉住"永远不调用"
- [x] 不按 `duration_ms` 排名或统计（红线 11）
- [x] 前端复习界面（独立一轮，且须先回答"不讨好用户怎么落地"）
- [x] J5 教训转卡
- [x] 不合并 `cards.status` 与 `state`
- [x] 不用 `reschedule_card` 实现推迟
