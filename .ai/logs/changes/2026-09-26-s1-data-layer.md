# 变更记录：S1 数据层（D3 行情）实现 + 6 批共 61 项决定落库

- **日期**：2026-09-26
- **类型**：`feat`（数据层）+ `docs`（治理文件）
- **范围**：
  - **代码**：`backend/src/alphacouncil/models/market.py`（新）· `providers/{__init__,base,sources,router,cache}.py`（新）· `backend/tests/unit/{test_market_data,test_provider_transport}.py`（新）· `backend/scripts/smoke_market.py`（新）· `backend/pyproject.toml`
  - **治理**：`.ai/memory/decisions.md`（+7 条 ADR）· `.ai/data-sources.md` · `.ai/status.md` · 本文件
- **依据**：宪法第九条 —— **"完成" = `make check` 通过**；宪法附则 —— 变更需在 `.ai/logs/changes/` 开记录

---

## 1. 为什么改

### 1.1 直接原因

主人指示：**「总结一下，然后我们开始开发」**。

路线图 v2 的 P0 是 `D1 关注池 · D3 行情 · I1 标的页 · T1 今日 · J1 决策登记`。
**其中 D3 是唯一的纯后端项，也是其余四项的地基** —— 没有行情，"失效条件触发了"这句话根本说不出口（产品亮点 ③ 的实现前提）。

### 1.2 更重要的原因：6 批决定积压

调研阶段产出的 **61 项可落地决定**（T-01~T-20 · S-01~S-11 · `origin`/`priority`/`status` · F-01~F-08 · L-01~L-06 · V-01~V-08）
**全部只存在于调研笔记里，一条都没进 `.ai/`**。

> **一份只写在调研笔记里的决定，等于没有决定。**
> 而且代码一旦先跑起来，**代码会变成事实上的规格** —— 那时再落库就变成"给已有实现补文档"，而不是"按决定写实现"。

所以本次**先落库、再写码**（实际是交替进行）。

---

## 2. 改了什么

### 2.1 新增代码：数据层（约 1,150 行）

| 文件 | 职责 |
|---|---|
| `models/market.py` | **v2 数据契约**。三条宪法规则**编码成类型**：① 数据四态 ② 单位显式（百分比 = 小数制）③ 必带 provenance |
| `providers/base.py` | Provider 协议 + **能力声明**（`datasets` / `markets` / `batch_semantics`）+ 异常四分类 |
| `providers/sources.py` | **腾讯 / 新浪 / 东财**三源。**fetch / parse 分离**（parse 是纯函数，测试不需要网络） |
| `providers/router.py` | **能力路由 + 降级链 + 熔断 + 缓存** |
| `providers/cache.py` | TTL 内存缓存 |

**把"纪律"落成"机制"的三处**：

| 规则 | 落在哪一层 | 实现 |
|---|---|---|
| 数据四态（ADR-0015） | **③ 类型/构造期** | `DataResult._check_state_consistency` —— **`ok` 没值、`error` 没码，构造就抛错** |
| 边界转换只在 providers 层（T-05） | **③ 接口签名** | `get_daily` 收 `date` 对象；东财转 `20260918`、腾讯转 `2026-09-18` |
| 未声明的交易所不发请求（T-07） | **③ 能力声明** | `ProviderCapabilities.markets` 预过滤 → `.BJ` 直接 `no_provider` |

### 2.2 新增治理内容

| 文件 | 变更 |
|---|---|
| `decisions.md` | **+7 条 ADR（0020 ~ 0026）**，归并 61 项决定。**每张决策表带「实现」列** —— 决定与代码连着 |
| `data-sources.md` | 数据边界表**腾讯拆成两行**（实时 / 日线两个子域）· 新增「三之二 2026-09-26 实测」· 降级差异**写具体**（腾讯日线缺成交额）· 实现约束 **8 条 → 15 条** · 修正问财条目 |
| `status.md` | S1 阶段 → **部分完成** · **D3 → 已实现** · ADR 12 → **26 条** · 未验证项 +4 |
| `pyproject.toml` | **移除已排除依赖**（llama-index-core / qdrant-client / akshare / lightrag-hku / pandas）· 描述改为 v2 定位 · **`py-fsrs` → `fsrs`** |

---

## 3. 验证（**本机真实执行，不是"应该能跑"**）

```
ruff check src tests   → All checks passed
mypy (strict)          → Success: no issues found in 22 source files
pytest tests/unit      → 101 passed   （含 v1 遗留的 54 项）
coverage               → 90.10%      （providers/sources.py 55% → 85%）
```

**联网冒烟（`scripts/smoke_market.py`）**：
```
[realtime]  status ok  source tencent  price 1237.0  change -1.1381%
            ohlc 1250.01 / 1256.13 / 1231.05   vol 3,123,900  amt 3,867,310,000
[daily]     status ok  source tencent  5 根日线（东财不可达 → 自动降级）
[venue BJ]  status error  code no_provider   ← 未发请求，诚实降级
```

### 3.1 ⭐ 三个实测发现

1. **腾讯有日线接口** —— `web.ifzq.gtimg.cn/appstock/app/fqkline/get`，`qfqday` 返回 `[日期, 开, 收, 高, 低, 量]`。
   → **推翻"只有东财有日线"的旧结论**，日线单点故障解除。
   → ⚠️ **代价**：**没有成交额** → `Quote.amount` 改为 `float | None`，**绝不填 0、绝不用 `close × volume` 估算**。

2. **东财在本机（沙箱代理下）不可达** —— 连接被中断（`server closed abruptly`），**重试 3 次全失败**；腾讯 / 新浪同时正常。
   → **恰好验证了降级链真的工作**：日线请求自动切到腾讯并成功返回。

3. **能力路由的意外好处** —— 默认顺序 `[东财, 腾讯, 新浪]`（看着反直觉）。因**选择由声明驱动**：东财不声明 `REALTIME` → 快照自动跳过它 → 快照实际「腾讯→新浪」；日线则东财优先（有成交额）。
   → **一份全局顺序，两套有效优先级。**

### 3.2 测试抓出的两个真实缺陷（不是设计时想到的）

| 缺陷 | 现象 | 修复 |
|---|---|---|
| **路由只做了"失败回退缓存"，没做"缓存命中"** | 补上后立刻暴露新问题 | ⭐ **实时快照绝不能命中缓存**（旧价当现价 = 说谎）→ 引入 `allow_cached_answer`：日线可命中（历史不可变），快照不可命中 |
| **腾讯对空响应报 `unavailable`** | `v_sh600519="";` 被判为"协议错误" | 语义应为 `no_data`（"这个标的没数据"）—— **两者的区别会传到用户眼前** |

### 3.3 依赖名错误（从未被验证过）

```
pip install py-fsrs  →  ERROR: No matching distribution found
pip install fsrs     →  ✅ fsrs 6.3.2
```

⚠️ **`py-fsrs` 在 PyPI 上不存在** —— 技术栈里记的包名是错的，且**从未实测**。已修正。

**实测 API**：`Card` / `Rating`（**四档**）/ `Scheduler` / `State`（**只有三态** `Learning`/`Review`/`Relearning`）。
→ ⚠️ **`State` 里没有「已推迟」也没有「已收敛」** → ADR-0021 的 S-01 / S-05 **必须由我们自己的表实现**。
→ ⚠️ **`Rating` 四档（记忆强度）与决策层的两个必填按钮（决策结论）是两个正交的轴**，不可混用。

---

## 4. 未完成 / 风险（不假装做过）

| 项 | 状态 |
|---|---|
| **磁盘缓存层** | ❌ 未实现 —— 当前仅内存，**重启后 `stale` 回退失效**（**T-11 只兑现了一半**） |
| 能力矩阵 `candidates` / `pending`（T-02） | ❌ 仅 `usable` |
| 交易日探针（T-08） | ❌ 未实现 |
| 已知口径不一致清单（T-06） | ❌ 未实现 |
| 依赖许可检查（L-06） | ❌ 未实现（`make check` 也尚未存在） |
| **`.ai/checks/` 脚本** | ❌ 仍未实现（只有约定文档） |
| `.ai/specs/001-data-layer` | ⚠️ **仍是 v1 方向**，需按本次实现重写 |
| **`models/domain.py` 的 `ResearchReport`** | ⚠️ **撞红线 15**（agent 生成报告 = 判断生成）—— **待主人确认后删除** |
| **`domain.Quote` 与 `market.Quote` 重名** | ⚠️ v1 遗留，`conftest.py` 的 fixture 用的是 v1 那个 |
| `core/config.py` 的 `qdrant_*` / `langfuse_*` | ⚠️ 依赖已删，字段成死代码 |
| 腾讯日线条数上限 | ⚠️ 未验证（保守取 320） |
| 北交所 `.BJ` | ⚠️ 未验证（当前所有源都不声明支持） |
| **换到真实用户网络后东财是否可达** | ⚠️ **必须复测**（当前结论来自沙箱代理环境） |

---

## 5. 对后续的影响

1. **S1 剩余项按依赖顺序**：磁盘缓存层 → `(market, code)` 标的表 → 关注池表 → 交易日探针。
2. **D1 关注池可以直接开始** —— 它需要的行情取数能力已经在了。
3. ⚠️ **`.ai/specs/` 重写优先级上升**：现在代码已经跑在 spec 前面，**必须尽快把 S1 的正式规格补上**，否则"代码即规格"。
4. ⚠️ **`make check` 仍未存在** —— 按宪法第九条，**当前所有工作严格来说都还没"完成"**。这是最该补的一项。

---

## 6. 附：把「单一命令入口」从口号变成可执行（同日）

落库过程中发现**三个"从未被执行过"的问题**，它们是**同一种病**。

| # | 问题 | 证据 | 为什么会这样 |
|---|---|---|---|
| 1 | ⚠️ **`make` 根本没装** | `which make` → not found | 宪法第九条写「一切命令走 `make`」「`make check` 才算完成」—— **这条规则从来没有被执行过**，因为不可能执行 |
| 2 | ⚠️ **`pytest tests/unit -m unit` 静默跳过 47 个测试** | `54 passed, 47 deselected` | 测试文件没有 `@pytest.mark.unit` 装饰器。**套件显示绿灯，而新写的 47 个测试一个都没跑** |
| 3 | ⚠️ **`pip install -e .` 一直是失败的** | `ValueError: Readme path must be within the project directory: ../README.md` | `pyproject.toml` 指向 `../README.md`，hatchling 不允许。**Makefile 的 `install` 目标从未成功运行过** |

> **共同点：规则/命令存在于文档里，但从未真正跑过一次。**
> 这正是宪法 §0.2 要解决的问题 —— **第 ① 层的规则（文档）不会自己生效。**

### 6.1 修复

**新建 `backend/scripts/dev.py`** —— 单一命令入口，**取代 make 成为真实现**（Makefile 变成薄包装）：

| 命令 | 作用 |
|---|---|
| `check` | CI 全部门禁；**有门禁未实现 → 退出码 1** |
| `check-lite` | 只跑今天存在的门禁（日常用） |
| `lint` / `typecheck` / `licenses` / `test` / `test-cov` / `clean` | 单项 |

**T-19 落地**（`check` 输出）：
```
  [PASS] lint           ruff check
  [PASS] typecheck      mypy (strict)
  [PASS] licenses       dependency licence scan (ADR-0024 · L-06)
  [SKIP] check-static   banned-pattern scan (.ai/checks/static/)   <- 12 scripts specified, 0 written
  [PASS] test           pytest tests/unit

  ran 5 · passed 4 · failed 0 · skipped 1

✗ INCOMPLETE — check-static did not run (not implemented).
  A skipped gate is not a passing gate.
```
**实测退出码 = 1** —— 绿灯不再可能被误认为完成。

**新建 `backend/scripts/check_licenses.py`** —— **L-06 落地**（ADR-0024）：
- 扫描**已安装**的 distribution 的许可元数据
- **AGPL / GPL → fail** · LGPL / MPL / 许可未知 → warn · MIT / Apache / BSD / ISC / PSF → ok
- 实测：**scanned 46 distributions · ok=42 · warn=4 · fail=0**
  - warn：`aiosqlite` / `colorama` / `pathspec`（**无许可元数据**）· `certifi`（MPL-2.0）
  - ⚠️ 诚实局限：**只扫已安装的**，声明但未安装的依赖扫不到（已写在脚本 docstring）

**修 `tests/conftest.py`** —— **目录即标记**：`pytest_collection_modifyitems` 按路径自动打 `unit` / `integration` / `live` marker。
→ **修的不是那 47 个文件，是这一类 bug** —— 以后往 `tests/unit/` 加文件，**不可能再漏**。
→ 效果：`-m unit` 从 **54 passed** 变成 **101 passed**。

**修 `pyproject.toml`** —— `readme` / `license` 移进 `backend/`（新增 `backend/README.md`）→ **`pip install -e .` 首次成功**。

**修 `Makefile`** —— 全部目标改为调用 `dev.py`；新增 `licenses` 目标；**删除 `dev` / `down`**（它们启动 docker-compose，属于 v1 的"服务器 + Qdrant"架构，与 ADR-0006 / 0007 冲突）。

### 6.2 教训

> **判断一条规则是否真实存在，不要看它写在哪里，要看它上一次失败是什么时候。**
> 一个从未失败过的检查，很可能从未运行过。

---

*本记录 Append-Only，不得修改历史条目。*
