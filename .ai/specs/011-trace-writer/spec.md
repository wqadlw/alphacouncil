# Spec 011 · trace 写入器（可观测地基，简历验收①第一块）

- **状态**：Active
- **目标阶段**：S0（status.md §三 `.ai/traces/`「❌ 未实现」· 简历验收①「traces ≥ 50 可回放」的地基）
- **依赖**：无新依赖（标准库 + structlog 已有）
- **依据**：`.ai/traces/README.md`（已定约定：Trace → Observation → Score，JSONL 只追加）· 宪法 8.2（token 与成本）/ 6.3（审计脱敏）/ 9（append-only）· 红线 15（可追溯）

---

## 宪法 2.2 三问（新增机制的门槛）

| 问 | 答 |
|---|---|
| ① 防止的**具体故障** | regression 0003 那类**间歇性故障无法归因**：`/quote` 半数 500 当时只有一行 traceback，没有"这次请求里路由器问了哪些源、各自什么四态结果、各花多久"。没有 trace，排错靠猜；评测（简历验收①）无从谈起 |
| ② 既有机制为何处理不了 | structlog 日志是**平的**：没有"同一次请求"的聚合，没有层级（哪次 provider 调用属于哪次请求），没有统一的时长/状态字段，不可回放 |
| ③ 必需还是可选 | 必需 —— 约束①验收标准（traces ≥ 50 可回放 + eval + 成本记录）的第一块；`.ai/traces/README.md` 已把格式与硬性要求定死，只欠实现 |

## 功能需求

| 编号 | 需求 |
|---|---|
| FR-1 | `core/trace.py`：`TraceWriter`（目标目录）+ `Trace` 句柄。落盘布局按 README 约定：`<dir>/YYYY-MM-DD/<run_id>.jsonl`，首行 trace 记录，其后每行一条 observation；`<dir>/scores/YYYY-MM-DD.jsonl` 存 Score。**JSONL 只追加**——同一 trace 的每次写都是 append，绝不重写 |
| FR-2 | Trace 记录：`{kind:"trace", id, name, started_at}`；Observation：`{kind:"observation", trace_id, id, name, started_at, ended_at, duration_ms, status: ok/error, error_code?, meta?}`；Score：`{kind:"score", trace_id, name, value, scored_at}`。**token/cost 字段预留在 schema**（`token_count` / `cost_usd` 可空）——agent 层落地即填，现在如实为空 |
| FR-3 | **审计脱敏**（6.3）：writer 与所有调用点**禁止写入请求/响应原文**；只写 路由、方法、状态码、时长、四态结果、错误码、源名、payload 的 SHA-256 前 12 位与字节数 |
| FR-4 | **写失败不影响请求**：磁盘任何故障 → warn 日志、请求照常（与 SqliteCache 同一纪律） |
| FR-5 | 请求级集成：FastAPI 中间件——每个 HTTP 请求开一条 trace（name = `METHOD 路由模板`），响应后闭合（status = HTTP 状态码类）；请求体/响应体**不入 trace**（FR-3） |
| FR-6 | 路由器集成：`MarketDataRouter` 接受可选 `tracer`；每次 provider 取数成为当前 trace 的一条 observation（源名 + 数据集 + 四态 + 时长）。**contextvars** 传递当前 trace——provider 调用发生在请求 context 之外时静默跳过 |
| FR-7 | `Settings.traces_dir`（默认 `%LOCALAPPDATA%\AlphaCouncil\traces`，与库文件同级）；运行数据不入库，`.ai/traces/` 只存开发期**主动归档**的证据 |

## 验收标准

| 编号 | 标准 |
|---|---|
| AC-1 | 一条 trace 的落盘文件：首行 trace + N 行 observation，每行合法 JSON、字段齐全、duration_ms > 0 |
| AC-2 | 同目录两次运行 → 两个文件、各自行追加；不重写既有文件 |
| AC-3 | TestClient 打 `/health` → 产生 trace 文件且记录 HTTP 状态与时长；打 POST 决策（含中文理由）→ **trace 文件中不出现理由原文**（脱敏），只出现 payload 哈希 |
| AC-4 | 路由器在 trace 内取数 → observation 记录源名与四态；无 trace 上下文（如启动期）→ 静默无 observation、取数照常 |
| AC-5 | 门禁全绿 |
| AC-6 | 变异 ≥ 3（重写代替追加 / duration 恒 0 / 中间件泄漏请求原文 → 各自红） |

## 已知的失败（本 spec 防的事故）

| # | 事故 | 防线 |
|---|---|---|
| 1 | 间歇性故障（如 0003）无法归因：不知道那次请求内部发生了什么 | FR-5/FR-6：请求与内部步骤聚合为一条可回放轨迹 |
| 2 | 用户内容（决策理由、标的理由）被写进 trace 文件 → 泄密面扩大 | FR-3 脱敏 + AC-3 反向断言 |
| 3 | trace 写失败把请求变成 500（观测者杀死被观测者） | FR-4 全部吞掉 + warn |
| 4 | 追加语义被重写破坏（工具打开文件 mode=w） | FR-1 append + AC-2 |
| 5 | eval 出现时没有 score 通道 | FR-2 的 scores 文件布局先行落定 |

## 边界（本 spec 不做）

- `make eval` / 评测集 / pass rate：需要先有评测对象（agent 抽取层），另立 spec。
- 成本汇总脚本：token/cost 字段现在恒空，无东西可汇总；agent 层落地后一并做。
- 不做异步落盘/批量缓冲：个人级频次，同步 append 足够（多一层的复杂度无收益）。
- `.ai/traces/`（仓库内）不做自动写入：运行数据在 LOCALAPPDATA，仓库内只放**主动归档**的开发期证据。
