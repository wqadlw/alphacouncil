# spec 028 · 计划

| # | 步骤 |
|---|---|
| 1 | `ErrorCode` 加 `NOTE_NOT_SCHEDULED` / `NOTE_ALREADY_SCHEDULED` |
| 2 | `domain/note_recall.py`：`NoteScheduleRow` / `NoteReviewRow` / 两个错误 / `NoteReviewOutcome`（含 `reset`） |
| 3 | 迁移 `0009_note_schedule`：`note_schedule` + `note_reviews`（含 append-only 触发器） |
| 4 | 约束台账加两张表（照 0005 的分类） |
| 5 | `repositories/note_recall.py`：`enroll` / `due_notes` / `record_review` / `defer` / `list_reviews` / `reset_on_edit` |
| 6 | ⭐ `notes.update_body` 接上 `reset_on_edit`（**这是本轮的核心接缝**） |
| 7 | API：`POST /{id}/schedule` · `GET /due` · `POST /{id}/review` · `POST /{id}/defer` |
| 8 | pytest：仓储（含 5/6 两条改写行为）+ API |
| 9 | 前端：`#/vault` 加「该复习」视图 + 契约测试 |
| 10 | 变异检查 + 门禁 + 台账 |

## ⭐ 预置

1. **界面不能挂队列计数** —— `nav.spec.ts` 与 `retrospective.spec.ts` 都钉死了
   「无数字」。**这一轮最容易犯的错就是给「该复习」加个数字徽标。**
2. **`.gitignore` 的 `data/` 无前导斜杠**（spec 025 §7.1）—— 别建 `data` 目录。
3. **`RouteName` 是手写联合**，加视图要同时改 `ROUTES` 与联合，否则
   `tsc` 报 `Type '"x"' is not assignable to type 'RouteName'`（spec 027 已记）。
