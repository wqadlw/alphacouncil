# Spec 008 · 能力矩阵（T-02，S1 收尾最后一件）

- **状态**：Active
- **目标阶段**：S1（status.md D3 还差项「能力矩阵 `candidates`/`pending`」· TSP 借鉴 T-01/T-02/T-03）
- **依赖**：D3 能力路由（已完成，provider 声明 + 运行时健康都在路由器里）
- **依据**：`references/tsp/借鉴笔记.md` ①②③ · 宪法 4.6 / 7.7

---

## 背景与目标

T-02 的核心判断：**"哑掉的功能"要提前暴露**——财务源没接好，"失效条件自动检查"就是哑的，而用户不知道；T-01：能力 = 一个标准化数据集，不是"功能"；T-03：**页面门控统一以 `usable` 为准**，不以"订阅了什么"为准。

本 spec 把路由器已经拥有的两份事实——provider 的**能力声明**（静态）与**运行时健康**（冷却/熔断）——合成一张矩阵并暴露出来。三态：

| 态 | 含义 | 判定 |
|---|---|---|
| `usable` | 现在就有源能服务 | ≥1 个声明方当前清醒（不在冷却） |
| `candidates` | 有源声明、但现在全在冷却 | 全部声明方 cooling（带各自冷却剩余秒数） |
| `pending` | 根本没人声明 | reason 说明"未接入" |

真实矩阵（实测声明）：15 格 = 5 数据集 × 3 市场。usable 6 格（realtime/daily/adj_factor × sh/sz）；pending 9 格（financial ×3、instruments ×3、realtime/daily × BJ）。`instruments` 数据集当前无人声明也是事实——标的清单目前来自用户手工输入，矩阵如实反映。

## 功能需求

| 编号 | 需求 |
|---|---|
| FR-1 | `MarketDataRouter.capability_matrix()`：遍历 `Dataset × Market` 全叉积，按上表三态合成格子；每格带声明方列表（name / healthy / cooldown_remaining_s）。**只读声明与健康，绝不发网络请求** |
| FR-2 | 模型落在 `providers/router.py`（它描述的是路由器自身的状态）；枚举 `CapabilityState`（usable/candidates/pending），禁布尔（7.7） |
| FR-3 | `GET /api/v1/capabilities`：`{generated_at, capabilities: [15 格]}`，排序 dataset → market（稳定可测）。无 DB 依赖 |
| FR-4 | 冷却剩余秒数来自路由器健康记账（`_BLOCKED_COOLDOWN_S` / `_FAILURE_COOLDOWN_S` 的运行时结果），**冷却中的源如实出现在 sources 里（healthy=false）**——"有候选但现在不可用"正是 candidates 态的本意 |
| FR-5 | 本轮**不做前端门控**：需要被门控的页面（财务面板等）还不存在，现在接是投机性集成（宪法 2.1 #2）。矩阵先作为 API 事实暴露，UI 门控随被门控的页面落地 |
| FR-6 | `cooldown_remaining_s` 只在 cooling 时非空；healthy 源不带剩余时间 |

## 验收标准

| 编号 | 标准 |
|---|---|
| AC-1 | 真实生产路由器（不联网）：6 格 usable（realtime/daily/adj_factor × sh/sz）· 9 格 pending——**把生产的能力图钉死成测试**，任何 provider 静默改声明都会红 |
| AC-2 | 一个被 403 熔断的源 → 它所在的格变为 candidates、`healthy=false`、cooldown_remaining_s > 0；同格的另一清醒源保持 usable |
| AC-3 | API：200 + 15 格 + 排序稳定 + generated_at 带 Z |
| AC-4 | 门禁全绿 |
| AC-5 | 变异 ≥ 3 |

## 已知的失败（本 spec 防的事故）

| # | 事故 | 防线 |
|---|---|---|
| 1 | provider 静默改声明（删一个 dataset/市场）→ 依赖它的页面变哑、无人知晓 | AC-1 把真实生产矩阵钉死为测试 |
| 2 | 有源但全在冷却时被报成 usable → 页面发起必然失败的请求 | candidates 态 + 冷却剩余秒数 |
| 3 | pending 被渲染成"故障"→ 用户以为系统坏了 | pending 的 reason 明说"未接入"，是事实不是错误 |
| 4 | 布尔字段表达三态 | 枚举（7.7） |

## 边界（本 spec 不做）

- **前端门控**：等被门控的页面出现（财务/公告面板）再接——本轮明确不做。
- 不新增数据集/市场：`ADJ_FACTOR` 的生产可用性（东财）未实测，矩阵如实按声明标注 usable——**声明 ≠ 实测过**，这个差别由 data-sources.md 承载。
- 交易日探针不进矩阵：它是派生判定（spec 007 已有自己的 basis 语义），不是数据集能力。
