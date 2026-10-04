# `.ai/checks/static/` —— 编译期扫代码检查

> **检查对象 = 源码（AST 级）。** 抓的是**"某段代码不该存在"**这类缺陷 —— **测试永远抓不住它**（测试只能证明"跑到的路径是对的"）。
> 建立：2026-09-26 · 依据 `references/deep-dives/09-primitives.md` 决定 8

---

## 一、每个脚本的头部必须写明三件事

```python
#!/usr/bin/env python3
"""守的缺陷：#<issue 号> —— <一句话描述>

反模式（禁止）：
    <具体的坏代码示例>

正确写法：
    <具体的好代码示例>

为什么不能用测试守：<说明这个缺陷为什么测试抓不住>
"""
```

**四件事缺一不可。** 理由：**三年后的人（或 agent）需要知道"为什么有这个脚本"，否则会把它删掉。**

---

## 二、CI 位置

```
Lint  →  Typecheck  →  ★ check-static  →  Test  →  Build
```

**在 Lint 之后、Build 之前** —— **早失败**：不用等测试跑完。

---

## 三、脚本清单

### 3.1 P0（对应宪法条款，必须有）

| # | 脚本 | 禁止 | 守的规则 |
|---|---|---|---|
| **S-01** | `no-raw-http` | 业务代码里直接 `httpx.get` / `requests.get` / `urlopen`；**任何文件里**自行 `httpx.Client(...)`（唯一构造点是 `core/http.py`，见 ADR-0031） | 宪法 7.8（唯一入口）· 4.5 |
| **S-02** | `no-boolean-state` | 用布尔值跟踪状态（`is_reviewed` / `has_outcome` 等组合） | 宪法 7.7 · 红线 6 |
| **S-03** | `no-prediction-field` | 出现"目标价 / 涨跌预测 / 买卖建议 / 看好 / 看空"类字段或接口 | 红线 1 · 2 |
| **S-04** | `check-append-only-triggers` | 日志类表缺 `BEFORE UPDATE` / `BEFORE DELETE` 触发器 | 宪法 5.4 · 红线 4 |
| **S-05** | `check-error-codes` | 代码里出现的 `code` 未登记在 `.ai/error-codes.md` | `.ai/error-codes.md` 维护规则 4 |
| **S-06** | `no-client-supplied-id` | 决策日志的 API schema 暴露了主键字段 | 宪法 5.2 规则 9 · 红线 4 |
| **S-13** | `tool-encoding` | 开发者工具（`scripts/` · `checks/__main__.py`）打印人类可读输出却**没调 `use_utf8()`** | 回归 0004 · 门禁可读性 |

### 3.2 P1（红线 UI 层，需要 E2E 配合）

| # | 脚本 | 检查 | 守的红线 |
|---|---|---|---|
| **S-07** | `home-no-return-rate` | 首页源码**不含"收益率"字样** | 9 |
| **S-08** | `immature-outcome-blank` | 未成熟结果的渲染分支**输出空**（不是 `0` / `—`） | 6 |
| **S-09** | `time-cost-in-stop-loss` | 止损提示组件**必含"恢复所需年数"** | 12 |
| **S-15** | `no-mojibake` | 源文件含 U+FFFD，或字节根本不是合法 UTF-8 —— **两个 code，因为成因和修法都不同** | 红线 1（说的话必须是人话） |

> ⚠️ **S-07 ~ S-09 是源码级静态检查，只能作为第一道防线**；最终由**前端 E2E 断言**保证（见宪法 12.1）。

### 3.3 P2（工程卫生）

| # | 脚本 | 检查 |
|---|---|---|
| **S-10** | `no-print` | 禁止 `print()`（宪法 7.4） |
| **S-11** | `no-bare-except` | 禁止裸 `except:` / `except Exception: pass`（宪法 7.3） |
| **S-16** | `no-enum-drift` | 后端 `openapi.json` 里的枚举与前端 `type X = 'a' | 'b'` 的镜像不一致（**双向**），或未在豁免表里写下它**是什么**（spec 049） | 同一概念两个家（`styleguide.test.ts` 已记录这个形状） |
| **S-17** | `no-route-drift` | 前端调用点 × 应用实际提供的路由，\**双向**，且**四个桶**（drift / unverifiable / orphan / ok）（spec 050）| 同一个接口两侧漂移（与 `S-16` 同类）|
| **S-18** | `no-response-drift` | 后端 `openapi.json` 发布的**字段**，前端没有一个具名类型声明它 —— 判据是**子集**且**只报这一个方向**（spec 053）| ⚠️ **三个已量出的洞**：① **嵌套** schema（`DueRead` 在 `Today.due` 里，⭐ 顶层比较看不见）② **请求体**（`api.ts` 里是函数体内的字面量）③ **只比字段名不比类型**（`volume: number` 改成 `string` 它不红）。⭐ 另有一处**假通过**：小 schema 会被无关类型满足（`Symbol` 的 3 个字段同时满足 3 个类型），⭐ 所以 `LessonCreate` 等是**碰巧**绿的 |
| **S-14** | `git-tracked` | 源文件在磁盘上却不在 git 里（未跟踪报 error；**被 `.gitignore` 藏起来报 warning** —— `git status` 看不见后者） |
| **S-12** | `check-doc-sync` | 关键文档里的代码块与实现**不脱同步**（借"测试直接从文档抽取代码执行"的思路） |

> ⚠️ **S-13 放在 P0 而不是 P2**：它守的不是风格，是**门禁本身能不能说话**。
> `dev.py` 曾因缺这一行而在中文控制台上把"十道全过"报成退出码 1（回归 0004），
> 而**同一天写第四个工具时就又犯了一次** —— 三个调用点不是机制，规则才是。
> 详见 `.ai/regressions/0004-console-encoding.md` 与 `0005`。

---

## 四、实现约束

1. **必须 AST 级，不用正则** —— 正则会被字符串字面量、注释、多行写法绕过。
   （例：`no-raw-http` 要区分"`import httpx` 后用"和"字符串里出现 `httpx.get`"。）
2. **每条脚本必须有自己的测试** —— 一个"应该报错"的 fixture + 一个"不该报错"的 fixture。
3. **报错必须用统一诊断信封**（`.ai/error-codes.md` 第一节），`fix` 给出**可执行的修改建议**。
4. **允许显式豁免，但必须写明理由** —— 用 `# noqa: S-01 -- 理由` 形式，**注释里的理由必填**。
5. **脚本自身不得依赖被测代码**（不能 import 被测模块）。

---

## 五、当前状态

| 项 | 状态 |
|---|---|
| 脚本清单 | ✅ 已定义（14 条） |
| 脚本实现 | ✅ **已实现** —— `backend/checks/rules/`，`checks/` 共 2,729 行 / 22 文件（最大 265 行） |
| 脚本测试 | ✅ **已实现** —— `backend/tests/unit/test_static_checks.py`，99 项（每条规则一个"必须报错"+一个"必须静默"） |
| 接入 `check-static` | ✅ **已接入** —— `python -m checks --strict`（由 `scripts/dev.py` 调用） |
| 接入 CI | ⏳ **待接入** —— 仓库还没有 CI 配置 |

### 5.0 模块分层

`checks/` 内部**只向下依赖，无环**（宪法 7.2 要求单模块 ≤400 行，`framework.py` 曾长到 501 行，已拆）：

```
checks/models.py       信封：Issue / CheckMeta / CheckResult / Severity / Rule（无包内依赖）
checks/exemptions.py   # noqa 解析与施加                → models
checks/scan.py         ScanContext / format_target      → exemptions, models
checks/ast_utils.py    AST 助手（独立）
checks/framework.py    facade，再导出以上四个（规则模块只 import 这一个）
checks/frontend.py     前端定位（S-07/08/09 共用）
checks/rules/*.py      12 条规则，各自 import framework
checks/registry.py     规则注册表
checks/__main__.py     运行器
```

**公开导入面由 `framework.py` 的 `__all__`（20 个名字）冻结** —— 加名字是唯一扩大它的方式，拆分时调用方零改动。

### 5.1 运行方式

```bash
python -m checks                    # 人读的汇总（stderr）
python -m checks --strict           # 有 error 或规则没跑 → 退出 1
python -m checks --json             # stdout 只放一个 JSON 文档（§1.1）
python -m checks --only S-01,S-05   # 只跑指定规则
python -m checks --root <path>      # 扫另一个仓库根（用于变异检查）
```

**⚠️ 退出码**：`python -m checks` 单独跑时遵循 `.ai/error-codes.md` §3 —— **`0` 只表示"跑完了"，发现问题是 `0`**。
门禁需要另一个信号，所以 `--strict` 是**显式 opt-in** 的，只有 `scripts/dev.py` 用它。**不改契约，加一个开关。**

**⚠️ `--strict` 下 `skipped` 也算失败**（T-19）：**没有东西可扫 ≠ 通过**。当前 S-04 / S-07 / S-08 / S-09 因为没有 schema 与前端而 skip，所以 `python scripts/dev.py check` 会正确地退出 1。

### 5.2 命名契约

**规则的 `slug` = 模块文件名**，`check-append-only-triggers` 住在 `checks/rules/check_append_only_triggers.py`。
`registry.py` 的 `MODULE_BY_ID` 按这个规则推导，并有测试逐个 import 核对 —— **防止注册表里一个复制粘贴错误把某条规则静默关掉**。

### 5.3 豁免写法

```python
import httpx  # noqa: S-01 -- the module already wraps a client it was handed
```

* ⭐ **先考虑这行根本不需要存在**：S-01 的两个白名单（`CONSTRUCTION_SITES` /
  `HTTP_AWARE_MODULES`）是**具名文件**，加一个文件比加一条豁免更容易被审阅 ——
  豁免是有时效的静默，名单是一次性的显式。
* **行级**：写在有代码的那一行行尾 → 只豁免该行。
* **文件级**：**单独占一行**、且在前 12 行内 → 豁免整个文件。
* **理由必填**：`# noqa: S-01` 不带 `-- 理由` **仍然生效**（否则代码既坏了又没法豁免），**但会额外报一条 `CHECK_EXEMPTION_UNREASONED` 错误**。

> ⚠️ 实测坑：注释横幅里写 `` # noqa: S-01 -- reason `` **会被 ruff 当成真的豁免指令**。写文档举例时注意。
>
> ⚠️ **在 `.md` 里，文件级豁免必须放进围栏。** 解析器要**两个**条件同时成立：
> `#` 在**行首**（否则不算「单独占一行」）、理由在**行尾**（否则正则的 `\s*$`
> 匹配不上，因为行尾是 ` -->`）。⭐ 裸写一行会被 markdown 当成一级标题，
> ⭐ 裹进 `<!-- -->` 又让 `#` 跑到行首之外、整份文件静不下来。
> ⭐ **放进 ``` 围栏两个条件都成立**，而且渲染出来是「一条指令」而不是「一节标题」。
> 实测见 `.ai/regressions/0005-arch-doc-and-adr-divergence.md` 开头。

---

*本目录与 `.ai/error-codes.md` 同步维护。*
