# 变更记录 · 2026-09-27 · 磁盘缓存层（spec 006）

- 日期：2026-09-27
- 类型：架构变更（S1 收尾头号项）—— 缓存的存活域从进程扩展到重启
- 范围：
  - 新增 `backend/src/alphacouncil/storage/migrations/0002_market_cache.{up,down}.sql` · 修改 `manifest.json`（+v2，destructive_down: false）· `constraints.json`（+4 条约束登记）
  - 重写 `backend/src/alphacouncil/providers/cache.py`（协议加 dataset + `SqliteCache`；`MemoryCache` 保留为测试替身）
  - 修改 `providers/router.py`（dataset 透传）· `providers/__init__.py` · `api/app.py`（生产装配 SqliteCache）
  - 修改 `models/market.py`（⭐ RealtimeQuote 序列化往返缺陷修复）
  - 新增 `tests/unit/test_disk_cache.py`（9 项）· 修改 `tests/unit/test_storage.py`（schema 读取器应用全链 + 守底数 24→28）· `tests/integration/test_migrations.py`（+3 项真实升级链测试）
  - 新增 `.ai/specs/006-disk-cache/` · 修改 `.ai/status.md`
- 依据：宪法 2.2（新增机制三问）/ 2.1 / 4.5 / 5.1 / 8.3 · ADR-0012 / 0016 · TSP T-10 / T-11

---

## ① 想做什么

status.md S1 还差项的头一条：**磁盘缓存层**。当前缓存只在进程内存里，重启即失——"全源失败时回退上一个有效值（标 stale）"在重启后无米下锅，约束②的验收标准「拔网线后仍能启动并显示缓存数据」没有前提。宪法 2.2 三问的完整回答见 spec 006（故障：重启清空进程内存；既有机制定义上不可跨重启；定性：必需）。

顺带兑现一个更老的欠账：**真实的 0002 迁移从此存在** —— 此前"升级链"只在合成意义上被验证过（status.md §五 原话）。

## ② 做了什么

- **迁移 0002**：`market_cache`（STRICT + 4 条 CHECK 全部登记台账；down 非破坏——缓存可再生）。
- **`SqliteCache`**：与用户数据同一 SQLite 文件（复用既有的开库/迁移/备份设施，不为可丢弃数据引入第二套存储）；**per-op 连接**（与每请求连接同一纪律）；墙钟 TTL（monotonic 纪元不跨进程——已知失败 #1）；损坏行自愈（warn + 删除 + 当作不存在）；**put 失败不上抛**（缓存写入不能把已成功的取数变成错误页）；**get 连接失败同样降级为 None**（缓存永不比没缓存更糟）。
- **协议显式携带 dataset**：磁盘行按 `DataResult[RealtimeQuote]` / `DataResult[list[Quote]]` 严格类型化重建——不解析 key 字符串前缀（那是用约定把两个模块焊起来）。
- **生产装配**：`app.py` 传 `SqliteCache(resolved.database_path)`；`MemoryCache` 保留（路由测试的轻量替身，有真实使用，不删）。

### 3.1 ⭐ 测试抓出一个真实模型缺陷：RealtimeQuote 序列化往返断裂

`change_pct` 是 `computed_field`（#30 的决定：序列化给客户端，客户端不做除法）——但 **dump 出的 JSON 在严格重校验时被当 extra 拒绝**（`extra="forbid"`）。也就是说任何 dump→validate 往返都断：磁盘缓存是第一个受害者（写入的行永远读不回来、自愈机制当场把它删掉），将来任何回放/回显场景都会踩。修复：`mode="before"` 校验器丢弃输入里的 `change_pct`，重建时以 price/prev_close **重算**（派生值只有一个权威来源，宪法 4.2）。测试守底。

## ③ 得到了什么样的结果

| 项 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `pytest -q` | **447 passed**（434 + 9 缓存 + 3 真实迁移 + 1 形状参数化新用例——`market_cache` 入台账后自动成为形状测试的一个参数） |
| 后端静态 | ruff check / format --check / mypy | 全过（75 source files） |
| 静态检查 | `python -m checks --strict` | 12/12，0 error |
| 质量门禁 | `scripts/dev.py check` | **`ran 9 · passed 9 · failed 0`** |
| ⭐ 真实库迁移 | 启动应用（%LOCALAPPDATA% 真库） | **v1→v2 成功**：快照 `alphacouncil.v1.20260927T0458*.db` 在升级前拍下、含 v1 全部表、不含 market_cache；用户数据（2 标的 / 2 决策）原样 |
| ⭐ 真实库缓存 | 取价 → 查表 → **重启进程** → 查表 | 腾讯源两条 realtime 行写入；**重启后仍在** —— 重启存活性在真实库上实证 |

### 3.2 变异检查（4 条，全部变红）

| # | 改坏哪里 | 变红的用例 |
|---|---|---|
| M1 | TTL 判定 `>=` → `>`（过期瞬间仍可用） | `test_an_expired_row_reads_as_absent` |
| M2 | 拆掉损坏行自愈（上抛代替 warn+删除+None） | `test_a_semantically_damaged_row_is_deleted_and_reports_absent` |
| M3 | put 空操作（永远不写盘） | `test_a_fresh_router_over_the_same_database_still_serves_the_stale_value`（+4） |
| M4 | 撤掉 RealtimeQuote 往返校验器 | realtime 往返 / 损坏自愈 / 重启存活性（3 failed） |

## ④ 留下了什么

- **新增能力**：重启存活的行情缓存（生产装配）；项目第一个真实的版本 2 迁移
- **status.md**：D3 还差项与 §五 两行（磁盘缓存 / 合成升级链）已消除
- **约束台账**：+4 条（market_cache），双向校验全绿
- **已知限制（不假装做过）**：拔网线端到端实测仍未做（本层是它的前提，实测量化"断网启动显示缓存数据 + 新鲜度提示"另行验证）；无过期行 GC（量级不需要，写入即覆盖）；S1 还剩交易日探针（T-08）与能力矩阵（T-02）
- **下一步候选**：交易日探针 + 能力矩阵（S1 收尾剩余两件）· Playwright 入仓 · `core/config.py` v1 检索配置清理
