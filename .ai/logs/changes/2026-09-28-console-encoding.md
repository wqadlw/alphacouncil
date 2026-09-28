# 2026-09-28 · 控制台编码缺陷（spec 014 / 回归 0004）

> 四段式台账（宪法 10.5）。**append-only：只追加，不改写。**
> 执行者：OpenCode（Codex · Space Bunny Free）· 接手当日第一批。

---

## ① 想做什么

接手 `alphacouncil`，先跑一次全量门禁看真实状态。四处缺陷按序处理，**本条只记第一批**：

| # | 缺陷 | 级别 |
|---|---|---|
| ① | `dev.py check` 在中文控制台上永远无法报成功 | P1 → spec 014 / 0004 |
| ② | `docs/ARCHITECTURE.md` 描述的技术栈已被宪法 v2.0 全部移除 | P1 → spec 015 |
| ③ | 遗留草稿 `backend/_fsrs_probe.py` 打断 lint 门禁 | P2 → 已处理 |
| ④ | `status.md` / `HANDOFF.md` 落后于代码 | P2 → spec 015 |

先做①的理由：**"绿了"这个信号失效，其余三条的验收都不可信**。
一个每道门禁都跑、但从不返回 0 的门禁，和没有门禁是同一种东西。

动手前先做了一次不写代码的核查（花的时间比直接改多，但值）：
逐字符实测 GBK 能不能编码、`checks` 与 `dev.py` 症状为何不同、
`check_licenses` 的 `✗` 到底在不在可达分支上。

## ② 做了什么

### 核查（先证实，再改）

| 问 | 答 | 怎么证的 |
|---|---|---|
| 本机 `sys.stdout.encoding` 是什么 | `gbk` | 直接打印 |
| `✓` `✗` `⚠` 能否编码 | **全部不能** | 逐字符 `PYTHONIOENCODING=gbk` 写入 |
| `→` `·` 能否编码 | 能 | 同上（所以只有标记炸） |
| `checks` 为何不崩 | 它写 **stderr**，而 stderr 是 `backslashreplace` | 读输出流 + 读 CPython 行为 |
| `check_licenses` 的 `✗` 可达吗 | **不可达**（`ok=42 fail=0`、无 copyleft） | 读代码分支 |

### 改动

| 文件 | 改动 |
|---|---|
| `backend/scripts/_console.py` | **新增**。`use_utf8()` 唯一实现 |
| `backend/scripts/dev.py` | `:316` 调用；`:27` import |
| `backend/scripts/check_licenses.py` | `:138` 调用；`:31` import |
| `backend/checks/__main__.py` | `:60` 调用；`:45` `sys.path` 桥接 + 原因注释；`:185` 改写一处含字面量 `# noqa` 的注释 |
| `backend/pyproject.toml` | `pythonpath` 加 `scripts` · `mypy_path = ["scripts"]` · `checks/**` 加 `E402` |
| `backend/tests/unit/test_console_encoding.py` | **新增** 14 项 |
| `.ai/regressions/0004-console-encoding.md` | **新增** |
| `.ai/regressions/{index,README}.md` | 登记 + 补两条硬规则 |
| `.ai/specs/014-console-encoding/` | **新增** spec / plan / tasks |
| `backend/_fsrs_probe.py` | **删除**（未跟踪的遗留草稿，见下） |

### 关于被删掉的 `_fsrs_probe.py`

那是前任为 **K3（FSRS 队列）** 做的探针脚本，忘了删，`print` 触发 T201 → **lint 门禁红**。
它问的五个问题记在这里，K3 开工时按自己的 spec 重新做一遍探针：

1. `review_card` 会不会就地改传入的 `Card`（`input mutated?` / `same object?`）
2. 关掉 fuzzing 后同一输入的 `due` 是否确定（可复现性）
3. `Card.to_dict()` → `from_dict()` 能否无损往返
4. 朴素 `datetime`（无 tzinfo）是否被接受
5. `learning → review` 的毕业过程，以及 `Again` 对 review 态卡片的作用

**已知随 spec 013 一并记录的边界**：批量录入时同毫秒主键可能撞键（`card_<毫秒>`），
K1/K2 都记了，K3 同样沿用。

### 关于「换掉 ✓/✗」这个更省事的方案

否决了，写在 spec §四。理由：能躲开崩溃，但换不来 `checks` 那个 P2
（`\u2713` 字面量），而且**下次有人加个 emoji 会再崩一次**。
修机制，不修字符。

## ③ 得到了什么样的结果

### 修复前后，同一台机器、同一个命令

| | 修复前 | 修复后 |
|---|---|---|
| `dev.py check` | `ran 10 · passed 10 · failed 0` → 崩溃，**退出码 1** | `ran 10 · passed 10 · failed 0 · skipped 0` → **退出码 0** |
| `checks --strict`（GBK） | `\u2713 PASSED`（字面量），exit 0 | 真 `✓`，exit 0 |
| `check_licenses` copyleft 分支 | **崩溃**（潜伏） | 打印 `✗` 并返回 1 |

### 门禁（实机，不是推断）

```
  [PASS] lint           ruff check
  [PASS] typecheck      mypy (strict)
  [PASS] licenses       dependency licence scan (ADR-0024 · L-06)
  [PASS] check-static   static checks S-01..S-12 (.ai/checks/static/)
  [PASS] test           pytest tests/unit
  [PASS] frontend-typecheck tsc -b
  [PASS] frontend-lint  oxlint
  [PASS] frontend-test  vitest run
  [PASS] frontend-build vite build
  [PASS] e2e            playwright test

  ran 10 · passed 10 · failed 0 · skipped 0
=== EXITCODE=0 ===
```

- 测试总数 **514 → 528**（+14）
- `ruff` / `mypy --strict` / `pytest` / `playwright` 全绿

### 变异检查

`use_utf8()` 改成空操作 → **7 failed / 7 passed**；恢复后 SHA-256 一致。
哪 7 条红了、哪 7 条本就不该红，逐条列在 `regressions/0004`。

### 失败的项 / 需要说明的

| 项 | 状态 |
|---|---|
| 恢复脚本第一次**校验未通过** | 已修（`newline=""`），详见 ④ |
| ruff `--fix` 把我写的 `# noqa: E402` 删了 | 预期（`E402` 已进 `checks/**` 的 `per-file-ignores`，`noqa` 变冗余） |
| `ruff --fix` 有没有打乱 `checks/__main__.py` 的 `sys.path` 顺序 | **已核查**：没有，`sys.path.insert` 仍在两个 import 之前 |

## ④ 留下了什么

### 新增的机制

- **`scripts/_console.py::use_utf8()`** —— 三个工具的唯一实现，
  进程启动时把**自己的**输出流定成 UTF-8。
- **`regressions/0004`** —— 记录 + 14 项回归测试。

### 新增的两条硬规则（`regressions/README.md` §四）

| # | 规则 | 从哪来 |
|---|---|---|
| 7 | **校验恢复用的哈希之前，先确认这个文件本来就该是哪种换行** | 本次恢复**真的**被哈希校验抓住，但抓的是 LF→CRLF 而非"没恢复" |
| 8 | **测试不得自己应用它要验证的修复** | 本次第一版测试**假绿**：测试里调了 `use_utf8()` |

规则 8 我认为比规则 7 更值钱。它是本项目最容易犯的测试错误，
而且**它不产生任何红灯**。

### 变异检查恢复又失败了一次（第二次）

`0003` 记过第一次（用 `cp`、没校验、恢复没生效）。
本次按纪律做了 SHA-256 校验，**于是真的抓到了** —— 但抓的是另一种：

```
after restore : ff67bd4b…    ← 与 before 的 4eea00e9… 不一致
```

根因：`Path.write_text()` 在 Windows 上默认 `\n` → `\r\n`，而本仓库工作区是 **LF**
（无 `.gitattributes`，`git` 每次告警 "LF will be replaced by CRLF"）。
**代码内容是对的，是换行全变了。**

> **若当时不知道换行这回事，就会误判成"代码被改坏"，转去排查一个不存在的问题。**
> 所以纪律不是"多校验一次"，是"校验之前先知道自己在跟什么比"。

旁证：工作区根目录那个遗留脚本 `_k2_append_rule.py` 的 docstring 写着
"CRLF preserved" 并显式设了 `NL = "\r\n"` —— **前任也踩过这一类**，只是方向相反。

### 新登记的缺口（进 `status.md` §五）

| 项 | 状态 |
|---|---|
| ⭐ **`scripts/` 完全不被 mypy 检查** | `files = ["src","tests","checks"]`。本次只加了 `mypy_path` 让测试能 import，**没有**纳入类型检查。这三个门禁工具是"决定项目是否被验证"的那层代码，却完全无类型约束 |
| ⚠️ **仓库没有 `.gitattributes`** | 换行靠 `core.autocrlf` 兜，每次 `git` 都告警。它是上面那次恢复失败的**共同前提** |
| ⚠️ **未验证：真实交互式控制台下的渲染** | 全部通过管道观察，管道里是 UTF-8 字节（测试已断言）。CPython 在真控制台走 `WriteConsoleW`，按 stdlib 行为应正常，**但没亲眼确认** |
| ⚠️ **未验证：`pythonw.exe`（无控制台）启动** | `_reconfigure` 的 `None` 分支有测试，但那是伪造的 `None`。留到 S5 |

### 本条**没有**做的事（明确划界）

| 不做 | 为什么 |
|---|---|
| 把 `scripts/` 加进 mypy `files` | 真实缺口，但混进来会让本 spec 的 AC 不可验证。**独立一件事** |
| 新增静态检查 S-13「工具必须调 `use_utf8`」 | 宪法 2.2 三问：已被 AC-1~AC-4 的行为测试覆盖，加规则是重复 |
| 改 `status.md` / `HANDOFF.md` / `ARCHITECTURE.md` | 属缺陷②④，spec 015 |
| 推 GitHub | 网络策略（GitHub 直连被墙）另行确认后再做 |
