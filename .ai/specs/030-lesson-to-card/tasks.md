# spec 030 · 任务清单（J5 教训转卡）

> 对照 [`spec.md`](spec.md) 第六节的验收表。**「做完了」在这里是逐条对得上的，
> 不是一段叙述** —— 叙述在 `.ai/logs/changes/2026-09-28-lesson-to-card.md`。

## 一、验收表逐条

| # | 验收项 | 状态 | 在哪里 |
|---|---|---|---|
| 1 | 从一次复盘记下教训，生成教训 + 调度项 + 流水三行 | ✅ | `lesson.record_lesson` · `TestRedLineSeven::test_recording_writes_the_lesson_the_schedule_and_the_ledger_row` |
| 2 | ⭐ **挡住 `lesson_schedule` 写入 ⇒ 记教训失败，且不留任何教训行** | ✅ | `TestRedLineSeven::test_blocking_the_schedule_insert_rolls_the_lesson_back` |
| 3 | ⭐ **`cards` 的两条出处 CHECK 一个字未动** | ✅ | `TestProvenanceWasNotTouched`（含「`cards` 里没有 `review_id` 那一列」） |
| 4 | 刚入队的流水行**没有评分** | ✅ | `test_the_enrolment_row_carries_no_grade` |
| 5 | 教训**立刻到期**（`learning`，due = 记下的那一刻） | ✅ | `test_a_lesson_is_due_immediately` |
| 6 | 一次复盘可以记多条教训 | ✅ | `test_one_review_can_hold_several_lessons` |
| 7 | 复盘还不存在 / 没写完 ⇒ 不能记教训 | ✅ | `test_a_lesson_needs_a_review_that_was_written` · `test_a_lesson_for_an_unknown_decision_is_refused` |
| 8 | ⭐ 教训**不可变**（数据库级，不是约定） | ✅ | `test_lessons_are_immutable` + `lessons_no_update` / `lessons_no_delete` 触发器 |
| 9 | ⭐ `lesson_reviews` **没有** `reset`，且被钉住 | ✅ | `TestWhyThereIsNoReset`（枚举 + 数据库 `CHECK` + 与 `note_reviews` 的对照） |
| 10 | ⭐ 转卡**要求出处**；两个 UNIQUE 让重复转卡不可能 | ✅ | `TestPromotion`（7 条） |
| 11 | ⭐ 转卡后**教训继续留在队列上** | ✅ | `test_promoting_does_not_discharge_the_guarantee` |
| 12 | 红线 7 `partial` → **`full`**，verifier 指向真跑的测试 | ✅ | `.ai/eval/redlines.json` · 门禁 6→7 · pass_rate 0.400→0.467 |
| 13 | 台账计数更新 · 门禁 10/10 · 变异检查 | ⚠️ **部分** | 台账 127→156 ✅ · 门禁 10/10 退出码 0 ✅ · ⭐ **变异检查未跑** |

## 二、计划里的九步

| # | 步骤 | 状态 |
|---|---|---|
| 1 | 迁移 `0010_lessons`（四张表） | ✅ |
| 2 | 约束台账 + 分类标记 | ✅ 127 → 156 |
| 3 | `domain/lesson.py` + `LESSON_*` 错误码 | ✅ |
| 4 | 仓储 `record_lesson()` —— 一个事务三件事 | ✅ |
| 5 | 仓储 `promote_lesson()` —— 要出处 + 两个 UNIQUE | ✅ |
| 6 | API：5 个端点 | ✅ |
| 7 | pytest：验收 1-12 | ✅ 后端 848 → 892 |
| 8 | `redlines.json` 红线 7 | ✅ |
| 9 | 前端：复盘页入口 + 教训队列 | ✅ 复盘页「记一条教训」+ 知识库「该复习」并列 · E2E 69 → 82 |
| 10 | 变异检查 + 门禁 + 四段式变更日志 | ⚠️ **变异检查未跑** |

## 三、⭐ 明确没做的（如实列出，不是遗漏）

- ⭐ **本轮的变异检查欠着。** 前三轮各跑 9 / 11 / 15 次并全抓；这一轮改了
  **错误码规则**（硬编码 → 从文档推导）、**四组触发器**、**一张 CHECK 清单**，
  而**未经变异检查的规则改动正是台账存在的理由**。
  该敲的四个靶点写在 `.ai/HANDOFF.md` 第七节。
- **「转卡」的界面没做** —— `POST /lessons/{id}/promote` 有端点、有领域规则、
  有 7 条测试，**页面上没有入口**。
- **复习时先自己回忆再揭示的遮罩** —— 队列直接展示教训全文。
  理由：教训正文是读者自己的句子，标题不是好提示词（与 spec 028 对笔记的判断同源）。
