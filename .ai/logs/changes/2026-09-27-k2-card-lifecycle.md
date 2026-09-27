# 变更记录 · 2026-09-27 · K2 卡片生命周期：状态留痕与收敛出口（spec 013）

- 日期：2026-09-27
- 类型：功能（feature）—— 知识层第二块：状态事件留痕 + 需要理由的收敛出口
- 范围：
  - 新增 `.ai/specs/013-card-lifecycle/`（spec.md / plan.md / tasks.md）
  - 修改 `backend/src/alphacouncil/domain/card.py`（新增 `CardEventType`、`CardNotActiveError`、`CardConvergeReasonRequiredError`）
  - 修改 `backend/src/alphacouncil/core/error_codes.py` 与 `.ai/error-codes.md`（新增 `CARD_NOT_ACTIVE`、`CARD_CONVERGE_REASON_REQUIRED`）
  - 新增 `backend/src/alphacouncil/storage/migrations/0004_card_events.up/down.sql`（append-only `card_events` 表 + 2 触发器 + 索引）
  - 修改 `storage/migrations/manifest.json`（登记 version 4）· `storage/constraints.json`（新增 card_events，约束总数 45 → 52）
  - 修改 `storage/repositories/cards.py`（`CardEventRow`、`list_events`、`converge`，`verify` 同事务写事件，各读取路径加载 events）
  - 修改 `api/routes/cards.py`（`CardConvergeRequest`、`CardEventRead`、`CardRead.events`、`PATCH {id}/converge`）· `api/errors.py`（`CARD_NOT_ACTIVE` → 409）
  - 修改 `backend/checks/rules/check_append_only_triggers.py`（append-only 表清单加 card_events）
  - 修改 `frontend/src/api.ts`（CardStatus/CardEventType/CardEvent 类型、`listCards` 支持 status、`convergeCard`）· 重写 `frontend/src/CardSection.tsx`（active/converged 分组、收敛理由表单、沉底弱化、事件时间线）
  - 修改测试：`tests/unit/test_card.py`（+6，共 25）· `tests/unit/test_cards_api.py`（+6，共 26）· `tests/integration/test_migrations.py`（+`TestTheRealFourthMigration` 4 例，共 42）· `tests/unit/test_storage.py`（约束计数，共 39）· `frontend/e2e/instrument.spec.ts`（+1 收敛闭环，共 15）
- 依据：ADR-0021（知识库模仿「记忆」，S-01 必须有 converged 出口）/ ADR-0022（「核对来源」升级必须留痕）/ 红线 4（状态变更同样先记录）· 红线 10（收敛 ≠ 删除/隐藏）· 红线 15（收敛理由由用户亲手写，非 agent 判断）

---

## ① 想做什么

K1 让卡片能被录入、展示与核实，但深度盘点发现两个真实缺口：

1. **状态变更没有留痕（违反 ADR-0022）**：K1 的 `verify` 直接 `UPDATE cards SET origin=...` 把卡从 `ai_generated` 升级为 `user_written`，却没有任何持久化记录证明升级发生过、何时、对哪张卡。`origin` 字段可变，与「只增不改」冲突。
2. **卡片没有出口（违反 ADR-0021 S-01）**：卡一旦 active，主张过时、被证伪或不再相关时无法退出。没有出口的知识库会膨胀成没人愿意打开的文件柜，而记忆会「收敛」。

K2 的核心不是加功能，而是把卡片从「只进不出的文件柜」变成「有出口、每次状态流转都留痕的记忆」：

> **一张 append-only 的状态事件表（`card_events`），加上一个需要理由的收敛出口。**

## ② 做了什么

**领域层**：新增 `CardEventType(StrEnum)`（`verified` / `converged`）与两个错误——`CardNotActiveError`（对非 active 卡收敛）、`CardConvergeReasonRequiredError`（收敛缺非空白理由）。新增错误码 `CARD_NOT_ACTIVE`、`CARD_CONVERGE_REASON_REQUIRED`，在 `error_codes.py`、`.ai/error-codes.md` 三处登记；`api/errors.py` 把 `CARD_NOT_ACTIVE` 映射到 409（理由缺失走默认 400）。

**迁移 0004**：建 `card_events`（STRICT）。`id` 服务端 `event_<毫秒>`、`card_id` 外键 `ON DELETE CASCADE`、`event_type IN (verified, converged)`、`reason` NULL 或非空白且 ≤500 字、`created_at` 用 `strftime` 往返；**converged 时 reason 条件必填**（`event_type!='converged' OR reason IS NOT NULL`）。两条触发器 `card_events_no_update` / `card_events_no_delete` 在数据库层强制 append-only；索引 `idx_card_events_card`。down 迁移 DROP 表（manifest 标 destructive_down）。

**仓储层**：新增 `CardEventRow` 与 `CardRow.events`；`list_events(card_id)` 追加序返回；`converge(card_id, reason)` 在**同一事务**内 UPDATE status + INSERT converged 事件；`verify` 改造为 UPDATE origin + INSERT verified 事件（reason 可选）。`get_by_id` / query / list_for_symbol / list_all 各读取路径都加载 events，保证「当前状态以 cards 为权威真源、card_events 是完整历史」。

**API**：`CardConvergeRequest`（reason 字段，`extra="forbid"`）、`CardEventRead`、`CardRead.events`；`PATCH /cards/{id}/converge` 收敛并回读带事件的完整卡（非 active → 409、缺理由 → 400、缺卡 → 404）。

**前端**：`CardSection` 按 active / converged 分组，active newest first；每张 active 卡有「收敛这张卡」按钮，展开内联理由表单（前端先校验非空白）；收敛卡移到「已收敛的主张」区，`opacity-60` 沉底弱化但**不隐藏**（红线 10）；每张卡底部展示事件时间线（verified「已对照出处」、converged「已收敛：<理由>」）。`api.ts` 补齐 CardStatus / CardEventType / CardEvent 类型，`listCards` 支持 status 过滤，新增 `convergeCard`。

**静态规则**：`check_append_only_triggers` 的 append-only 表清单加入 card_events，触发器缺失即静态检查红。

## ③ 得到了什么样的结果

| 项 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `pytest -q` | **514 passed**（K1 497 → +17：仓储 +6、API +6、迁移 +4、约束计数 +1） |
| 后端静态 | ruff / mypy(strict) | 全过（ruff 修复了 `__all__` 排序后 0 findings） |
| 前端 | `tsc -b` / oxlint / vitest / vite build | 全过（**vitest 62 passed** · oxlint 0 errors，5 个既有 set-state-in-effect warnings 均有意） |
| 端到端 | Playwright（构建产物 + Edge） | **15 passed**（14 + K2 收敛闭环） |
| 总门禁 | `scripts/dev.py check` | **ran 10 · passed 10 · failed 0 · skipped 0，退出码 0** |
| 约束台账 | constraints.json ↔ 真实库 | 一致，**52 项**（card_events 7 项，append_only=true） |

### 3.1 变异检查（2 条）

| # | 改坏哪里 | 结果 |
|---|---|---|
| M1 | 让 `converge` 只 `UPDATE status`、early return，**跳过事件写入** | `test_converge_moves_active_card_to_converged`、`test_converge_retire_active_card_with_a_reason`、`test_verify_then_converge_history_is_complete` **3 条变红** ✓，恢复后绿 |
| M2 | 从 0004 迁移**移除两条 append-only 触发器** | `test_the_event_stream_is_append_only` 变红（UPDATE/DELETE **DID NOT RAISE**）✓，恢复后绿 |

**说明**：M1 证明「状态变了但事件没写」会被仓储与 API 测试同时抓住；M2 证明数据库层 append-only 一旦失守，行为测试立即变红。两层防护（同事务双写 + 触发器）都有测试看门。

## ④ 留下了什么

- **K2 交付**：append-only `card_events` 表（0004 迁移）、verify/converge 同事务双写、需要理由的收敛出口（`PATCH {id}/converge`）、标的页 active/converged 分组与沉底弱化、事件时间线。知识层「记 → 核 → 收敛」的生命周期闭环完成。
- **编号对齐**：能力地图旧的「K2 图谱（双向链接）」与 spec 013 的「K2 生命周期」编号冲突，已把知识层表格对齐 spec：图谱改为「编号待定」并说明让位，K3 FSRS / K4 检索编号保留；能力总数 17 → 18。
- **边界记录**：`event_<millis>` 主键与 `card_<millis>` 同款，同毫秒两次创建会撞 UNIQUE；手动 UI 不触发、脚本化可能，待批量录入时与 cards/decisions 统一决策。
- **下一步候选**：K3 FSRS 复习队列（包名 `fsrs`、「已推迟」第三态需自建表）· K4 SQLite FTS5 检索 · 图谱双向链接（待编号）· specs 001/003 按 v3 修订（S0 剩余）· make eval 评测集骨架 · S5 前端构建产物接入 PyInstaller · 交易日早晨 ≥10:05 实测 spec 007 盘中假设。
