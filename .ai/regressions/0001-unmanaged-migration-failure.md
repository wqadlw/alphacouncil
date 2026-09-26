# 0001 · 迁移脚本失败以未受管的异常形状冒出来

- **发现日期**：2026-09-26
- **严重级别**：P1
- **状态**：已修复
- **发现方式**：写 `tests/integration/test_migrations.py` 的原子性用例时，先跑了一次探针看异常类型

## 现象

迁移脚本里有一个语法错误时，`migrate.apply()` 抛出的是 **`sqlite3.OperationalError`**，不是 `MigrationError`。

```
_run_script(c, 'CREATE TABLE ok (x TEXT);\nCREATE TABLE broken (;\n', 99)
→ type = sqlite3.OperationalError
  is MigrationError? False
  msg = near ";": syntax error
```

同一模块里其他每一种失败都带**受管错误码**：

| 失败 | 异常 | 码 |
|---|---|---|
| 库版本新于程序 | `DatabaseNewerThanAppError` | `STORAGE_DB_NEWER_THAN_APP` |
| 无升级路径 | `NoUpgradePathError` | `STORAGE_DB_NO_UPGRADE_PATH` |
| 快照失败 | `SnapshotError` | `MIGRATION_SNAPSHOT_FAILED` |
| **脚本写错** | ~~`sqlite3.OperationalError`~~ | **（无）** |

## 影响

**最可能发生的那一种失败，恰好是唯一没有受管码的那一种。**

后果有两层：

1. **调用方无法分支。** `api/errors.py` 的 `CODED_ERRORS`、启动路径的 `except MigrationError`，都会漏掉它 —— 一个"脚本写错"的迁移会以未映射的形状冒到用户面前，而 `.ai/error-codes.md` 已经为"迁移失败"写好了用户文案（「备份位于 `<path>`；可点击重试」），只是永远用不上。
2. **诊断信息不可行动。** `near ";": syntax error` 在 200 行的迁移文件里没有指向任何位置。

## 根因

`_run_script` 直接 `connection.execute(statement)`，没有 `try`。事务的原子性是对的（回滚确实把半套 DDL 撤掉了 —— 这一点探针同时验证了），但**失败的报告形状**没人管。

## 修复

`backend/src/alphacouncil/storage/migrate.py:328-337` —— 在语句循环内包裹 `sqlite3.Error`，转成 `MigrationError` 并带上「第几条 / 共几条」：

```
migration 2 failed at statement 2/2: near ";": syntax error
```

同一事务内，所以"失败后数据库完全没变"这条性质不受影响。

## 回归测试

`backend/tests/integration/test_migrations.py::TestAFailedMigrationLeavesNothingBehind::test_the_failure_is_reported_through_the_managed_code`

断言三条，全部写死字面量：

- `caught.value.code is ErrorCode.MIGRATION_FAILED`
- `"statement 2/2" in str(caught.value)`
- `isinstance(caught.value.__cause__, sqlite3.Error)` —— **原异常必须挂链**，否则真正的 SQLite 消息被吞掉

同文件另有两条同源用例：`test_the_version_is_not_bumped`、`test_the_partial_ddl_is_rolled_back`。

## 变异检查（⚠️ 必填）

| 改坏哪里 | 哪个测试变红 | 结果 |
|---|---|---|
| 把 `raise MigrationError(msg) from exc` 改回 `raise` | `test_the_failure_is_reported_through_the_managed_code` | ✅ **已确认变红** |

## 是否可被测试固化？

✅ 可以（运行时行为）。

## 遗留

`_run_script` 里**记录版本号**那一步的 `except` 标了 `# pragma: no cover`，但保留。实测 `PRAGMA user_version = N` 在可写连接上从不失败（越界也只是静默回绕，已由 `load_migrations` 的范围校验前移拦住）；唯一会失败的连接是只读的，而在只读连接上 DDL 会先失败。**删掉它反而会恢复本条缺陷**（未受管的失败形状），所以标注而不是删除。理由写在代码注释里。
