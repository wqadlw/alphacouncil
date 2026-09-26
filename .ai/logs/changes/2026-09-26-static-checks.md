# 变更记录 · 2026-09-26 · 12 条静态检查（`check-static` 从占位符变成真实现）

> **一句话**：`check-static` 此前是一个**说得出名字、跑不起来**的门禁 —— 文档列了 12 条检查、代码里 0 条。
> 本轮把它变成 **12 个真模块 + 99 个测试**，并用**全 12 条变异检查**证明它们真的会红。
>
> 关联：`.ai/checks/static/README.md`（规格）· `.ai/error-codes.md`（诊断信封与码）· `.ai/constitution.md` 7.3 / 7.4 / 7.7 / 7.8 / 12.1 · ADR-0026（T-14~T-19）

---

## 1. 新增：`backend/checks/`（静态检查子系统，2,580 行 / 18 文件）

| 文件 | 作用 |
|---|---|
| `checks/framework.py` | 诊断信封 · 扫描上下文 · 豁免解析 · AST 助手 |
| `checks/frontend.py` | 前端源码定位（S-07/08/09 共用） |
| `checks/registry.py` | 12 条规则的**显式**绑定与执行顺序 |
| `checks/rules/*.py` | 12 个规则模块，**每个头部写明四件事** |
| `checks/__main__.py` | 运行器：退出码 · stdout/stderr 分流 · 崩溃处理 |

**规则**：S-01 裸 HTTP · S-02 布尔状态 · S-03 预测字段 · S-04 append-only 触发器 · S-05 错误码登记 · S-06 客户端主键 · S-07 首页收益率 · S-08 未成熟结果 · S-09 时间成本 · S-10 `print` · S-11 裸 `except` · S-12 文档同步。

---

## 2. 新增：`tests/unit/test_static_checks.py`（99 项）

**每条规则两个 fixture**：一个"必须报错"、一个"必须静默"。**前者才是重点** ——
没有它，一条规则和一个从不运行的规则无法区分。这个仓库已经为此付过一次学费（见第 5 节）。

另含：信封形状 · 豁免解析（行级/文件级/理由必填）· `contains_token` 的词组匹配 ·
**注册表完整性**（12 条、ID 连续、每个 ID 都能 import 到声明它的模块、每个模块的 `CODE` 都在 `ErrorCode` 里）· 运行器退出码与流路由 · **规则崩溃必须报错**。

---

## 3. 三个必须记下来的设计决定

### 3.1 退出码：不改契约，加一个开关

`.ai/error-codes.md` §3 说 `0` = "跑完了"，**发现问题也是 0**。这对"检查器"是对的，对"CI 门禁"不可用。
**没有改契约**，而是加了 **`--strict`**（有 error 或规则没跑 → 退出 1），**只有 `scripts/dev.py` 用它**。
理由：**改行为要显式要求，不偷偷改契约**。

### 3.2 `skipped` 不算通过（T-19）

S-04 没有 schema 可扫、S-07/08/09 没有前端可扫 —— 它们报 **`skipped`**，不是"通过"。
`--strict` 下 skipped 也退出 1，所以 **`python scripts/dev.py check` 现在会正确地失败**（`ran 5 · passed 4 · failed 1`）。

**这是刻意的。** 一条"没有东西可扫所以绿灯"的规则，就是本子系统存在的理由的反面。

### 3.3 豁免必须有理由，但**没有理由也仍然生效**

`# noqa: S-01 -- 理由`：
* 行尾 → 只豁免该行；**单独占一行且在前 12 行内** → 豁免整个文件。
* 不带理由 → **仍然豁免**（否则代码既坏了又没法豁免），**但额外报一条 `CHECK_EXEMPTION_UNREASONED` 错误**。

这个组合才让"理由必填"成为规则而不是愿望。

---

## 4. 修掉的真实缺陷（都是检查抓出来的，不是想出来的）

| # | 缺陷 | 怎么发现的 |
|---|---|---|
| 1 | **`provider` 路径判断写错** —— S-01 对 `providers/sources.py` 误报 `import httpx` | 第一次真实运行就报错；`_PROVIDERS_REL` 相对基准搞错了一层 |
| 2 | **豁免对不上** —— 豁免写 `S-01`，框架拿 `CHECK_RAW_HTTP` 去比，**永不生效** | 单元测试 `test_an_exempted_finding_disappears` 红 |
| 3 | **`S-05` 分不清"属性引用"和"裸字符串"** | 单元测试红；修法是把两种用法分开收集，并**只对 `src/` 的裸字符串报错**（`checks/` 禁止 import 产品，只能用字面量） |
| 4 | **枚举里声明但文档没登记 → 漏报** | 单元测试红：只查"用到的"会漏掉"声明了但没人用的" |
| 5 | **表头计数被重复累加 9 次** | 变异检查时发现的：无理由豁免被**每条打开该文件的规则各报一次**，而表头按规则累加。修法：**计数改为对去重后的结果按错误码归属** |
| 6 | **文档与代码 slug 不一致** | S-12 自己抓出来的：`check-append-only-triggers` vs `append-only-triggers`；随后按"slug = 模块文件名"统一，并加测试逐个 import 核对 |
| 7 | **注释里的 `# noqa: S-01 -- reason` 会被 ruff 当成真豁免** | ruff 警告 `Invalid # noqa directive`。**活生生的"注释会被误读"案例**，已写进 README §5.3 |

---

## 5. 变异检查（12/12 全部变红）

在**临时副本**上种入缺陷，逐条确认规则会红（**不改动真实仓库**）：

| 种入的缺陷 | 期望 | 实测 |
|---|---|---|
| `import httpx` + `httpx.get()` | S-01 | ✅ 2 error |
| `reviewed: bool` + `outcome_filled: bool` | S-02 | ✅ 1 error |
| `target_price: float` | S-03 | ✅ 1 error |
| `CREATE TABLE decisions` 无触发器 | S-04 | ✅ 1 error |
| `"DATA_SOURCE_RATE_LIMITTED"`（错拼）+ 已登记码写成裸字符串 | S-05 | ✅ 3 error |
| `class DecisionCreate: id: int` | S-06 | ✅ 1 error |
| 首页含"收益率" | S-07 | ✅ 1 error |
| `resultScore ?? 0` | S-08 | ✅ 1 error |
| `StopLossDialog` 不含"恢复所需年数" | S-09 | ✅ 1 error |
| `print()` | S-10 | ✅ 1 error |
| 裸 `except:` | S-11 | ✅ 1 error |
| README 多一行 `S-99` | S-12 | ✅ 1 error |
| `# noqa: S-10`（无理由） | 运行器 | ✅ `CHECK_EXEMPTION_UNREASONED` |

**`ran 12 · skipped 0 · findings 33 (13 error)`** —— **没有一条规则是"永远绿灯"的。**

---

## 6. 顺带修正的错误码契约

`.ai/error-codes.md` 与代码**此前不一致**（文档用大写下划线，代码用 `"blocked"` / `"no_provider"`）。
本轮把 **`ErrorCode(StrEnum)` 立为单一真源**，`DataResult.error_code` **类型化**：

* 写错码 → **编译期就挂**（实测：pydantic 直接拒绝 `input_value='blocked'`，一次抓出测试里 2 处漏网）。
* 补登记：`DATA_SOURCE_UNREACHABLE` · `DATA_SOURCE_NOT_SUPPORTED` · 12 个 `CHECK_*` · `CHECK_EXEMPTION_UNREASONED` · `CHECK_RUNNER_ERROR`。
* `providers/base.py` 的异常类 `code` 从**第二个字符串命名空间**改为 `ErrorCode`（**它此前是死代码，没有任何地方读**）。
* `DATA_SOURCE_NOT_SUPPORTED` 定为 **info 不是 error** —— 能力路由在**发请求之前**判定，把它算成故障会让"我们没问过它"看起来像"它坏了"。

---

## 7. 门禁状态（实测）

```
python scripts/dev.py check-lite
  [PASS] lint / typecheck / licenses / test          ran 4 · passed 4        exit 0
  → ruff 全绿 · mypy strict 全绿（42 文件）· 200 passed

python scripts/dev.py check
  [PASS] lint / typecheck / licenses / test
  [FAIL] check-static                                ran 5 · passed 4 · failed 1   exit 1
  → 12 条规则全跑，0 error，0 warning，20 info，4 skipped（S-04/07/08/09）
```

**`check` 现在失败是正确的**：4 条规则因"没东西可扫"而 skip，T-19 不允许它变绿。

---

## 8. 还差什么

* **CI 配置**（仓库还没有）
* `.ai/checks/data/` 的 24 条运行时扫库检查（0 实现）—— **`check-data` 门禁仍是 `implemented=False`**
* S-04 / S-07 / S-08 / S-09 需要真实载体才能观测：**schema（S1）与前端（S2）**
* S-11 的已知边界：**只抓"裸 `except`"与"空 body"**，不判断"捕获后处理得好不好" ——
  静态规则分不清"刻意的降级返回"和"吞掉的 bug"，硬猜会被关掉，那一层留给评审。

---

## 9. 收尾：拆分 `framework.py`（我自己违反了宪法 7.2）

### 9.1 问题

统计交付物规模时发现：**`checks/framework.py` = 501 行，超过宪法 7.2 的「单模块不超过 400 行」。**

这一整轮我都在讲"没进检查的规则只是意图"，那就得自己先守。所以先拆。

### 9.2 拆法：4 个兄弟模块 + 1 个 facade

| 新模块 | 内容 | 依赖 |
|---|---|---|
| `checks/models.py` | `Severity` / `Issue` / `CheckMeta` / `CheckResult` / `Rule` | **无包内依赖** |
| `checks/exemptions.py` | `Exemption` / `Suppressions` / `_NOQA_RE` / `split_target` / `rule_id_for` / `apply_exemptions` | → models |
| `checks/scan.py` | `ScanContext` / `_SKIP_DIRS` / `format_target` | → exemptions, models |
| `checks/ast_utils.py` | `dotted` / `call_target` / `annotation_idents` / `declared_fields` / `snake_tokens` / `contains_token` / `parent_map` / `enclosing_function` | 无 |
| `checks/framework.py` | **facade**：再导出以上四个 | 全部 |

**分层只向下，无环。** `Rule` Protocol 引用 `ScanContext`，用 `TYPE_CHECKING` 导入避免运行期环。

**公开导入面用 `__all__`（20 个名字，RUF022 排序）冻结。** 拆分前先跑 AST 脚本枚举全仓 `from checks.framework import ...` 的真实名字（实测 13 个被外部导入），确认没有遗漏，因此**调用方零改动** —— 12 个规则模块、`frontend.py`、`registry.py`、`__main__.py`、99 项测试一行都没改。

**结果**：`checks/` 从 2,580 行 / 18 文件 → **2,729 行 / 22 文件**，最大文件从 501 行降到 **265 行**（`__main__.py`）。多出的 149 行是 facade 的 import 与文档。

### 9.3 验证（三路，都是实测）

1. **99 项单测全过** —— `99 passed in 3.03s`
2. **门禁语义未被破坏** —— `check` 仍然 `ran 5 · passed 4 · failed 1`，`check-static` **仍然因 4 条 skip 而失败**（T-19 的 skipped 语义完好）；`check-lite` `ran 4 · passed 4 · skipped 0` 退出 0
3. **变异检查重跑** —— 13 例（含 4 例豁免行为）**13/13 通过**，规则仍然会红

`--json` 契约未变：stdout 仍是纯净单文档，`issues` 键仍恰好是 `['code','fix','message','severity','target']`。

### 9.4 两个判断

**① 变异检查不该另建 gate。** 我一度想把它落成 `scripts/check_mutations.py` 并加进 `check`。查过之后否掉了：
12 条规则在 `test_static_checks.py` 里**各有一个 `*_is_reported` 正例**，`TestRunner` 又覆盖了 `--only` / JSON / 退出码 / 崩溃处理 —— **再加一个脚本是重复**。它的真实价值是**一次性的拆分验证**，不是常驻门禁。
（附：作为独立脚本跑要 40 秒 —— 13 次解释器启动。这个成本本身就说明它不该在日常 gate 里。）

**② 一个真实的环境坑，值得记下来。**
第一次写变异检查我用 bash heredoc 喂 Python，S-11 报"没触发"。查下来是**夹具坏了**：

```
写入前（我以为）：  'try:\n    pass\nexcept:\n    pass\n'
磁盘上（实际）：    'try:/n    pass\nexcept:/n    pass\n'
```

**Git Bash 的 MSYS 路径转换把 `:` 紧跟 `\n` 的 `\` 改成了 `/`** —— 报错行直接显示 Python 收到的源码已经是 `try:/n`。
所以"裸 `except`"从来没出现在文件里，**S-11 是无辜的**。
→ 教训：**含转义的源码要用 Write 工具落成文件再跑，别用 heredoc。** 已写进 `MEMORY.md` §九。

### 9.5 门禁状态（拆分后实测）

```
check-lite → ran 4 · passed 4 · failed 0 · skipped 0    exit 0
check      → ran 5 · passed 4 · failed 1 · skipped 0    exit 1   ✗ check-static
             200 passed · ruff 全绿 · mypy strict 全绿（42 文件）
```
