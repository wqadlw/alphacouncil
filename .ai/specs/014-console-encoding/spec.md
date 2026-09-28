# Spec 014 · 门禁工具在中文控制台上无法输出（Console Encoding）

- **状态**：Active
- **目标阶段**：S0 治理收尾（约束③「agent 全程开发」的可信度基础）
- **依赖**：无（不触碰产品代码、不动 schema、不动 API）
- **依据**：
  - 宪法第一条（红线必须落在**机制**上，不能只写在文档里）
  - 宪法 0.2「从纪律到机制的四层次」—— 本条属于"③ 类型/④ 数据库"之外的**环境层**：
    判据不是"能不能移进类型或数据库"，而是"这条规则靠自觉遵守过吗"
  - 宪法第九条（单一命令入口 `scripts/dev.py` 是真实现）
  - T-19（**一道没跑成的门禁不等于通过**）—— 本条缺陷的直接后果就是 T-19 被架空
  - `.ai/regressions/README.md`（每个缺陷 → 一条记录 + 变异检查）

---

## 一、背景与现象

`scripts/dev.py` 是本项目**唯一**的质量门禁入口（宪法第九条；本机没装 `make`）。
2026-09-28 接手时实测：

```
  [PASS] e2e            playwright test (built app on Edge/Chromium)

  ran 10 · passed 10 · failed 0 · skipped 0
Traceback (most recent call last):
  File "...\scripts\dev.py", line 266, in _summarise
    _say("\n\u2713 every gate that ran, passed")
  File "...\scripts\dev.py", line 172, in _say
    print(message, flush=True)
UnicodeEncodeError: 'gbk' codec can't encode character '\u2713' in position 2: illegal multibyte bytes
Exited with code 1
```

**十道门禁全过，工具报失败。** 退出码来自未捕获异常，不是来自门禁结论。

### 根因（已实测，不是推断）

本机 `sys.stdout.encoding == 'gbk'`（中文 Windows 默认 cp936）。逐字符实测：

| 字符 | 写入 GBK stdout |
|---|---|
| `✓` U+2713 | **UnicodeEncodeError** |
| `✗` U+2717 | **UnicodeEncodeError** |
| `⚠` U+26A0 | **UnicodeEncodeError** |
| `→` U+2192 | 正常 |
| `·` U+00B7 | 正常 |

`sys.stdout` 默认 `errors='strict'`（`sys.stderr` 才是 `backslashreplace`），
所以这三个字符在一个**只增不改的"检查输出"**里恰好是致命的。

### 波及范围：三个工具，两种症状

| 工具 | 输出流 | 症状 | 级别 |
|---|---|---|---|
| `scripts/dev.py` | stdout | **崩溃 + 退出码错误** | P1 |
| `scripts/check_licenses.py` | stdout | **崩溃（潜伏）** —— `✗`/`⚠` 只在 FAIL / copyleft 分支，而当前 `ok=42 fail=0` 无 copyleft | P1 潜伏 |
| `checks/__main__.py` | stderr | 不崩（`backslashreplace`），但 PASS 标记渲染成**字面量 `\u2713`** | P2 |

实测证据（`PYTHONIOENCODING=gbk`）：

```
$ python -m checks --strict
  ran 12 · skipped 0 · crashed 0 · findings 18 (0 error, 0 warning, 18 info)
  \u2713 PASSED            ← 字面量反斜杠，不是对勾；exit=0
```

> **`check_licenses.py` 那条潜伏缺陷最值得记**：这个工具存在的唯一目的，是在你
> 引入了一个许可证有问题的依赖时告诉你。**它恰好会在那一刻崩溃**，
> 报出一个 `UnicodeEncodeError` 而不是那个许可证问题。

### 为什么此前没被发现

`status.md` §三 写「`make check` ✅ 已可执行，且已全绿 · **退出码 0**」。
那句话只在 **UTF-8 环境**下为真（Git Bash / CI）。本机的 PowerShell 与
Windows Terminal 默认 cp936 —— 也就是**这个项目自己的开发机**。
一个只在 CI 里被验证过的本地工具，本地从未被验证。

---

## 二、设计

### 2.1 机制：进程启动时把**自己的**输出流改成 UTF-8

单点实现 `backend/scripts/_console.py::use_utf8()`，三个工具各自在 `main()` 第一行调用。

```python
def use_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        _reconfigure(stream)
```

- `encoding="utf-8"` —— 保住 `✓`/`✗`/`⚠` 的**区分度**。
  退路 `errors="replace"` 会把它们变成 `?`，而 `checks` 已经在用 `?`，
  于是 PASSED 与 FAILED 会渲染成同一个字符（实测确认过这一点，不是担心）。
- `errors="replace"` —— 兜底：将来出现连 UTF-8 都写不出的字符时降级成 `?`，
  而不是让一个**检查工具**因为装饰字符崩掉。
- **同时改 stderr**：否则 `checks` 仍会打印字面量 `\u2713`（P2 那条）。

### 2.2 为什么允许静默

`_reconfigure` 吞掉 `AttributeError` / `ValueError` / `OSError` /
`io.UnsupportedOperation`，这与"错误必须显式"并不冲突，因为：

1. 门禁的结论由**退出码**承载，不由能否画出对勾承载；
2. 真实的失败模式必须保持"崩溃"吗？不 —— 让门禁工具因为**装饰字符**崩掉，
   是比画不出对勾更坏的结果（它会把"全绿"报成"失败"，正是本缺陷本身）。

三种必须容忍的真实情况：

| 情况 | 为什么会出现 |
|---|---|
| `sys.stdout is None` | `pythonw.exe` 无控制台 —— **本项目是 pywebview 桌面程序**，这是将来真的会走到的路径 |
| 流没有 `reconfigure` | pytest 的 capture 对象、某些 IDE 包装流 |
| 流已关闭 | `ValueError` |

### 2.3 落点

| 文件 | 改动 |
|---|---|
| `backend/scripts/_console.py` | **新增**，唯一实现 |
| `backend/scripts/dev.py` | `main()` 首行调用 |
| `backend/scripts/check_licenses.py` | `main()` 首行调用 |
| `backend/checks/__main__.py` | `main()` 首行调用（`sys.path` 加 `scripts/`，原因写进注释） |

> **`_console.py` 为什么放 `scripts/` 而不是 `checks/`**：`checks/` 的包文档写的是
> "static checks for the defects tests structurally cannot catch" —— 把通用控制台
> 工具塞进去是范畴错误。而 `scripts/` 下两个工具 `python scripts/x.py` 运行时
> `sys.path[0]` 就是 `scripts/`，`import _console` **零配置**可用；
> 三个调用方里只有 `checks` 需要一行 `sys.path`。

---

## 三、验收标准

- **AC-1（机制）**：非 UTF-8 stdout 下写入 `✓`/`✗`/`⚠` **不抛异常**，且落盘字节是 UTF-8。
- **AC-2（缺陷本身）**：GBK 控制台下 `dev._summarise` 对**全绿**结果返回 **0**（不是崩溃）。
- **AC-3（潜伏兄弟）**：GBK 控制台下 `check_licenses.main()` 返回 0 且正常输出。
- **AC-4（P2 症状）**：GBK **stderr** 下 `checks._write_human` 的 PASS 标记是真 `✓`，
  **不是**字面量 `\u2713`。
- **AC-5（健壮）**：`sys.stdout = None`、无 `reconfigure` 的流、重复调用 —— 都不抛。
- **AC-6（回归记录）**：`.ai/regressions/0004-console-encoding.md` + `index.md` 登记。
- **AC-7（变异检查）**：把 `use_utf8()` 改成空操作，AC-1/2/3/4 **必须变红**，
  且**先确认变异真的生效**（有过假绿教训，见 `0003` 末尾的操作失误记录）。
- **AC-8（门禁）**：`dev.py check` 10 道全过，**且退出码为 0**（本条是 AC-2 的实机版）。

---

## 四、明确不做

| 不做 | 为什么 |
|---|---|
| 把 `✓`/`✗` 换成 ASCII | 能躲开崩溃，但换不来 `checks` 的 P2，且**下次有人加个 emoji 会再崩一次**。修机制不修字符。 |
| 只改 `dev.py` | 三个工具同根因；只改一个等于把同一个 bug 留两份。 |
| 把 `scripts/` 加进 mypy `files` | 真实缺口（`scripts/` 当前**完全不被类型检查**），但那是独立的一件事，混进来会让本 spec 的 AC 变得不可验证。**已登记进 `status.md` §五。** |
| 新增静态检查 S-13「工具必须调用 `use_utf8`」 | 宪法 2.2 三问：具体故障=？既有机制为何不行=？必需还是可选=？本条已由 AC-1~AC-4 的**行为测试**覆盖，加规则是重复。 |
| 清理 `docs/ARCHITECTURE.md` 等文档 | 属 spec 015（文档与残留清理），不与代码修复混在一处。 |
