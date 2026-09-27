# Spec 013 · K2 卡片生命周期：状态留痕与收敛出口（Card Lifecycle）

- **状态**：Active
- **目标阶段**：知识层（K1 之后的自然延续）
- **依赖**：K1 卡片（spec 012：`cards` / `card_symbols`）· 迁移基础设施（0001–0003）· 错误码与静态检查子系统
- **依据**：
  - ADR-0021（知识库模仿「记忆」不模仿「文件系统」：S-01 必须有 `converged` 出口）
  - ADR-0022（K1 三字段与三种录入通道：「核对来源」升级**必须留痕**；需要一张升级留痕表）
  - 红线 4（结果之前记录，状态变更同样需要可追溯）
  - 红线 10（必须让用户面对不舒服的数据：收敛不等于删除或隐藏）
  - 红线 15（状态判定不由 agent 生成；收敛理由由用户亲手写）
  - `AlphaCouncil-基础功能打磨与AI桥接.md` §2.5 / §12（`ai_generated` 升级留痕）

---

## 一、背景与设计理念

K1 让卡片能够被录入、展示与核实，但盘点发现两个真实缺口：

1. **状态变更没有留痕（违反 ADR-0022）**
   K1 的 `verify` 直接 `UPDATE cards SET origin=...`，把一张卡从 `ai_generated` 升级为
   `user_written`，但**没有任何持久化记录**证明这次升级发生过、由谁、在什么时刻。
   `origin` 字段可变，与「只增不改」冲突——ADR-0022 明确要求「这次修改留痕」。

2. **卡片没有出口（违反 ADR-0021 S-01）**
   一张卡一旦是 `active`，当主张过时、被证伪或不再相关时，**无法退出**。
   没有出口的知识库会持续膨胀，最终变成没人愿意打开的文件柜；
   而记忆会「收敛」——处理完的材料移出当前主张集合。

K2 的核心不是加功能，而是把卡片从「只进不出的文件柜」变成「有出口、每次状态流转都留痕的记忆」：

> **一张 append-only 的状态事件表（`card_events`），加上一个需要理由的收敛出口。**

设计原则：
1. **每次状态/来源变更都追加一条不可改、不可删的事件**（数据库触发器强制 append-only）。
2. **当前状态仍以 `cards` 表为权威真源**（查询快、与 K1 一致），`card_events` 是状态流转的
   完整历史。两者在**同一事务**内写入，保证「状态变了必有事件、有事件状态必已变」。
3. **收敛必须写理由**：为什么这张卡不再代表当前主张。理由是用户亲手写的事实，不是 agent 的判断。
4. **收敛 ≠ 删除，也 ≠ 隐藏**：卡片仍保留并可见，只是退出「当前主张集合」、视觉弱化，
   并沉到「已收敛」区域（红线 10：用户必须看得到自己放弃过什么、为什么）。

---

## 二、数据契约：`card_events`（迁移 0004）

状态事件表，一张卡的每次状态/来源变更追加一行。

| 字段 | 类型 | 必填 | 约束 / 规则 | 说明 |
|---|---|---|---|---|
| `id` | TEXT | ✅ | PRIMARY KEY, `GLOB 'event_[0-9]*'` | 服务端生成 `event_<毫秒>` |
| `card_id` | TEXT | ✅ | FK `cards(id)` ON DELETE CASCADE, `length(trim)>0` | 归属卡片 |
| `event_type` | TEXT | ✅ | `IN ('verified','converged')` | 事件类型 |
| `reason` | TEXT | ➖ | NULL 或非空白，`length<=500`；**converged 时必填** | 变更理由 |
| `created_at` | TEXT | ✅ | `strftime('%Y-%m-%dT%H:%M:%fZ',…)=…` | 事件时刻（服务端） |

事件类型语义：

| `event_type` | 触发动作 | 卡片字段变化 | `reason` |
|---|---|---|---|
| `verified` | 「核对来源」 | `origin: ai_generated → user_written` | 可选 |
| `converged` | 「收敛/作废」 | `status: active → converged` | **必填** |

条件必填（ADR-0016 标准写法，不用 CASE WHEN）：

```sql
CHECK (event_type != 'converged' OR reason IS NOT NULL)
```

append-only 触发器（与 `decisions` / `watchlist_events` 同款）：

```sql
CREATE TRIGGER card_events_no_update BEFORE UPDATE ON card_events
BEGIN SELECT RAISE(ABORT, 'card_events is append-only: 状态变更不可修改'); END;
CREATE TRIGGER card_events_no_delete BEFORE DELETE ON card_events
BEGIN SELECT RAISE(ABORT, 'card_events is append-only: 状态变更不可删除'); END;
```

索引：`CREATE INDEX idx_card_events_card ON card_events(card_id);`

回滚（0004 down）：DROP TRIGGER → DROP TABLE，不影响 `cards` 内容。

---

## 三、领域层与仓储层

### 3.1 领域层（`domain/card.py`）

- 新增 `CardEventType(StrEnum)`：`VERIFIED="verified"` / `CONVERGED="converged"`。
- 新增错误类：
  - `CardNotActiveError`：对非 `active` 的卡执行收敛（例如已收敛的卡再次收敛）。
  - `CardConvergeReasonRequiredError`：收敛未提供非空白理由。

### 3.2 仓储层（`storage/repositories/cards.py`）

- 新增 `CardEventRow` dataclass（id/card_id/event_type/reason/created_at）。
- 新增 `list_events(connection, card_id) -> tuple[CardEventRow, ...]`（按 created_at ASC）。
- 改造 `verify`：在原 `origin` 校验通过后，**同一事务内**
  `UPDATE origin` + 插入一条 `verified` 事件（reason=None）。
- 新增 `converge(connection, card_id, reason, *, now=None) -> CardRow`：
  1. 取卡；不存在 → `CardNotFoundError`；
  2. `status` 非 `active` → `CardNotActiveError`；
  3. `reason` 为空白 → `CardConvergeReasonRequiredError`；
  4. **同一事务内** `UPDATE status=converged` + 插入一条 `converged` 事件（reason）；
  5. 返回更新后的 `CardRow`（status=converged，events 已含本次事件）。
- `_to_card_row` / 各列表读取一并加载 events（沿用 K1 symbols 的逐行加载模式，个人级数据量可接受）。

事务边界：`UPDATE` 与事件 `INSERT` 必须在同一事务，要么都成功要么都不发生。

---

## 四、接口规范（API）

Prefix：`/api/v1/cards`

### 1. `PATCH /api/v1/cards/{id}/converge`（新增）
收敛一张 active 卡。
- **请求体**（`extra="forbid"`）：`{ "reason": "渠道调研口径已被公司直营替代，该先行关系失效。" }`
- **响应**：`200`，返回更新后的 `CardRead`（status=converged，events 含本次）。
- **错误**：卡不存在 → 404（CARD_NOT_FOUND）；非 active → 409（CARD_NOT_ACTIVE）；
  理由空白 → 400（CARD_CONVERGE_REASON_REQUIRED）。

### 2. `PATCH /api/v1/cards/{id}/verify`（沿用，行为增强）
- 端点与入参不变；成功后除升级 `origin` 外，**自动写入一条 `verified` 事件**。

### 3. `CardRead` 增加 `events`
- 新增 `events: list[CardEventRead>`（默认空），字段：`id` / `event_type` / `reason` / `created_at`。
- 卡片在任何地方被读取（列表 / 详情 / 标的详情）都携带其状态事件历史，前端无需额外请求。

---

## 五、前端交互

1. **收敛操作**：每张 `active` 卡提供「收敛」按钮，点击展开内联理由输入（必填）+ 确认；
   提交后卡片退出当前主张集合。不做删除、不做编辑。
2. **已收敛区域**：
   - `active` 卡仍按 newest first 展示为「当前主张」；
   - `converged` 卡沉到页面底部「已收敛的主张」，**视觉弱化**（降低不透明度、灰化、去掉左侧分类色），
     但默认可见（红线 10），并显示收敛理由与时间。
3. **状态历史**：每张卡展示其事件——`verified` 显示「已对照出处 · 时间」；
   `converged` 显示「已收敛 · 理由 · 时间」。
4. 收敛后的卡不再显示「我已对照过出处」按钮；AI 生成卡未核实前不允许直接收敛的限制**不设置**
   （收敛一张未核实的 AI 卡是合法的「我不采纳这个猜测」，理由会留痕）。

---

## 六、验收标准（Acceptance Criteria）

- **AC-1（Schema）**：0004 迁移创建 `card_events` 表、索引与两条 append-only 触发器，CHECK 完整；
  `constraints.json` / `manifest.json` 同步；down 可执行；升级路径（0003→0004）有集成测试。
- **AC-2（留痕）**：`verify` 成功后必有一条 `verified` 事件；`converge` 成功后必有一条
  `converged` 事件且 `cards.status=converged`；事件与状态在同一事务（中途失败则都不变）。
- **AC-3（收敛校验）**：非 active 卡收敛 → CARD_NOT_ACTIVE；理由空白 → CARD_CONVERGE_REASON_REQUIRED；
  卡不存在 → CARD_NOT_FOUND。
- **AC-4（append-only 强制）**：对 `card_events` 的 UPDATE / DELETE 被触发器拒绝（行为测试）。
- **AC-5（API）**：PATCH converge 四态正确；CardRead 携带 events；verify 自动写事件。
- **AC-6（前端）**：可收敛（填理由）；converged 卡弱化沉底、显示理由；状态历史可见；
  新增/更新一条 E2E 覆盖收敛闭环。
- **AC-7（门禁）**：后端 ruff / mypy / pytest 全绿；前端 tsc / oxlint / vitest / build 全绿；
  `dev.py check` 10 道全过。

---

## 七、已知的失败（验收时该检查什么）

- **只改 `cards` 状态却忘了写事件**（或反之）：必须同事务；用「断开事件写入」的变异测试验证会变红。
- **用静默 UPDATE 冒充留痕**：事件表若不是 append-only，留痕就是假的（触发器 + 行为测试）。
- **收敛变成删除/隐藏**：违反红线 10；converged 卡必须仍可见、带理由。
- **收敛理由由 agent 代填**：违反红线 15；理由只能来自用户输入。
- **沿用 K1 同毫秒主键问题**：`event_<毫秒>` 同 K1，脚本化同毫秒两次可能撞键；人工 UI 不触发，
  与 K1 一并记录，待批量/脚本录入时统一决策。
