# Plan · Spec 006 磁盘缓存

> ⚠️ 按项目纪律，本文件对审查者隐藏。

## 技术方案

### 迁移 0002（`storage/migrations/`）

```sql
-- 0002_market_cache.up.sql
CREATE TABLE market_cache (
    cache_key  TEXT NOT NULL PRIMARY KEY,
    dataset    TEXT NOT NULL,
    payload    TEXT NOT NULL,
    expires_at REAL NOT NULL,
    CONSTRAINT market_cache_dataset_check
        CHECK (dataset IN ('realtime', 'daily')),
    CONSTRAINT market_cache_key_required_check
        CHECK (length(trim(cache_key)) > 0),
    CONSTRAINT market_cache_payload_required_check
        CHECK (length(trim(payload)) > 0),
    CONSTRAINT market_cache_payload_json_check
        CHECK (json_valid(payload))
) STRICT;
-- down: DROP TABLE IF EXISTS market_cache;   destructive_down: false
```

- `expires_at REAL` = Unix 墙钟秒（`time.time()` 域）；TTL 判定在读取侧。
- CHECK 三条全部登记 `constraints.json`：dataset→enum；key/payload required→required；payload→json。
- 首个"约束台账 + STRICT + json_valid"一起上真库的迁移，正好给 AC-1 的真实升级链当考题。

### SqliteCache（`providers/cache.py` 内新增类）

```python
class SqliteCache:
    def __init__(self, database_path: Path | str, ttl_seconds: float = 900.0, *, clock: Callable[[], float] = time.time) -> None
    def get(self, key: str, dataset: Dataset) -> DataResult[Any] | None
    def put(self, key: str, value: DataResult[Any], *, dataset: Dataset) -> None
```

- **per-op 连接**：`connect(self._path)` → 操作 → `close()`。与每请求连接同一纪律（不共享、顺序使用、serialized 模式）。
- put：`with transaction(...)` + `INSERT OR REPLACE`。**put 异常不向上抛**（warn 日志）—— 已知失败 #6。
- get：`expires_at` 过期 → None；`model_validate_json` 失败 → warn + DELETE 行 + None。
- 类型化重建：`_VALIDATORS = {Dataset.REALTIME: DataResult[RealtimeQuote], Dataset.DAILY: DataResult[list[Quote]]}`。
- 时钟注入与 MemoryCache 同型，但默认 `time.time`。

### 协议扩展（FR-3）

`Cache` 协议加 `dataset`；`router._route` 把已有的 dataset 传给 `self._cache.get/put`；`MemoryCache` 签名同步（dataset 忽略）。5 个现有路由测试不受影响（MemoryCache 行为不变）。

### 装配（FR-5）

`app.py`：`app.state.market_data = default_router(cache=SqliteCache(resolved.database_path))`。
`providers/__init__.py` 导出 `SqliteCache`。`default_router` 默认值保持 MemoryCache（测试路径）。

## 测试

- `tests/unit/test_disk_cache.py`（新）：往返两载荷 / TTL 过期 / 损坏自愈 / put 失败不抛（损坏的库路径）
- `tests/unit/test_market_data.py`（增）：**重启存活性**（AC-5）——同库路径的两个 router 实例
- `tests/integration/test_migrations.py`（增）：真实 1→2 升级带数据 + 快照时序
- `tests/unit/test_storage.py`：约束台账自动覆盖新表（现有双向测试）

## 风险

| 风险 | 对策 |
|---|---|
| 真实用户的库将被 1→2 迁移（首例） | 框架已有快照+SHA-256+回滚授权；冒烟时在真实库上演练并核对快照存在 |
| WAL 模式下缓存表与用户表同库 | WAL 是既有库配置；缓存写频次极低 |
| Dataset 枚举日后扩充（分钟线等） | `_VALIDATORS` 缺 key → 显式 KeyError（fail fast），不加兜底 |
