# spec 030 · 计划

| # | 步骤 |
|---|---|
| 1 | 迁移 `0010_lessons`：`lessons` / `lesson_schedule` / `lesson_reviews` / `lesson_promotions` |
| 2 | 约束台账：计数 127 → N，分类标记补齐，两条「无 reset」测试进红绿 |
| 3 | `domain/lesson.py`：`LessonDraft` + 错误码（**新前缀** `LESSON_*`，因为产物不是卡片了） |
| 4 | 仓储 `lesson.py`：`record_lesson()` —— **一个事务三件事** |
| 5 | 仓储：`promote_lesson()` —— 要出处 + 两个 UNIQUE 兜底 |
| 6 | API：`POST /reviews/{decision_id}/lesson` · `POST /lessons/{id}/promote` |
| 7 | pytest：验收 1-11 条 + **原子性反向测试** |
| 8 | **`.ai/eval/redlines.json`：红线 7 `partial` → `full`** |
| 9 | 前端：复盘页「记一条教训」+ 教训队列 |
| 10 | 变异检查 + 门禁 + 四段式变更日志 |

## ⭐ 五条容易踩的，已预置

1. **不要碰 `0003` 的两条出处 CHECK。** 验收第 3 条就是为了让「没人偷偷放松
   provenance rule」变成可执行的 —— 一个只查「`cards` 上还有没有
   `NOT NULL`」的测试，比没写测试好。
2. **`lesson_reviews` 不要抄 `note_reviews` 的 `reset` 分支。** 抄了就等于说
   教训可变，而它不可变。验收第 9 条钉住这个缺席。
3. **不要复用 `scheduling.enroll()`。** 它会检查「是否已在队列上」并对重复入队
   抛错 —— 而这里刚入队，走一遍那条路径等于把「自动」变成「尝试」，
   红线的保证就变成了一个可能被前置检查挡掉的分支。
4. **`lesson_promotions` 是 append-only 触发器，不是 `lessons` 的一个列。**
   因为 `lessons` 不可变，而「已经转过了」必须被记下来。
5. **`.ai/eval/redlines.json` 是机器可读的** —— 改 `coverage` 时
   **`verifier` 必须同时指向一个真存在、会被执行的测试**，
   否则 `eval` 会把一个「声明」当成「强制」。
