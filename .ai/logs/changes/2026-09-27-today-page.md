# 变更记录 · 2026-09-27 · T1 今日页最小切片（spec 005）

- 日期：2026-09-27
- 类型：功能（S3 —— **P0 五块的最后一块**；同日第二单，接在 spec 004 关注池行情之后）
- 范围：
  - 修改 `backend/src/alphacouncil/domain/decision.py`（`KillCriterion.due`）· `storage/repositories/decisions.py`（`list_all`）· `api/app.py`（注册路由）
  - 新增 `backend/src/alphacouncil/api/routes/today.py` · `backend/tests/unit/test_today_api.py`（8 项）
  - 修改 `frontend/src/routing.ts`（+test 同步改写）· `format.ts`（`todayLabel`）· `App.tsx` · `PoolPage.tsx` · `api.ts`
  - 新增 `frontend/src/TodayPage.tsx` · `QuoteCell.tsx`（自 PoolPage 提出，纯移动）
  - 新增 `.ai/specs/005-today-page/` · 修改 `.ai/status.md` · `frontend/README.md`
- 依据：宪法 2.1 / 2.3 / 4.6 / 7.5 / 10.3 · `AlphaCouncil-产品定义-v3.md` §六（首屏四块）· status.md S3 行

---

## ① 想做什么

P0 = D1 · D3 · I1 · T1 · J1，前四块已齐，**只剩 T1**。P0 验收句「每天打开能看到动态」的落点就是首屏。产品定义 §六规定：打开程序默认落在今日，四块 —— ①需要你处理的 ②我关注的 ③今天的数据变化 ④你在重复自己。

诚实的前提取件：四块里当前只有 ② 完全可做（D1+D3 已通），① 可诚实做一部分（失效条件到期），③④ 依赖未建的 D4/D5/J4。本切片的原则沿用标的页先例：**能做的做真，做不了的明说"还没有"，绝不渲染成空的假区块。**

## ② 做了什么

**领域规则先行**（宪法 0.2 层次③）：`KillCriterion.due(as_of: date)` —— 今天 ≥ as_of 即到期，日期注入、纯函数。docstring 里写死了最容易漂移的语义边界：**due = "问题可以问了"，不是"触发了"** —— 指标值不在本系统（D4 未建），触发与否未验证。

**后端**：
- `GET /api/v1/today` → `{generated_at, attention}`。路由只做编排（list_all → 展平 → 领域规则过滤 → 组装），规则本身在领域层。
- `attention` 的每条带 `kind="kill_criterion_due"`（枚举，给 J3/J4 以后的更多类型留位）+ 决策 id + 标的 + action + 谓词四要素（复用 decisions 路由的 `KillCriterionRead`，单一来源）。
- `list_all()`：**无 LIMIT 的全量读**。三年前决策上的谓词恰恰是今天到期的那个，`LIMIT` 会静默漏掉它 —— 个人级规模（几千行）让"不截断"成为诚实且可行的选择。

**前端**：
- `#/` 默认落在今日页，`#/pool` 关注池，`POOL_HREF`/`TODAY_HREF` 常量收口所有地址（routing 测试同步改写）。
- `QuoteCell` 从 PoolPage 提为共享组件（spec 004 建立时就是两页共用的形状，今日页是第二个使用方——先复用，不复制）。
- `TodayPage`：三个独立请求（attention / 名单 / 行情），各自失败各自说。①每条链回标的页，文案**「你写的失效条件「…」观察期已到 —— 去核实数据」+「到期不等于触发」**；②复用行情列；③④各一句"还没有（缺 D4/D5、J4）"。
- `todayLabel(now: Date)`：时钟是参数（可测），"今天"是读者日历上的今天，不过时区机器（北京午夜 = UTC 的 26 号，一个会翻转的"今天"不是任何人的今天）。

## ③ 得到了什么样的结果

| 项 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `pytest -q` | **434 passed**（426 + 8） |
| 后端静态 | ruff check / format --check / mypy | 全过（74 source files） |
| 前端四道 | typecheck / lint / vitest / build | **62 passed**（60 + 2 todayLabel）· 0 errors / 4 warnings（同一类刻意保留的 set-state-in-effect，口径见 frontend/README）· build 26 modules · JS 264.52 kB |
| 质量门禁 | `scripts/dev.py check` | **`ran 9 · passed 9 · failed 0 · skipped 0`**（⚠️ 见 3.1：PATH 陷阱） |
| 静态检查 | `python -m checks --strict` | `ran 12 · skipped 0 · crashed 0` ✓ |
| ⭐ 真实冒烟 | uvicorn + `curl --noproxy` | 三步全通：空库 attention=[] → 录一条 `as_of=昨天` 的决策（201，服务端时间戳）→ **`/today` 立即返回该条**（decision_id / display / action / criterion 全部正确回传） |

### 3.1 ⭐ 环境：dev.py 的前端门禁对 PATH 敏感

`dev.py check` 的四个前端门禁经 `shutil.which("npm")` 解析——**所在 shell 的 PATH 必须含 node**。本机 node 不在系统 PATH（见 `REFERENCE.md` 与我的接手记录），裸跑 `dev.py check` 会报 4 个前端门禁全 FAIL，**看起来像代码坏了，实际是环境**。带着 node PATH 跑即 9/9 全绿。失败模式 #3「把接口坏了当成确实没有」的本地翻版。

### 3.2 变异检查（4 条，全部变红）

| # | 改坏哪里 | 变红的用例 |
|---|---|---|
| M1 | 领域边界写反：`>=` → `>` | `test_a_criterion_is_due_on_its_own_day`（边界当天必须算到期） |
| M2 | 路由丢掉到期过滤：`if criterion.due(...)` → `if True:` | `test_a_future_cutoff_does_not_arrive_in_attention` · `test_only_the_due_criteria_...`（2 failed） |
| M3 | action 写死 `HOLD`（丢真实决策动作） | `test_a_past_cutoff_arrives_in_attention` |
| M4 | `todayLabel` 改用 UTC 取日期 | `stays on the constructed calendar day`（本地午夜被翻成昨天） |

## ④ 留下了什么

- **新增能力**：今日页最小切片（默认首页）· `GET /api/v1/today` · `KillCriterion.due` · `list_all`
- **P0 状态**：D1 ✅ · D3 ✅ · I1 ✅ · **T1 ⚠️ 最小切片完成** · J1 ✅ —— P0 验收句的三段各自有了着落：加票带理由 ✅、每天打开看到动态 ✅（今日页）、想买时被拦住 ✅（决策必填门禁）
- **新增文件**：spec 005 三件套 · `routes/today.py` · `test_today_api.py` · `TodayPage.tsx` · `QuoteCell.tsx`
- **数据库里留下的**：冒烟时在真实库录了 1 条测试决策（600519，as_of=2026-09-26，理由注明"冒烟测试"）—— append-only，无法删除；它会让今日页 ① 区块有一条真实条目，正好作为演示数据
- **未做（不假装做过）**：复盘到期提醒（需 `decision_review_state`，J3）· ③数据变化（D4/D5）· ④重复检测（J4 算法未定义）· 提醒收口到 3 个区域的完整规则 · 离线新鲜度徽标（磁盘缓存层）
- **下一步候选**：S1 收尾三件（磁盘缓存 / 交易日探针 / 能力矩阵）· Playwright 入仓（浏览器层验证目前不会自动跑）· `core/config.py` v1 检索配置清理（`/health` 仍汇报已废弃的检索层）
