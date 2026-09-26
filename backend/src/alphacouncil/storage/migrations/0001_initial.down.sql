-- 0001_initial · 回滚
--
-- ⚠️ **这是破坏性回滚。** 它会删掉 `decisions` 与 `audit_log` 的全部内容 ——
-- 也就是用户"在结果之前写下的文字"，那是不可再生的证据（红线 4）。
--
-- 所以它**不是一条可随意执行的退路**，而是"把库退回空 schema"的运维动作。
-- `migrations/manifest.json` 把本迁移标为 `destructive_down: true`，
-- 迁移器在未显式传 `--allow-destructive` 时**拒绝执行**（ADR-0012 规则 2：
-- 确实不可逆时必须显式声明并说明理由，而不是假装它可逆）。
--
-- 正确做法：升级前先做 `VACUUM INTO` 快照（ADR-0012 规则 3），要退回就从快照恢复，
-- 而不是跑这个文件。这个文件的存在是为了"schema 可还原"，不是为了"数据可还原"。
--
-- 顺序：先删触发器与索引，再删视图，最后按外键依赖的逆序删表。

DROP TRIGGER IF EXISTS audit_log_no_delete;
DROP TRIGGER IF EXISTS audit_log_no_update;
DROP TRIGGER IF EXISTS decisions_no_delete;
DROP TRIGGER IF EXISTS decisions_no_update;
DROP TRIGGER IF EXISTS watchlist_events_no_delete;
DROP TRIGGER IF EXISTS watchlist_events_no_update;

DROP INDEX IF EXISTS audit_log_target_idx;
DROP INDEX IF EXISTS decisions_symbol_idx;
DROP INDEX IF EXISTS watchlist_events_symbol_idx;

DROP VIEW IF EXISTS watchlist_current;

-- 逆外键序：watchlist_events / decisions 都引用 instruments
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS decisions;
DROP TABLE IF EXISTS watchlist_events;
DROP TABLE IF EXISTS instruments;
