# 变更记录 · 2026-09-27 · 能力矩阵（spec 008）

- 日期：2026-09-27
- 类型：功能（S1 收尾最后一件 · TSP 借鉴 T-01/T-02/T-03 落地）—— **S1 数据层宣告完成**
- 范围：
  - 修改 `backend/src/alphacouncil/providers/router.py`（`CapabilityState` / `CapabilitySource` / `CapabilityCell` + `capability_matrix()` + `_cooldown_remaining()`）
  - 新增 `backend/src/alphacouncil/api/routes/capabilities.py` · `tests/unit/test_capability_matrix.py`（4 项）· `tests/unit/test_capabilities_api.py`（3 项）
  - 修改 `api/app.py`（注册）
  - 新增 `.ai/specs/008-capability-matrix/` · 修改 `.ai/status.md`（**S1 宣告完成**）
- 依据：宪法 7.7 / 2.1 · TSP 借鉴笔记 ①②③ · status.md D3 还差项

---

## ① 想做什么

S1 还差的最后一件：**能力矩阵**。T-02 的判断是"哑掉的功能要提前暴露"——财务源没接好，依赖它的功能就是哑的，而用户不知道。路由器已经拥有两份事实：provider 的**静态声明**（datasets × markets）与**运行时健康**（冷却/熔断记账），本 spec 把它们合成一张三态矩阵并暴露为 API。至此 **S1 数据层宣告完成**（D1/D3/三源互备/Pydantic 契约 + spec 004/006/007/008 全部落位）。

## ② 做了什么

- **三态枚举**（宪法 7.7，禁布尔）：`usable`（≥1 个声明方清醒）/ `candidates`（有源声明但全在冷却，带各自剩余秒数）/ `pending`（无人声明，reason 明说"未接入"——是产品事实，不是错误）。
- **`capability_matrix()`**：`Dataset × Market` 全叉积 15 格，**只读声明与健康记账，绝不发网络请求**——这正是它和"取数"的本质区别，页面可以随便问。`_cooldown_remaining()` 是 `_cooling()` 的数值版。
- **`GET /api/v1/capabilities`**：15 格按 dataset → market 稳定排序，不过滤不隐藏——`pending` 格必须原样出现，否则用户会把"没做"当成"坏了"。
- **真实矩阵钉死为测试**（AC-1）：`default_router()` 直接构造（无网络），15 格逐格写死期望。**provider 静默改声明（删 dataset/删市场）→ 这张表先红**——这正是矩阵存在的意义。

**有意不做**（宪法 2.1 #2，投机性集成）：前端门控。需要被门控的页面（财务面板等）还不存在，现在接就是"以后可能用得上"的代码；矩阵先作为 API 事实与钉死的测试存在，UI 门控随被门控的页面落地（已写进 spec 边界与 status.md 还差项）。

## ③ 得到了什么样的结果

| 项 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `pytest -q` | **468 passed**（461 + 7） |
| 后端静态 | mypy / ruff | 全过（80 source files） |
| 质量门禁 | `scripts/dev.py check` | `ran 9 · passed 9 · failed 0` |
| ⭐ 真实冒烟 | uvicorn + curl | 15 格 = **6 usable**（realtime/daily/adj_factor × sh/sz）+ **9 pending**，与钉死矩阵逐格一致 |

### 3.1 变异检查（3 条，全部变红）

| # | 改坏哪里 | 变红的用例 |
|---|---|---|
| M1 | candidates 分支短路（全冷却仍报 usable） | `test_a_blocked_source_turns_its_cells_into_candidates` |
| M2 | pending 格被丢弃（`continue`） | 生产矩阵钉死测试 + pending reason 测试 + API 15 格计数（3 failed） |
| M3 | 冷却剩余秒数被隐藏（恒 None） | `test_a_blocked_source_turns_its_cells_into_candidates`（cooldown_remaining_s > 0） |

### 3.2 测试自己抓住的一个错误期望

生产矩阵的 sources 期望最初写错（把东财写进了 realtime 格——它只声明 daily/adj_factor）。测试红 → 查声明 → 修正期望。**这正是 AC-1 的运行方式**：矩阵钉死测试对"我以为"和"实际声明"的任何分歧都会立刻发声。

## ④ 留下了什么

- **新增能力**：`GET /api/v1/capabilities`（15 格三态矩阵）· `router.capability_matrix()` / `_cooldown_remaining()`
- **里程碑**：**S1 数据层完成**。当前阶段总览：S0 ⚠️（traces 写入器 / specs 重写仍未做）· **S1 ✅** · S2 ✅ · S3 ⚠️（最小切片）· S4 ✅（J1）· S5 ⚠️（仅最小程序）
- **未做（不假装做过）**：UI 门控消费矩阵（等页面出现）· `ADJ_FACTOR` 声明为 usable 但**从未实测**（data-sources.md 承载声明≠实测的差别）
- **下一步候选**：Playwright 入仓（浏览器层自动化，宪法 12.1 五条红线断言的载体）· `core/config.py` v1 检索配置清理（`/health` 仍汇报废弃检索层）· trace 写入器（简历验收①的第一块）
