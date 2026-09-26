# 变更记录 · 2026-09-26 · 仓储层与薄 API + 测试与文档同步

- 日期：2026-09-26
- 类型：架构变更（把领域规则接到 HTTP 边界）+ 测试补齐 + 由写测试发现的 7 处缺陷修复
- 范围：
  - 新增 `backend/src/alphacouncil/storage/repositories/{__init__,instruments,watchlist}.py`
  - 新增 `backend/src/alphacouncil/api/{deps,errors}.py` · `api/routes/{__init__,instruments,watchlist}.py`
  - 新增 `backend/src/alphacouncil/core/time.py`
  - 新增 `backend/tests/unit/test_storage.py` · `test_watchlist_api.py` · `backend/tests/integration/test_migrations.py`
  - 修改 `api/app.py` · `storage/migrate.py` · `storage/db.py` · `storage/constraints.json` · `storage/migrations/0001_initial.up.sql`（**仅注释**）· `core/error_codes.py` · `checks/rules/check_error_codes.py` · `tests/conftest.py`
  - 修改 `.ai/status.md` · `.ai/error-codes.md` · `.ai/regressions/`
- 依据：宪法 5.1 / 5.4.2 / 5.4.3 / 5.5 · 6.3 · 8.1 / 8.3 · 第零条 0.2 · ADR-0011 / 0012 / 0016 / 0017 · `.ai/status.md` S1 与 D1

---

## 1. 为什么改

### 1.1 #23：规则齐了，但没有一条路径能写入

上一轮结束时，D1 关注池的状态是：表在、约束在、触发器在、领域规则在（覆盖率 100%）——**但没有任何代码能把一条记录写进去**。P0 的验收句是「能把自己关注的 10 只票加进去（带理由）」，而当时连一个 HTTP 端点都没有。

同时有一处**形状不一致**必须先解决：

> FastAPI 的 `HTTPException` 返回 `{"detail": ...}`，而业务错误返回五字段信封 —— **同一个失败被两种形状报告**，正是 `.ai/error-codes.md` §1 警告的情况。
> 改法：**让领域抛带码的错误**，API 只负责映射状态码。

### 1.2 #24：注释里的规则不是规则

`manifest.json` 与 `constraints.json` 的 `$comment` 都写着同一句话：

> 「本文件与 `.sql` 文件由 `tests/unit/test_storage.py` 交叉校验」

**那个文件不存在。** 全仓 `find . -name "test_storage*.py"` 返回空。也就是说，两个 JSON 文件里所有"会被校验"的承诺，写下时就是空的 —— 而这恰好是本项目一直在防的那类缺陷：**一条从未失败过的检查，很可能从未运行过**。

于是 #24 的实质不是"补测试"，而是**把两句空话兑现，并看看兑现时会暴露什么**。结果暴露了 7 处（见 §3）。

---

## 2. 改了什么

### 2.1 仓储层（`storage/repositories/`）

| 文件 | 关键决定 |
|---|---|
| `instruments.py` | `ensure()` —— 已存在则**校验** `asset_type`，不一致抛 `AssetTypeConflictError`。不静默覆盖：`600519` 是股票，如果哪天被当成指数写进来，那是数据源错了，不是"更新一下就好" |
| `watchlist.py` | `append()` **先 `ensure` 标的再追加事件**，两步同一事务 —— 否则会出现"事件存在但没有对应标的"的行。`current()` 走 `watchlist_current` 视图，不自己写 `MAX(id)` 子查询：视图是 schema 的一部分，重复实现等于给同一个规则两份定义 |

### 2.2 薄 API（`api/`）

| 决定 | 理由 |
|---|---|
| 领域抛**带码**的错误，API 只做 `_STATUS_BY_CODE` 映射 | 状态码是 HTTP 的词汇，不是业务规则的词汇。写在领域层会让领域依赖传输协议 |
| `WatchlistState` 放在 `domain/` 而非 `api/` | 它是"规则"的输入（`require_followed` 的入参）。放在 `api/` 会让 `storage` 反过来依赖 `api` |
| `require_followed` **用返回值**解决窄化，不用 `assert` | `assert` 在 `-O` 下会被剥掉，而"已移出还能改理由"必须在任何构建下都被拦住 |
| `resolve` 的歧义返回 **200 带 `candidates`**，不是错误 | 输入只差一个答案就合法了 —— 那是**问题**，不是失败。往信封里塞第六个键会破坏"恰好五键"的契约 |
| **刻意没有 `DELETE`** | `DELETE /watchlist/{ticker}` 会暗示"删掉它"。关注池是 append-only 的，"移出"是一条新记录。实测 `client.delete(...)` → **405** |
| 测试隔离：`_isolated_database` autouse fixture | app factory 在启动时跑迁移，所以 `TestClient(create_app(Settings()))` 会迁移**开发者自己的库**。这不是假设 —— 2026-09-26 真的发生了 |

### 2.3 测试（+57 项）

| 文件 | 项数 | 覆盖的"必须被拒绝" |
|---|---|---|
| `tests/unit/test_storage.py` | 33 | 清单↔目录双向 · **约束台账↔真实 schema 双向** · 类别↔形状 · append-only 三方一致 · 版本越界 · 截断脚本 · `:memory:` 不被当成路径 |
| `tests/integration/test_migrations.py` | 34 | 全新安装 · 升级保数据 · **快照在升级之前且内容属于旧版本** · 每次重试新文件 · 库新于程序拒绝 · 无路径拒绝 · 失败迁移的原子性 · 回滚授权 · 连接剖面 · 触发器真拦 |
| `tests/unit/test_watchlist_api.py` | 32 | 理由三层防线 · 歧义是问题不是错误 · **两条理由都还在盘上** · 无 DELETE · 信封恰好五键 · 被拒的写入连 instrument 一起回滚 |

`constraints.json` 的交叉校验是**双向**的，两个方向各挡一类事故：

- 台账列了但库里没有 → 声明是空头支票
- **库里有但台账没登记** → 这次修复里"顺手加一条约束、忘了更新台账"的经典事故，且**不会有任何报错**

---

## 3. 实测证据（可复现）

| 项 | 命令 | 结果 |
|---|---|---|
| 单测全量 | `pytest -q` | **373 passed**（本轮 +57） |
| 覆盖率 | `pytest --cov=alphacouncil` | **TOTAL 94%**；`storage/` **5 个模块全 100%** · `domain/` 100% |
| 静态检查 | `ruff check .` · `mypy` | `All checks passed!` · `Success: no issues found in 66 source files` |
| 静态检查（全量） | `python -m checks` | `ran 12 · skipped 3 · crashed 0 · findings 14 (0 error, 0 warning, 14 info)` —— 与上轮一致（S-04 保持 PASS，3 条 skip 是前端红线 S-07/08/09） |
| 质量门禁 | `scripts/dev.py check-lite` | `ran 4 · passed 4 · failed 0`，exit 0 |
| 质量门禁 | `scripts/dev.py check` | `ran 5 · passed 4 · failed 1`，exit 1 —— 失败的是 `check-static`（**T-19：skip 不算通过**），符合预期 |
| ⭐ **变异检查** | 逐条改坏后跑对应用例 | **17 / 17 全部变红**，四个被改文件按 SHA-256 校验恢复原样 |
| 测试隔离 | 真实库 mtime | 保持 `19:42:10` 不变（修好之前每次 pytest 都会动它） |

### 3.1 ⭐ 写测试时暴露的 7 处缺陷

这一节是本轮最有价值的产出。**7 处里有 5 处不是"写错了"，而是"从来没有人看"**。

#### D-A · `constraints.json` **根本不是合法 JSON**（P1）

```
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 8 column 17
```

第 8、12 行有未转义的 ASCII `"`（`"迁移里漏掉一条约束"`）。**任何 `json.loads` 都会抛错。**

后果比"格式错"严重：这个文件**从未被任何程序读过**。它和 `manifest.json` 里"由 `tests/unit/test_storage.py` 双向比对"那句话，在被写下的那一刻就是**无法成立的承诺** —— 因为被承诺的测试文件也不存在。两份 JSON 互相引用对方会被校验，而两边都没有校验者。

修复：内层引号改 `「」`；补上 `tests/unit/test_storage.py`。

#### D-B · 3 条约束记错了类别（P2）

`decisions_rationale_required_check` 的形状是 `length(trim(rationale)) > 0`。而宪法 5.4.2 第 5 类被**明确限定**为 `A OR B IS NOT NULL` 写法（「条件必填用 `A OR B IS NOT NULL` 写法，不用 `CASE WHEN`」）。这个形状属于**5.4.3 的必填规则**，不是 5.4.2 的条件必填。

错位 3 条：`decisions_rationale_required_check` · `decisions_counter_evidence_required_check` · `audit_log_action_not_blank_check`。

**记错类别此前是不可见的** —— 全仓没有任何代码读这个字段，它是纯声明。修复：新增第 6 类 `required`（来源标注宪法 **5.4.3**，与 5.4.2 的五类并列），3 条归位。测试按**形状**校验类别，所以再错位会红。

#### D-C · `0001_initial.up.sql` 把 `constraints.json` 的位置写错了（P2）

原文「外置清单见同目录 `constraints.json`」。实际：`.sql` 在 `storage/migrations/`，清单在 `storage/`。修复为「上级目录」。

#### D-D · 迁移脚本失败抛**裸 `sqlite3.OperationalError`**（P1）

```
_run_script(c, 'CREATE TABLE ok (x TEXT);\nCREATE TABLE broken (;\n', 99)
→ type = sqlite3.OperationalError   is MigrationError? False
```

本模块其他每一种失败都带受管错误码（`DatabaseNewerThanAppError` / `NoUpgradePathError` / `SnapshotError`），而**最可能发生的那一种**（脚本写错）会绕过所有 `except MigrationError`，以未映射的形状冒到用户面前。

修复：`_run_script` 内包裹，消息带「第几条 / 共几条」。`sqlite3.OperationalError: near ";": syntax error` 在 200 行的迁移文件里不是可行动的信息。

#### D-E · `PRAGMA user_version` **越界静默回绕**（P2）

```
PRAGMA user_version = 2147483648  →  读回 0
```

`user_version` 是 32 位有符号整数，**不报错，直接回绕**。`manifest.json` 里一个版本号笔误会造出一个"看起来永远升不上去"的库，且不记任何日志。

修复：`load_migrations` 读清单时校验 `1..MAX_VERSION`（与它已经在做的"连续性校验""文件存在校验"同一性质 —— 校验自己的输入）。

#### D-F · `split_statements` 里有一个不可达分支（P2）

`if buffer.strip():` —— 实测 `sqlite3.complete_statement("   ")` 返回 **`False`**，所以它返回 `True` 时 buffer 一定含 `;`，`strip()` 永远为真。

修复：删除。判据与上一轮删 `isinstance(raw, str)` 相同（宪法第零条 0.2：能移到别处的检查必须移）。

#### D-G · `db.resolve_database_path` 没有任何调用方（P2）

全仓只有定义处与 `__all__` 各一处引用。`api/deps.py` 直接用 `settings.database_path`。它的 docstring 说"供 CLI 的 `--database` 使用"，而那个开关不存在。

修复：删除。（与上一轮删 `parse_millis` 同一判据：不留未用代码。）

### 3.2 变异检查明细（17 条，全部变红）

| # | 改坏哪里 | 变红的用例 |
|---|---|---|
| 1 | 永不拍快照 | `test_the_snapshot_is_taken_and_verified` |
| 2 | **快照改到升级之后拍** | `test_the_snapshot_holds_the_state_from_before_the_upgrade` |
| 3 | **版本号提到事务之外** | `test_the_version_is_not_bumped` |
| 4 | 失败时 `COMMIT` 而不是 `ROLLBACK` | `test_the_partial_ddl_is_rolled_back` |
| 5 | 破坏性回滚不再需要授权 | `test_a_destructive_rollback_is_refused_by_default` |
| 6 | SQL 失败不包裹成 `MigrationError` | `test_the_failure_is_reported_through_the_managed_code` |
| 7 | 版本断档当成可升级 | `test_a_gap_with_no_path_is_refused` |
| 8 | 库新于程序时静默降级 | `test_a_newer_database_is_refused` |
| 9 | 台账列一条库里没有的约束 | `test_every_ledger_constraint_exists_in_the_schema` |
| 10 | **库里长出一条台账没登记的约束** | `test_every_schema_constraint_is_registered` |
| 11 | 类别记错 | `test_constraints_have_the_shape_their_category_claims` |
| 12 | append-only 标志被拿掉 | `test_every_table_with_triggers_is_declared_append_only` |
| 13 | **多出一个没登记的 `.sql` 文件** | `test_every_sql_file_is_registered` |
| 14 | 接受存不进去的版本号 | `test_a_version_that_cannot_be_stored_is_refused` |
| 15 | 清单缺失当成"没有迁移" | `test_a_missing_manifest_is_refused` |
| 16 | 截断的脚本静默接受 | `test_a_truncated_script_is_refused` |
| 17 | `str` 路径被当成 `Path` | `test_a_string_is_passed_through_to_sqlite` |

加粗的三条是"**只改一个字符、后果完全静默**"的类型：快照拍在升级后（备份里有新表，回滚回去得到混合状态）、版本号脱离事务（库升到一半留下半套 schema）、库里有未登记的约束（台账从此不是完整清单）。

---

## 4. 有意保留 / 未改的

- **`_run_script` 里 PRAGMA 失败的 `except` 标了 `# pragma: no cover`，但保留**。实测 `PRAGMA user_version = N` 在可写连接上**从不失败**（越界也只是回绕，已由 D-E 的校验前移拦住）；唯一会失败的连接是只读的，而在只读连接上 DDL 会先失败。所以这个分支经公开接口不可达 —— **删掉它反而会恢复刚修好的 D-D**（未受管的失败形状）。标注比删除更诚实。
- **只改了 `0001_initial.up.sql` 的**一行注释**，未动任何 SQL**。严格说"已发布的迁移不改"（宪法 5.1），本轮的理由是：该迁移从未发布（仓库还没有 CI、程序从未运行过、唯一的库是测试建的、4 表全 0 行），且改的是把读者指向错误目录的注释。**记录在案，不做默认做法。**
- **`models/market.py` 的 `Symbol.code` 仍用 `^\d{6}$`（Unicode 宽松）**，未改。已在 `domain/instrument.py` 的注释里写明，`domain` 层是唯一的入口。
- **`constraints.json` 的 `$comment` 改为描述"六类 + 两个章节来源"**，并写明 `identity` 与 `required` 的边界（前者含"给了就不能空白"，后者是"必填且非空白、没有 NULL 分支"）。

---

## 5. ⚠️ 未做（不假装做过）

| 项 | 状态 |
|---|---|
| **升级路径只测了合成的链** | ⚠️ `0→1→2` 里的 2 是测试里造的（`0002_notes`）。**真实的 `1→2` 迁移还不存在**，所以"升级链"这件事只在合成意义上被验证过 |
| **形状标记不覆盖全部类别对** | ⚠️ `identity` 与 `conditional_required` 在"同字段 NULL 守卫"（`x IS NULL OR length(trim(x)) > 0`）上**仍可能互相误报**。已在测试 docstring 写明，没有假装它是严密的 |
| **`constraints.json` 只比对名字与形状，不比对表达式文本** | ⚠️ 有意为之（SQLite 会规范化表达式文本，比对字符串会引入脆弱的空白差异）。所以"约束存在但逻辑写反了"不会被这个测试抓到 —— 那要靠行为测试 |
| **`000xxx` 歧义段仍未与真实数据源核对** | ⚠️ 段表是手写规则。已记入 `.ai/status.md` §五 |
| **前端（S2）** | ❌ 未开始。`000xxx` 让用户选市场的界面、标的页都还没有载体 |
| **`.ai/regressions/` 的正式记录** | ⚠️ 本轮**第一次填写**（见该目录 `0001` / `0002`）。规则第 3 条要求"每个缺陷一个测试文件"，本轮两个缺陷的测试位于 `tests/integration/test_migrations.py` 与 `tests/unit/test_storage.py`，**没有单独建文件** —— 理由与偏差已写进记录 |
| **`core/config.py` 的 v1 检索配置** | ❌ 仍未清理（`qdrant_*` / `langfuse_*` / `embedding_*` / `reranker_*` / `recall_top_k` / `rerank_top_k` / `enable_graph_retrieval` / `enable_text2sql`）。违背 ADR-0006，且 `/health` 还在汇报不存在的检索层。需要专门一轮（会动 `test_config.py` 4 个用例） |
| **`models/domain.py` 的 `ResearchReport` / `ResearchRequest`** | ❌ 未删（撞红线 15）。**待主人确认** |
| **CI 配置** | ❌ 仓库里还没有 |
| **`.ai/checks/data/` 的 24 条运行时扫库检查** | ❌ 0 实现 |

---

## 6. 下一步

1. **I1 标的页的后端半边** —— 一个聚合端点（标的 + 关注理由历史 + 最新行情）。S2 前端要有东西可渲染，而"我对这家公司知道什么 / 做过什么 / 结果如何"这三块的取数逻辑现在还不存在
2. **把 D3 行情接到关注池** —— 首页"我关注的"要有涨跌，否则 S1 的行情层与 D1 之间没有连接，P0 验收句里的"每天打开能看到动态"就没有着落
3. **清理 `core/config.py` 的 v1 检索配置** —— `/health` 现在汇报的是一个已作废的检索层，这比"少一个配置"更容易误导人
