# Spec 006 · 磁盘缓存层（SqliteCache + 真实 0002 迁移）

- **状态**：Active
- **目标阶段**：S1（status.md D3 还差项「磁盘缓存层」· §五「T-11 只兑现了一半」）
- **依赖**：迁移框架（已完成）· D3 行情路由（已完成）· spec 004/005（行情的下游页面）
- **ADR 依据**：ADR-0012（迁移纪律）· ADR-0016（CHECK 外置台账）· 宪法 4.5（本地缓存优先）/ 5.1（迁移可逆）

---

## 宪法 2.2 三问（新增机制的门槛）

| 问 | 答 |
|---|---|
| ① 它防止的**具体故障** | 应用重启（或崩溃）清空进程内存 → 重启后一旦全源失败（断网、限流、封禁），**无 stale 可退**，行情页面空 —— 而"昨天的收盘价"本该是可用的真相 |
| ② 既有机制为何处理不了 | `MemoryCache` 的存活域是进程内存，**定义上不可跨重启**；TTL 用的 `monotonic` 时钟在重启后也不连续。cache.py 的文档早已标注此限制"真实存在且在此声明" |
| ③ 必需行为还是可选弹性 | **必需** —— 约束②（自用）验收标准「拔网线后仍能启动并显示缓存数据」的直接前提；TSP 借鉴 T-11「取数失败保留上轮有效缓存」只兑现了一半 |

## 功能需求

| 编号 | 需求 |
|---|---|
| FR-1 | 迁移 **0002_market_cache**：`market_cache` 表（STRICT）—— `cache_key` 主键 · `dataset`（enum CHECK）· `payload`（DataResult JSON）· `expires_at`。约束登记进 `constraints.json`（双向校验）。down = DROP TABLE，**非破坏性**（缓存可再生），`destructive_down: false` |
| FR-2 | `SqliteCache(database_path, ttl_seconds, clock)` 实现 `Cache` 协议：**每次操作开一条连接**（复用 `storage.db.connect`，用完即关——与每请求连接同一纪律）；put 走事务 `INSERT OR REPLACE`；get 校验 TTL 后**按 dataset 类型化反序列化** |
| FR-3 | `Cache` 协议显式携带 dataset：`get(key, dataset)` / `put(key, value, dataset=...)`，router 透传。—— 理由：让磁盘行可以严格类型化重建（`DataResult[RealtimeQuote]` / `DataResult[list[Quote]]`），**不做 key 字符串前缀解析**（那是把两个模块用约定焊起来） |
| FR-4 | get 遇**损坏行**（JSON 非法 / 模型校验失败）：警告日志 + 删除该行 + 返回 `None`，**绝不抛** —— 缓存的职责是降级，缓存自己坏掉不能把"降级"升级成"故障" |
| FR-5 | 生产装配：`app.py` 用 `default_router(cache=SqliteCache(resolved.database_path))`；`MemoryCache` 保留为路由单元测试的轻量替身（有真实使用，不删） |
| FR-6 | TTL 语义与 MemoryCache 一致（默认 900s），但时钟必须是**墙钟**（`time.time`）—— monotonic 的纪元不跨进程 |

## 验收标准

| 编号 | 标准 |
|---|---|
| AC-1 | 真实 **1→2 升级链**：v1 库带用户数据 → 升级 → 数据完好、`market_cache` 就位、快照在升级前拍下（status.md §五"真实的 1→2 迁移还不存在"就此消除）；全新安装直达 v2 |
| AC-2 | put→get 往返对两类载荷都类型化还原：realtime 单条、daily 列表 |
| AC-3 | TTL 过期（注入时钟推进）→ `None` |
| AC-4 | 人为写坏的行 → `None` + 行被删 + 警告日志（不抛） |
| AC-5 | ⭐ **重启存活性**（本 spec 的核心）：router A 成功取数写入 → 构造全源失败 → 拿到 stale；**新建 router B 指向同一库文件（模拟重启）** → stale 仍然可用且带 `stale=True` |
| AC-6 | 约束台账双向校验通过（新增 CHECK 全部登记、无未登记约束） |
| AC-7 | 门禁全绿（后端 ruff/mypy/pytest + 前端四道 + 静态检查 + `dev.py check`） |
| AC-8 | 变异检查 ≥ 3 条 |

## 已知的失败（本 spec 防的事故）

| # | 事故 | 防线 |
|---|---|---|
| 1 | monotonic 时钟写进磁盘：重启后纪元重置，TTL 永远"未过期"，三天前的价被当昨天的报 | FR-6 墙钟 + AC-3 注入时钟测试 |
| 2 | 缓存行损坏 → get 抛异常 → 全源失败时连"降级"都失败 | FR-4 自愈 + AC-4 |
| 3 | payload 里的 source/fetched_at 再存一份列 → 两份真相 | FR-1 只存 payload + expires_at + dataset |
| 4 | 用 key 前缀猜数据集 → 路由改 key 格式即静默坏 | FR-3 dataset 显式入协议 |
| 5 | 升级链仍是"合成"的：框架从未在带数据的真库上跑过 1→2 | AC-1 真实迁移测试 |
| 6 | 缓存写失败（库锁等）让取数本身失败 | put 的异常不向上抛（warn 日志）—— 缓存永远不比没缓存更糟 |

## 边界（本 spec 不做）

- **不做双层缓存**（内存 L1 + 磁盘 L2）：当前缓存只服务 stale 回退与不可变日线，频次极低，双层是投机抽象（宪法 2.1 #2）。
- **不做过期行 GC**：量级（十只票 × 两个数据集）不需要；同 key 写入即覆盖。
- **不做离线端到端实测**：本层是它的前提，实测另行验证（拔网线启动 / 缓存回退）。
- 交易日探针（T-08）、能力矩阵（T-02）：各自独立 spec。
