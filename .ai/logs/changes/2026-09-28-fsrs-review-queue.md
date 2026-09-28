# 2026-09-28 · K3 复习队列与回归 0006（spec 018）

> 四段式台账（宪法 10.5）。**append-only：只追加，不改写。**
> 执行者：OpenCode（Codex · Space Bunny Free）· **同一天第四批**

---

## ① 想做什么

路线图上的下一块：**K3 FSRS 队列**。它是红线 7「教训必须能再次遇到」的强制手段，
也是 `status.md` 里唯一一条"依赖已装但从未 import"的项（`fsrs` 声明了两年）。

但这一轮真正发生的事不是 K3，是它**顺手带出来的 0006**。

## ② 做了什么

### 1. 先问库（K3 的五个探针问题重做）

上一位 agent 留过一个探针脚本、问了五个问题、**结论没落库**。
设计不能建立在假设上，所以重做一遍（`fsrs` 6.3.2）：

| # | 问 | 答 | 对设计的影响 |
|---|---|---|---|
| Q1 | `review_card` 就地改传入对象吗 | **不会**，返回新对象 | 可以放心传递 |
| Q2 | 关 fuzz 确定吗 | **确定** | 测试可断言精确 due |
| Q3 | `to_dict`→`from_dict` 无损吗 | **无损** | 状态整体存一列 JSON，不必拆七列 |
| Q4 | 朴素 datetime | **拒绝** | 必须走 `core/time.py` |
| Q5 | `State` 几态 | **三态** | **"已推迟"必须自建** |

追加实测：`card_id` 是 **int**（我们的主键是 TEXT）· **四档**评分 ·
**`reschedule_card` 不是推迟**（传 datetime 直接 `TypeError`，它是"换调度器时重算"）
→ **推迟是我们的机制**。

### 2. K3 机制（spec 018）

- 迁移 0005：`card_schedule`（每卡一行当前排程，可变）+ `card_reviews`（append-only 流水）
- 两表分开的理由：**ADR-0014 的先例 —— 分开不合并**（生命周期事件罕见带理由，
  复习事实高频全结构化）
- `ScheduleState` **四态**，多一个 `deferred`；⭐ **推迟只动 `due_at` 与队列态，
  `state_json` 逐字节不变** —— "现在不是时候"不是一次失败，不该改记忆强度
- ⭐ **不调用 `get_card_retrievability`**：它是"你记住了多少"，**那是成绩**。
  有 **AST 级**测试钉住"永远不调用"（用 AST 而不是字符串，因为两个模块的
  docstring 都要**故意提到**这个方法名来说明我们不用它）
- 新卡 `due` 取**注入的 `now`** 而非墙钟 —— 否则"到期了吗"取决于测试何时跑

### 3. ⭐ 回归 0006：上线两天的 P1，**顺带查出**

我给自己的新函数加了事务，随即发现 API 路由里**早就**有一层 `transaction()`。
去查"事务归谁"，查出：

```
converge raised: blocked              ← 事件 INSERT 被挡下
status after the failure : converged  ← 状态已经改了
events  after the failure : 0         ← 没有任何记录
```

**七个写路由全部在路由层开事务，整个仓库没有一个仓储函数开。**
而 `cards.converge` 的 docstring 明写 "The status UPDATE and the event INSERT
are one transaction"。

根因：`db.py` 用 `isolation_level=None`（autocommit），
而 **`with connection:` 在 autocommit 连接上不开事务**。

**它躲过了什么**：10 道门禁全绿、单元测试全绿、append-only 触发器完美。
**测试之所以全绿，是因为测试经由 HTTP 路由调用，而路由开了事务** ——
唯一会暴露它的那条路径，恰好是唯一有人测过的那条路径。

**修法**（不是"把事务挪进仓储"）：项目的成文决定是 `db.transaction()` 拒绝嵌套，
而两个 `watchlist` 端点确实需要跨读写事务。所以仓储**既不开也不静默 ——
它检查**：

```python
def require_open_transaction(connection, *, operation) -> None:
    if not connection.in_transaction:
        raise RuntimeError(...)
```

**七个路由一个字未改**，而任何绕过路由的调用会**立刻大声失败**。

## ③ 得到了什么样的结果

### 门禁

`dev.py check` **10 道全过 + 退出码 0**；测试 563 → **615**；变异 **6/6 变红**。

### eval：诚实的结果是**通过率没变**

```
5 / 15 guarded (33.3%)  ·  coverage: full 5 · partial 3 · none 7
```

红线 7 从 `none` 升到 **`partial`**，而 **`partial` 不算通过**，所以 5/15 一动不动。

**这就是 T-19 的意思**：K3 落地了机制，但「每条教训自动生成调度项」还没有 ——
本项目根本没有「教训」这个类型，J5 未开工，**是用户手动排程的**。
把 `partial` 算成通过会让数字好看，文档就是假的。

### 三个我在自己的测试里犯的错（都不是产品 bug）

| # | 错 | 后果 | 修法 |
|---|---|---|---|
| 1 | `with _in_tx(...), pytest.raises(...)` | **`pytest.raises` 先捕获 → 事务 `COMMIT` 了半截写入** | `pytest.raises` 必须在外层；两种模式各收进一个 helper |
| 2 | 变异脚本 `read_text()` 读、`write_text(newline="")` 写 | 把两个文件整体 CRLF→LF，并**自己报"恢复失败"** | **读和写都要 `newline=""`** |
| 3 | 变异脚本把选择器当单个 argv 传 | 收集 0 个测试，退出码非 0 → **报成"已抓住"** | 收集 0 个 = harness 错误 |

第 1 条最值得记：**`ruff` 的 SIM117 恰恰要求把它们合并** —— 照做就重新引入这个 bug。
已用 `# noqa: SIM117` + 写明理由的 helper 收口。

> 三个都是同一族：**一个不会变红的断言装置**。0004 的假绿、spec 017 的 harness 假绿、
> 这次的 harness 假绿与嵌套顺序 —— 全都是"绿色的测试什么都没测"。

## ④ 留下了什么

### 新机制

- **`card_schedule` + `card_reviews`**（0005）
- **`ScheduleState.DEFERRED`** —— 推迟不污染记忆
- **`db.require_open_transaction()`** —— 把"调用方开事务"这条**只存在于记忆里的约定**变成机制
- **回归 0006** + 10 项测试
- **`comparison` 约束类别** —— 旧的六种形状都装不下 `fsrs_card_id > 0`，
  **宁可加一类，也不把新约束塞进近似类别**（错误比缺失更贵）

### 新登记的缺口

- **`decisions.append` / `watchlist.append` 仍无守卫**（只写一张表，风险低，但约定仍在记忆里）
- **`db.transaction()` 拒绝嵌套是成文决定，未推翻** —— 它间接导致了 0006，
  本次选择兼容而非推翻。将来若要改需走 ADR。

### 本条**没有**做的事

| 不做 | 为什么 |
|---|---|
| API 三端点 + 前端复习界面 | 界面必须先回答"不讨好用户怎么落地"（红线 13/14 目前无检查） |
| J5 教训转卡 | 所以红线 7 只能 `partial` |
| 把 `partial` 算成通过 | 数字会好看，文档就是假的 |
| 用 `get_card_retrievability` | **那是成绩**（红线 2/9） |
| 合并 `cards.status` 与 `state` | 一张 `converged` 的卡仍可有排程状态；合并会逼出布尔（宪法 7.7） |
| 按 `duration_ms` 排名 | 红线 11 明文禁止 |
| 推 GitHub | 悬空的 `origin/main` 仍未修 |
