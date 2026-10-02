# Agent 开发框架

本目录定义了 AlphaCouncil 的**规格驱动、多角色协作**开发流程。它约束的不是代码，而是**「谁在什么阶段做什么、不能做什么」**。

## 为什么需要它

当项目由 AI Agent 主导开发时，最容易出现三类问题：

1. **无约束生成** —— Agent 自由发挥，代码风格分裂、依赖随意引入、测试缺失。
2. **自我验证** —— 同一个 Agent 写代码又写测试，自己的 bug 自己验不出来。
3. **上下文丢失** —— 换了会话就忘了上次为什么这样设计，重复踩坑。

本框架用三个层次分别解决：**规格层**约束「做什么」，**角色层**约束「谁来做」，**质量层**约束「能不能合并」。

## 目录结构

```
.ai/
├── constitution.md        # 项目宪法（v3.0）—— 最高约束，动手前必读
├── status.md              # 能力地图：目标能力 / 当前状态（每行以"还差什么"结尾）   ← v3.0 新增
├── agent-guide.md         # agent 工作指南：读的顺序 / 失败模式 / 我做不到什么 / 回答模板  ← v3.0 新增
├── data-sources.md        # 数据边界 + 实测记录 + 降级差异 + 未接入表                ← v3.0 新增
├── error-codes.md         # 错误码命名空间 + 诊断信封 + 退出码契约                 ← v3.0 新增
├── failure-modes.md       # 失败模式清单（只增不改，每条带"自查问法"）              ← v3.0 新增
├── release-checklist.md   # 发布检查清单（8 项）+ 打包排除清单格式                  ← v3.0 新增
├── agents/                # 角色定义
│   ├── architect.md       # 架构师：只出方案，不写代码
│   ├── developer.md       # 开发者：按 spec 实现
│   ├── tester.md          # 测试者：独立验证，不信任实现
│   └── reviewer.md        # 审查者：只读，输出问题台账
├── specs/                 # 规格（每个功能一个目录）
│   └── <编号>-<功能名>/
│       ├── spec.md        # 做什么
│       ├── plan.md        # 怎么做（⚠️ 对审查者隐藏）
│       └── tasks.md       # 拆成哪些任务
├── checks/                # 检查子系统                                    ← v3.0 新增
│   ├── data/              # 运行时扫库（24 条一致性检查）
│   └── static/            # 编译期扫代码（AST 级，12 条反模式脚本）
├── regressions/           # 回归记录（每个缺陷 → 测试 + 变异检查结果）        ← v3.0 新增
├── memory/
│   ├── decisions.md       # 架构决策记录（ADR）—— 为什么这样设计
│   └── YYYY-MM-DD.md      # 工作日志
├── traces/                # agent 运行 trace：Trace → Observation → Score   ← v2.0 新增
└── logs/                  # 台账（Append-Only，禁止修改历史）
    ├── review/            # 审查记录
    └── changes/           # 变更与依赖审批记录
```

> **⚠️ 台账只有这两处**（`memory/decisions.md` + `logs/`）。**一张台账只存在一个地方**，不新建重复目录。
> **⚠️ 只增不改的文件**：`failure-modes.md` · `regressions/` · `logs/` · `decisions.md`（追加式）。

> **⚠️ `specs/` 目录状态（2026-09-26）**：现有 `001-data-layer` / `002-retrieval-layer` / `003-agent-orchestration` 写于 v1 方向，**已与新宪法不一致**，待按 v3 路线图（S0–S5）重写。

## 标准工作流

```
① 立项     Architect 读 constitution → 产出 specs/NNN/spec.md + plan.md
                              ↓ 人工确认规格
② 拆解     Architect 产出 tasks.md（每个任务可独立验证）
                              ↓
③ 实现     Developer 按 task 逐个实现 + 写单元测试
                              ↓
④ 验证     Tester 独立编写验收测试（不看 Developer 的测试）
                              ↓
⑤ 审查     Reviewer 只读审查 → 输出问题台账（P0/P1/P2）
                              ↓
⑥ 修复     Developer 按台账修复 → 附 file:line 与验证命令
                              ↓
⑦ 完成     make check 全绿 + 审查通过 + 人工确认
```

> ⚠️ **第 ⑦ 步的定义**：「完成」= **`make check` 通过**，不是"我写完了"，不是"能跑起来"。

## 六条不可违反的纪律（v1.0 三条 → v2.0 四条 → v3.0 五条）

1. **规格先行** —— 没有 `spec.md` 的功能改动不受理。
2. **角色分离** —— 实现与验收测试必须由不同角色完成；Reviewer 只读不改。
3. **台账 Append-Only** —— `.ai/logs/` 下的记录只追加，历史不可篡改。
4. ⭐ **单一命令入口 + `make check` 才算完成**（v2.0 新增）—— 所有命令走 `make`，不直接调 `pytest` / `ruff` / 裸脚本。
5. ⭐ **能往 ③④ 移的规则必须移**（v3.0 新增）—— 见宪法 0.2：一条规则如果只写在文档里，**它迟早会被违反**（不是因为有人故意，而是因为没人记得）。
6. ⭐ **测量时把做法也量一下**（v3.1 新增）——写一个具体做法前，先读签名、读类型、读词表；写一个具体数字前，先数。⇓ **两种错误的失败点相同：都是没打开文件，只是一种在写代码前失败、另一种在计划被执行时失败。**
   实测（2026-10-02）：一份计划里的三处说法被推翻 —— 「**12 约束**」（实际 8，而 12 从 SQL 推不出来）、「`default_router()` 加 `BaostockFinancial`」（**照做会 mypy 失败**，因为那个列表的类型是 `list[MarketDataProvider]`，而财务实现的是第二个协议）、「整栈已交付，只差没插」（实际还差**九处**，其中两处是设计决定）

## v3.0 相对 v2.0 的主要变化

| # | 变化 | 来源 |
|---|---|---|
| 1 | 新增 **第零条 0.2「从纪律到机制的四层次」**（**判据：能往 ③④ 移就必须移**） | 09 primitives · 11 open-science |
| 2 | 新增 **第十一条 边界与非目标**（不做清单 + "降低的是执行成本不是判断成本"） | 11 open-science |
| 3 | 新增 **第十二条 缺陷的固化（五种形态）** + **红线三层落地** | 07~11 五篇交叉 |
| 4 | **数据四态**（`ok`/`no_data`/`error`/**`unavailable`**）写进 4.6 | 10 akshare · 11 open-science |
| 5 | **SQLite CHECK 外置 + append-only 触发器**写进 5.4（把纪律变成机制） | 11 open-science |
| 6 | **状态用枚举 + 有限状态机**写进 7.7；**外部调用唯一入口**写进 7.8 | 09 primitives · 10 akshare |
| 7 | **变异检查**写进 8.3（"改坏会不会红"） | 10 akshare |
| 8 | **工作记录四段式**（加 `留下了什么`）+ **文案语气**写进 10.5 / 10.6 | 11 open-science |
| 9 | 红线 15 第 ④ 档 **"导出备份" → "替用户托管数据备份"** | 11 open-science |
| 10 | 新增 **8 个工程资产**（见目录结构）+ **7 条 ADR**（ADR-0013~0019） | 全 11 篇 |

**来源**：`references/deep-dives/README.md`（全 11 篇 · **188 项可落地决定** · 15 项对既有设计的修正）
**落库记录**：`.ai/logs/changes/2026-09-26-constitution-v3.md`

---

## v2.0 相对 v1.0 的主要变化

| # | 变化 | 来源 |
|---|---|---|
| 1 | 新增**产品红线 15 条**（写进宪法，代码必须守住） | 产品定义 v3 |
| 2 | 新增**Agent 协作规约**（六条工作约定 + 新增机制门槛 + 单一命令入口 + 不虚构） | wealthfolio `AGENTS.md` / anki `CLAUDE.md` |
| 3 | 技术栈整表更新：移除 LlamaIndex / Qdrant / LightRAG / AKShare / Next.js | 产品定义 v3 |
| 4 | 新增**数据契约**（四类口径 + PIT + 数据源纪律） | TSP 借鉴笔记 / anki 反面教材 |
| 5 | 新增**数据库与迁移纪律**（可逆 / 不编辑已发布 / 迁移前快照 / `temp_store=FILE`） | wealthfolio 51 个迁移 + 21KB 验证报告 |
| 6 | 新增**Agent 权限边界**（工具权限四档，红线 15 的落地） | wealthfolio `cli-mcp-agent-access.md` |
| 7 | 审查纪律升级：**质疑机制是否需要存在** + **「修复未经验证」** | wealthfolio `AGENTS.md` |

## 给人类贡献者

如果你是人类开发者，这套框架同样适用——只是你一个人可以扮演多个角色，但请**在不同阶段切换心态**：写代码时不要想着怎么通过自己的测试，写测试时要假设实现是错的。

## 给 AI Agent

**每次开始工作前，按顺序读取**：

1. `.ai/constitution.md` —— 了解红线（**15 条产品红线 + 12 条工程条款**）
2. `.ai/status.md` —— **我在哪一步、还差什么**
3. `.ai/agent-guide.md` —— **读的顺序 / 失败模式 / 我做不到什么 / 回答模板**
4. 当前任务对应的 `.ai/specs/NNN-*/spec.md` 与 `plan.md`
5. `.ai/memory/decisions.md` —— 了解既有架构决策，**避免推翻已有结论**
6. 你的角色定义文件

**按需读**：`.ai/data-sources.md`（取数）· `.ai/error-codes.md`（错误处理）· `.ai/failure-modes.md`（**动手前扫一眼**）· `.ai/checks/`（加检查）· `.ai/regressions/`（修 bug）· `.ai/logs/changes/`（改宪法 / 加依赖）

**工作完成后必须**：

- 在 `.ai/memory/YYYY-MM-DD.md` 追加工作日志（**四段式**，含 `留下了什么`）
- 若产生了架构决策，追加到 `.ai/memory/decisions.md`
- 若修了 bug，在 `.ai/regressions/` 建档（**含变异检查**）
- 若踩了新坑，往 `.ai/failure-modes.md` 加一条
- 若完成了一个能力，更新 `.ai/status.md`
- 若发现问题，写入 `.ai/logs/review/`
- **运行 `make check`，并在报告中写明结果**（未运行就说未运行，不得暗示已通过）

