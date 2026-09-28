# 0006 · 卡片的"状态变更"与"记录这次变更"从来不在一个事务里

- **发现日期**：2026-09-28
- **严重级别**：P1
- **状态**：已修复
- **发现方式**：**为 K3 写测试时踩进了同一个坑**。我给新写的
  `scheduling.record_review` 加了事务，然后发现 API 路由里早就有一层 `transaction()` ——
  于是去查"事务到底归谁"，查出了这条**已经上线两天**的缺陷。
- **发现者**：OpenCode（与 0004/0005 同一天，同一个人）

---

## 现象

`cards.verify()` 与 `cards.converge()` 的 docstring 都写着状态 UPDATE 与事件 INSERT
"是同一个事务"（`converge` 的原话：**"The status UPDATE and the event INSERT are one
transaction"**）。

**它们不是。** 而且不止不是 —— 整个仓库里**没有任何一个仓储函数**开事务；
**七个写路由全部在路由层开**（`api/routes/` 的 `cards` ×3、`decisions` ×1、`watchlist` ×3）。

实测（`regressions/0004` 的探针脚本改一改）：

```
converge raised: blocked                    ← 事件 INSERT 被触发器挡下
status after the failure : converged        ← 状态已经改了
events after the failure  : 0               ← 而且没有任何记录

>>> NOT ATOMIC: the card says 'converged' with no record of why.
```

## 根因

`storage/db.py` 用 `sqlite3.connect(..., isolation_level=None)` 打开连接 ——
**autocommit**。项目里本来就有 `db.transaction()`（显式 `BEGIN` / `COMMIT` / `ROLLBACK`），
但只有 `migrate.py` 用它。

而 `with connection:` 在 autocommit 连接上**不开事务** ——
`sqlite3` 的上下文管理器只在连接**不是** autocommit 时才隐式 `BEGIN`。
所以"看起来像事务"的写法在这里什么也没做。

**为什么它躲过了所有门禁**：

1. 10 道门禁全绿 —— 没有任何一道检查"这个函数是不是原子的"；
2. 单元测试全绿 —— 测试**经由 HTTP 路由**调用，路由开了事务，所以是原子的；
3. K2 的 `card_events` 表有完美的 append-only 触发器 —— **它忠实地保护了那些事件，
   问题是需要保护的那条事件根本没写进去。**

> 这与 `0002`（从不被解析的台账）、`0003`（从未运行的检查）是同一族：
> **不是写错了，是"在唯一会暴露它的那条路径上，没人去看"。**

## 修复

不能简单地把事务挪进仓储：项目的成文决定是
`db.transaction()` **"不支持嵌套"**（"savepoint 会掩盖调用方的错误而不是报出来"），
而路由层的两个 `watchlist` 端点**确实**需要跨"读 + 写"的事务。

所以仓储**既不开事务，也不静默继续 —— 它检查**：

```python
# storage/db.py
def require_open_transaction(connection, *, operation) -> None:
    if not connection.in_transaction:
        raise RuntimeError(f"{operation} writes more than one row and must run inside ...")
```

- 路由层**一个字没改**（七个写端点照旧开事务）
- **任何绕过路由的调用**（脚本、测试、将来的后台任务、数据迁移）
  **会立刻大声失败，而不是静默丢掉原子性**

已接入：`cards.verify` · `cards.converge` · `scheduling.record_review` · `scheduling.defer`。

## 回归测试

`backend/tests/unit/test_card_lifecycle_atomicity.py`（10 项）

| 用例 | 挡什么 |
|---|---|
| `test_a_card_does_not_retire_without_a_record_of_why` | 让事件 INSERT 失败，断言状态**没动** |
| `test_a_card_is_not_upgraded_without_a_record` | 同上，`verify` |
| `test_converge_without_a_transaction_is_refused` / `test_verify_...` | **守卫本身** |
| `test_the_happy_path_still_writes_both` ×2 | 守卫**没有**把写入变成 no-op |
| `test_autocommit_is_the_cause_not_a_missing_trigger` | 钉住机制：`isolation_level is None` |
| `test_a_bare_with_connection_block_does_not_open_a_transaction` | 钉住那个"看起来对"的写法 |

断言的期望值是**数据库里的事实**（`status`、`len(events)`），
不引用任何被测常量。

## 变异检查

| 改坏哪里 | 结果 |
|---|---|
| `require_open_transaction` 不再检查（M5） | ✅ 4 failed |
| `cards.converge` 不再要求事务（M6） | ✅ 1 failed |

## 顺带记录：这次踩的**测试**坑（与产品无关，但更隐蔽）

我第一版把回滚测试写成：

```python
with _in_tx(connection), pytest.raises(...):   # ← 错
    repo.converge(...)
```

`with A, B:` 意味着 B 先 `__exit__`。**`pytest.raises` 先捕获了异常，
事务上下文管理器从未见到失败，于是它 `COMMIT` 了。**

结果：一张卡**在"测试证明它不会发生"的同时**被改成了 `converged`。
症状看起来和真 bug 一模一样。

正确写法是 `pytest.raises` 在**外层**。而 `ruff` 的 **SIM117 恰恰要求把它们合并**
——照做就重新引入这个 bug。

**处理**：两种模式各收进一个 helper（`_expect_rollback` / `_in_tx`），
helper 里那一行标 `# noqa: SIM117` 并写明理由。
**一个豁免、一处解释，胜过八份复制。**

## 是否可被测试固化？

✅ 可以（事务行为是运行时事实，可通过让第二段语句失败来复现）。

## 遗留

- **`decisions.append` / `watchlist.append` 仍是"调用方开事务"且无守卫。**
  本次只给"写两张以上表"的四处加了守卫；这两个写一张表，原子性风险低，
  但**约定仍然只存在于人的记忆里**。已登记进 `status.md` §五。
- **`db.transaction()` 仍然拒绝嵌套**，这是成文的决定，本次没有推翻它。
  如果将来出现"仓储必须自己开事务"的需求，该决定需要重新审视（走 ADR）。
