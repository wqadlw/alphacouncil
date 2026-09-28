# Spec 018 · K3 复习队列：FSRS 排程机制（切片 1）

- **状态**：Done（切片 1：机制 + 仓储 + 事务守卫；**无 API、无前端**）
- **目标阶段**：知识层（K1 卡片 → K2 生命周期 → **K3 排程**）
- **依赖**：K1（`cards`，spec 012）· K2（`card_events`，spec 013）· `fsrs` 已声明未 import
- **依据**：
  - 红线 7（**教训必须能再次遇到** —— 每条教训必须生成一条调度项）
  - ADR-0014（**三表分离，不合并** —— 本条同样适用：生命周期事件与复习事实是两种形状）
  - ADR-0021（知识库模仿「记忆」不模仿「文件系统」）
  - 宪法 4.6（四态；`unavailable` 不得打扮成答案）· 7.7（状态用枚举，不用布尔）

---

## 一、动手前先把五个问题问过 `fsrs` 本体

上一位 agent 留过一个探针脚本，问了五个问题但**结论没落库**。
设计不能建立在假设上，所以先实测（2026-09-28，`fsrs` 6.3.2）：

| # | 问题 | 实测答案 | 对设计的影响 |
|---|---|---|---|
| Q1 | `review_card` 会就地改传入的 `Card` 吗 | **不会**，返回**新对象** | 领域层可以放心传递，无需深拷贝防护 |
| Q2 | 关掉 fuzzing 后同一输入的 `due` 确定吗 | **确定**（4 次同输入 → 1 个 due） | 测试可断言精确的 due，不必用近似 |
| Q3 | `to_dict()` → `from_dict()` 无损吗 | **无损** | 状态可以整体存 JSON，不必拆成 7 列 |
| Q4 | 朴素 `datetime`（无 tzinfo） | **拒绝**：`ValueError: datetime must be timezone-aware and set to UTC` | 必须走 `core/time.py`，不能自己 `datetime.now()` |
| Q5 | `State` 有几态 | **三态**：`Learning=1` / `Review=2` / `Relearning=3` | **「已推迟」必须自建**（`status.md` 早已登记此事实） |

补充实测：

- `Card.to_dict()` 的键：`card_id, difficulty, due, last_review, stability, state, step`
- `card_id` 是 **int**，而我们的 `cards.id` 是 TEXT（`card_<毫秒>`）→ **需要一个 int 句柄**
- `Rating` 是**四档**：`Again / Hard / Good / Easy`（FSRS v6，不是五档）
- `Scheduler.reschedule_card(card, review_logs)` 的用途是**换调度器时重算**，
  **不是"推迟"**（实测传 datetime 直接 `TypeError`）
  → **推迟是我们的机制，不是 fsrs 的**
- `Scheduler.get_card_retrievability` 存在，**但本切片不调用**（见 §四）

---

## 二、数据契约（迁移 0005）

### 2.1 为什么是两张表（而不是塞进 `card_events`）

`card_events`（K2）是**生命周期**事件：罕见、带散文理由（`converged` 必填理由）。
复习事实是另一种形状：**高频、每张卡每次交互一行、字段全是结构化的**
（评分 / 新 due / 新状态 / 耗时）。

**按 ADR-0014 的先例分开，而不是合并。** 一张表两种形状会让条件必填的 CHECK
爆炸，而 CHECK 一多就等于没有。

### 2.2 `card_schedule` —— 当前排程状态（每张卡一行，**可变**）

它是"现在怎么样"的真源，与 `cards.status`（K2 的生命周期状态）**不是一回事**：
一张 `converged` 的卡仍然可以有排程行，只是不再进复习队列。

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | TEXT PK | FK `cards(id)` ON DELETE CASCADE |
| `fsrs_card_id` | INTEGER | **fsrs 只接受 int**，而我们的主键是 TEXT；这是内部句柄，**无语义** |
| `state_json` | TEXT | `fsrs.Card.to_dict()` **原文**（Q3 已验证无损往返） |
| `state` | TEXT | **我们的**枚举：`learning` / `review` / `relearning` / **`deferred`** |
| `due_at` | TEXT | ISO datetime，UTC，**索引列** |
| `enrolled_at` / `updated_at` | TEXT | 服务端时刻 |

**`state` 为什么多一态 `deferred`，而 `state_json` 不动**：
"现在不是时候"**不是一次失败**，不该改动记忆强度。
所以推迟只改 `state`（队列语义）与 `due_at`（何时回来），
**`state_json` 原封不动** —— 下次真正复习时从它重建 FSRS 卡，
稳定性一步都没被"推迟"污染。

> 用枚举而不是"是否推迟"的布尔（宪法 7.7）。

### 2.3 `card_reviews` —— append-only 复习流水

| 字段 | 说明 |
|---|---|
| `id` | `review_<毫秒>`，服务端生成 |
| `card_id` | FK，`card_events` 同款 |
| `outcome` | `reviewed` / `deferred` |
| `rating` | `again` / `hard` / `good` / `easy`；**`deferred` 时必为 NULL** |
| `reviewed_at` | 服务端时刻 |
| `duration_ms` | 「写下回答花了多久」（fsrs 的 `review_duration`）。**红线 11：只自省，不排名** |
| `from_due_at` / `to_due_at` / `from_state` / `to_state` | 这次交互把排程从哪推到哪 |

条件必填（ADR-0016 标准写法，不用 CASE WHEN）：

```sql
CHECK (outcome != 'reviewed' OR rating IS NOT NULL)
CHECK (outcome != 'deferred' OR rating IS NULL)
CHECK (outcome != 'deferred' OR duration_ms IS NULL)
```

**append-only 两触发器**，与 `decisions` / `watchlist_events` / `card_events` 同款。

---

## 三、领域层与接口

> ⚠️ **本切片只做到仓储层。** 下面 §3.3 的三个端点与 §3.1/§3.2 的 API 暴露**未实现** ——
> 见 §四"明确不做"的第一条。写在这里是为了固定接口形状，不是已完成清单。

### 3.1 `domain/scheduling.py`

- `ReviewRating(StrEnum)`：`AGAIN` / `HARD` / `GOOD` / `EASY`，映射到 `fsrs.Rating`
- `ScheduleState(StrEnum)`：`LEARNING` / `REVIEW` / `RELEARNING` / `DEFERRED`
- 错误：`CardNotScheduledError` · `CardAlreadyScheduledError` · `ReviewOutcomeRequiredError`

### 3.2 仓储 `storage/repositories/scheduling.py`

- `enroll(connection, card_id, *, now)` —— 首次排程（`state_json` 来自一张新 FSRS 卡）
- `due_cards(connection, *, as_of, limit)` —— `due_at <= as_of` 且 `state != 'deferred'`？**否** ——
  推迟的卡 `due_at` 已推后，**到期自然入队**，不需要额外条件（少一个状态条件少一处出错）
- `record_review(connection, card_id, rating|None, *, now, duration_ms)` —— **同事务**：写流水 + 更新 `card_schedule`
- `defer(connection, card_id, *, now, days)` —— 同事务：写 `deferred` 流水 + 只推 `due_at`、**不动 `state_json`**

### 3.3 API

| 端点 | 说明 |
|---|---|
| `POST /api/v1/cards/{id}/schedule` | 排程一张卡（= "生成调度项"） |
| `GET /api/v1/cards/due` | 今日到期队列（`as_of` 由调用方注入，可测） |
| `POST /api/v1/cards/{id}/review` | 交一次复习（`rating`）**或**推迟（`outcome=deferred`），请求体 `extra="forbid"` |

---

## 四、明确不做（且每条都有理由）

| 不做 | 理由 |
|---|---|
| **不存 / 不显示 `get_card_retrievability`** | 它是"你记住了多少"的预测概率 —— **那是成绩**。红线 2（只做过程不优化预测）+ 红线 9（不展示成绩）。机制在，**故意不用** |
| **不按 `duration_ms` 排名或做统计** | 红线 11 原文：「写下回答花了多久」**只用于自省**，不做排名 / 打卡。存下来是为了自省，不是为了比较 |
| 前端复习界面 | 本切片是机制。界面是独立一轮，**且它必须先回答"不讨好用户"怎么落地**（红线 13/14 目前无检查） |
| J5 教训 → 自动生成调度项 | J5 未开工。**所以红线 7 只能从 `none` 升到 `partial`，不能升到 `full`** |
| 不把 `cards.status` 与 `state` 合并 | 一张 `converged` 的卡可以有排程状态。合并会逼出布尔（宪法 7.7） |
| 不用 `reschedule_card` 实现推迟 | 实测它是"换调度器时重算"，与推迟无关 |
| 不把到期队列做成"第 N 张"编号 | 那是打卡 |

---

## 五、验收标准

- [ ] **AC-1（Schema）** 0005 建两表 + 索引 + 2 触发器；CHECK 完整；
      `manifest.json` / `constraints.json` / `APPEND_ONLY_TABLES` 三处同步；down 可执行；0004→0005 有集成测试
- [ ] **AC-2（确定性）** 关 fuzzing 时同一 `(card, rating, now)` 产出同一 `due`（Q2 已被测试钉住）
- [ ] **AC-3（无损）** 存进 `state_json` 再取出，`Card` 逐字段相等（Q3）
- [ ] **AC-4（推迟不污染记忆）** `defer` 后 `state_json` **逐字节不变**，`due_at` 推后，
      `state` 变 `deferred`，`card_reviews` 有一行 `outcome='deferred'` 且 `rating IS NULL`
- [ ] **AC-5（同事务）** 流水写成功但排程更新失败 → 两者都不变
- [ ] **AC-6（append-only）** 对 `card_reviews` 的 UPDATE / DELETE 被触发器拒绝
- [ ] **AC-7（tz）** 朴素 datetime 进不了系统（Q4 的约束由 `core/time.py` 承担，并有测试）
- [ ] **AC-8（API）** 三端点四态正确；`extra="forbid"`；错误码入册
- [ ] **AC-9（门禁）** `dev.py check` 10 道全过 + 退出码 0
- [ ] **AC-10（诚实）** `dev.py eval` 跑出新的通过率，**红线 7 从 `none` 升到 `partial` 并写明 gap**；
      baseline 按实际结果更新（不许为了好看升到 `full`）
- [ ] **AC-11（变异检查）** 每个新分支回答"改坏会不会红"，并**先确认变异真的生效**
