# 变更记录 · 2026-09-26 · 存储层与领域层（D1 关注池的骨架）

- 日期：2026-09-26
- 类型：架构变更（新增两个分层 + 仓库第一条数据库迁移）
- 范围：
  - 新增 `backend/src/alphacouncil/storage/`（`__init__.py` · `db.py` · `migrate.py` · `migrations/0001_initial.{up,down}.sql` · `migrations/manifest.json` · `constraints.json`）
  - 新增 `backend/src/alphacouncil/domain/`（`__init__.py` · `instrument.py` · `watchlist.py`）
  - 新增 `backend/tests/unit/test_instrument.py` · `test_watchlist.py`
  - 修改 `core/error_codes.py` · `checks/rules/check_error_codes.py` · `src/alphacouncil/__init__.py` · `.ai/error-codes.md` · `.ai/status.md`
- 依据：宪法 5.1 / 5.2 / 5.4 / 5.5 · 7.5 · 8.1 · 8.3 · ADR-0011 / 0012 / 0016 / 0017 · `.ai/status.md` S1 与 D1

---

## 1. 为什么改

三件事同时到期，而且互相扣着：

1. **没有数据库，S-04 是一条空规则。** 上一轮修掉了 S-04 的静默通过漏洞（schema 存在但无 append-only 表时它报 "clean" 而其实什么都没查）——修好之后它仍然只能 skip，因为**没有任何 schema 文件可扫**。一条规则要能失败，先要有能被它扫的东西。
2. **"能把自己关注的 10 只票加进去（带理由）"是 P0 的验收句**，而它需要一张表。此前 D1 只有一行 `❌ 未开始`。
3. **ADR-0017 定了主键是 `(market, code)`，但没有任何东西强制它。** 只写在 ADR 里的规则，下一轮就有人绕过（宪法 0.2 的判据：能移到数据库的规则必须移）。

---

## 2. 改了什么

### 2.1 `storage/` —— SQLite 连接与迁移（624 行 Python + 252 行 SQL）

| 文件 | 关键决定 |
|---|---|
| `db.py` | **两个 PRAGMA 剖面**：应用 `synchronous=NORMAL`、迁移 `FULL` + `temp_store=FILE`。`temp_store=FILE` 不是优化是**内存上限**（wealthfolio 实测：MEMORY 下百万行 UPDATE 峰值 2,046 MiB，FILE 仅 76 MiB）。`foreign_keys` 默认关闭且是连接级 → 每个连接显式打开 |
| `migrate.py` | **版本从 `manifest.json` 读，不从文件名排序**（`00010` 会排在 `0009` 前面）· **DDL 与 `PRAGMA user_version` 同一事务**（实测：回滚后版本号与 schema 一起还原）· 迁移前 `VACUUM INTO` 快照 + SHA-256 · **三向版本比较，库新于程序即拒绝**，不降级 · `sqlite3.complete_statement` 切分 SQL（触发器体含分号；不用 `executescript`，它会隐式 COMMIT） |

### 2.2 `migrations/0001_initial` —— 4 表 / 1 视图 / 6 触发器 / 3 索引，全部 `STRICT`

- `instruments`：**主键 `(market, code)`**（ADR-0017）· `code` 用 `GLOB '[0-9]×6'` 而非手写 `\d` 模式
- `watchlist_events`：**append-only 事件日志**，不是带 `reason` 列的可改表 —— 只有事件日志能让"你这句说过 3 次"可查询（产品亮点 ②），也才能挡住第 ④ 档权限的 agent 改写用户原话
- `decisions`：**主键 = 服务端毫秒时间戳**（ADR-0011），API schema 不暴露该字段
- `audit_log`：`detail <= 500` —— **长度上限保证正文塞不进来**
- 6 个触发器，RAISE 消息带中文（用户可见）：`watchlist_events is append-only: 改变想法请追加新记录`
- `watchlist_current` 视图：按 `id DESC LIMIT 1` 取最新事件，排除 `removed`

### 2.3 `domain/` —— 业务规则（455 行，覆盖率 100%）

`instrument.py` 实现 ADR-0017 的硬规则，其中**两条与 ADR 的字面表述存在张力，本轮给出了裁决并写进了模块 docstring**：

> ADR-0017 规则 2 说"推断不能用于补全"，规则 3 说"`000xxx` 必须让用户选市场"。两者的边界是：**能唯一确定时是查表，不是猜**；有多个候选时才交给用户。
> 裁决依据不是我的解释，而是 `.ai/error-codes.md` §2.1 已经写下的用户文案 —— 它把 `600519` 列为**合法输入形式**，只给 `000001` 配了"请选择市场：沪市 / 深市"。

`watchlist.py` 的关注理由规则，**三条里两条用签名强制、只有一条用检查**：
- 只有 `reason_revised` 能带 `supersedes_id` → `added` / `removed` **不接受该参数**，写错是 `TypeError`
- `reason_revised` 的 `supersedes_id` **无默认值** → 漏传是 `TypeError`
- 理由非空白 + 长度上限 → 唯一需要运行期检查的一条，因为**只有它的消息是给用户看的**

### 2.4 错误码：新增 `WATCHLIST_*` 子命名空间

`WATCHLIST_REASON_REQUIRED` · `WATCHLIST_REASON_TOO_LONG`。与 `DECISION_*` 分开的理由：一个守的是"已经发生的交易"，另一个守的是"还没有交易、只是先关注"；合并会让"用户多久不写理由"无法统计。

三处同步：`ErrorCode` 枚举 · `.ai/error-codes.md` §2.8 · `checks/rules/check_error_codes.py` 的 `CODE_PATTERN`（新增 `WATCHLIST` 前缀）。

**副作用（正向）**：`DATA_SOURCE_TICKER_AMBIGUOUS` 与 `DATA_SOURCE_TICKER_INVALID` 此前是"声明了但没人用"的 info 级发现，本轮起真的被触发。

---

## 3. 实测证据（可复现）

| 项 | 命令 | 结果 |
|---|---|---|
| 迁移端到端 | 临时目录建库后 `migrate.apply` | `applied (1,)` · `snapshot None`（version=0 无数据可拍）· 4 表 + 1 视图 + 6 触发器 · 重跑 `applied () up_to_date changed False` |
| 静态检查（全量） | `python -m checks` | `ran 12 · skipped 3 · crashed 0 · findings 14 (0 error, 0 warning, 14 info)` —— **S-04 从 skip 变为 PASS**，skip 由 4 降到 3（剩下 3 条是前端红线 S-07/08/09） |
| 质量门禁 | `scripts/dev.py check-lite` / `check` | `check-lite` 4/4 通过；`check` `ran 5 · passed 4 · failed 1`，失败的是 `check-static`（**T-19：skip 不算通过**，符合预期） |
| 单测 | `pytest -q` | **274 passed**（本轮 +70：ticker 47 · 关注池 23） |
| `domain/` 覆盖率 | `pytest --cov=alphacouncil.domain` | **100%**（116 语句 / 32 分支，全 0 未覆盖）—— 宪法 8.1 要求 ≥90% |
| 静态检查 | `ruff check .` · `mypy` | `All checks passed!` · `Success: no issues found in 54 source files` |
| ⭐ **变异检查** | 逐条改坏规则后跑对应用例 | **14 / 14 全部变红** |

### 3.1 变异检查抓到的两个"测试没守住规则"

这是本轮最有价值的产出，值得单独记：

| 变异 | 表面结果 | 真实原因 |
|---|---|---|
| `[0-9]{6}` → `\d{6}` | 测试**仍然绿** | 全角码 `６００５１９` 被"未知代码段"守卫顺手拦了 —— **ASCII 数字规则本身从未被测试**。补了一条"带显式市场"的用例，把那个守卫让开，规则才真正被钉住 |
| 删掉"前后缀二选一"守卫 | 测试**仍然绿** | 形状检查会兜住 `sh000001.SZ` —— **该守卫的全部贡献是诊断信息**。补了一条断言消息内容的用例，并写明"这里钉措辞就是钉功能" |

> **一个从未失败过的检查，很可能从未运行过。** 这两条测试在变异前都"通过"了。

### 3.2 两个 Unicode 陷阱（实测确认，都已在代码里修掉）

| 陷阱 | 实测 | 后果（若不修） |
|---|---|---|
| Python 的 `\d` 匹配任意 Unicode 十进制数字 | `re.fullmatch(r"\d{6}", "６００５１９")` → `True` | 全角代码进入 `Symbol`（**pydantic 的 `^\d{6}$` 同样宽松**），再进入数据库 —— 一个数据源永远认不出的代码，长得完全正常 |
| `re.IGNORECASE` 单独使用时 U+017F（长 s）可替代 `s` | `re.match(r"^(sh\|sz\|bj)", "ſh600519", re.I)` → `True` | 前缀匹配成功，随后 `Market("ſh")` 抛**没有错误码的裸 `ValueError`** —— 调用方无法分支，S-05 也看不到 |

修复：`[0-9]{6}` + `re.ASCII`。纵深防御：数据库侧 `GLOB '[0-9]×6'`（SQLite 的 GLOB 是纯 ASCII）。

### 3.3 段表的第一次真实失效

`parse_ticker("204001")` 曾被解析为**深市** —— 因为段表里 `20` 盖住了深市 B 股 `200xxx`，而 `204001` 其实是**沪市国债逆回购**。
这是"前缀过宽"的典型失效模式：不会报错，只会安静地指向另一个市场。已收紧为 `200`，并补了回归测试。

---

## 4. 有意保留 / 未改的

- **`core/config.py` 的 v1 检索配置**（`qdrant_*` / `langfuse_*` / `embedding_*` / `reranker_*` / `recall_top_k` / `rerank_top_k` / `enable_graph_retrieval` / `enable_text2sql`）**未清理** —— 它们违背 ADR-0006（检索层已整体作废），且 `/health` 还在汇报。留待专门一轮（会动 `test_config.py` 的 4 个用例）。
- **`models/domain.py` 的 `ResearchReport` / `ResearchRequest` 未删** —— 撞红线 15，但需要主人确认。
- **`database_url` 已删**（实测全仓只有声明处一处引用，是死配置，且违反宪法 5.3），改为 `database_path` + 平台默认路径。
- **段表只修了发现的那一处**，没有逐段核对（见下）。

---

## 5. ⚠️ 未做（不假装做过）

| 项 | 状态 |
|---|---|
| **关注池的仓储层与薄 API** | ❌ 未开始（下一轮）。表、约束、领域规则都在，**但还没有任何代码能写入它** |
| **升级路径的集成测试** | ❌ 未写。目前只冒烟过"全新安装"与"幂等"两条路径，**没有测过 `0 → 1` 之外的迁移链** |
| **`constraints.json` 的完整双向交叉校验** | ⚠️ 只做了 `watchlist_events` 的 4 条（枚举 / 长度 / supersedes / 理由必填）与领域常量的对照，**`instruments` / `decisions` / `audit_log` 的约束尚未交叉校验** |
| ⭐ **段表未与真实数据源核对** | ⚠️ 段表是**手写**的交易所编号规则，它决定"裸码能否唯一确定市场"。**换到真实网络后必须用行情源逐段抽样核对** —— 已记入 `.ai/status.md` §五 |
| **前端交互** | ❌ 未开始。`000xxx` 让用户选市场的界面、标的页入口都在 S2 |
| **`000xxx` 歧义段的真实覆盖** | ⚠️ 只验证了 `000001`。其他 `000xxx`（指数 / 股票）的分布**未逐条核对** |

---

## 6. 下一步

1. **#23 仓储层与薄 API** —— `storage/repositories/{instrument,watchlist}.py` + `api/routes/*`，把领域规则接到真实的 HTTP 边界
2. **#24 测试与文档同步** —— 迁移升级路径集成测试 · `constraints.json` 完整双向校验 · 触发器真拦的行为测试
3. 之后才是 **I1 标的页**（S2 的第一项），因为到那时它才有数据可显示
