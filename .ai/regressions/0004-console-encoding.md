# 0004 · 质量门禁在中文控制台上无法输出，全绿也退出 1

- **发现日期**：2026-09-28
- **严重级别**：P1
- **状态**：已修复
- **发现方式**：接手时先跑一次全量门禁。输出是 `ran 10 · passed 10 · failed 0`，
  紧接着一条 `UnicodeEncodeError` 栈，退出码 1。**门禁说全过，工具说失败。**
- **对应规格**：`.ai/specs/014-console-encoding/`

---

## 现象

```
  [PASS] e2e            playwright test (built app on Edge/Chromium)

  ran 10 · passed 10 · failed 0 · skipped 0
Traceback (most recent call last):
  File "...\scripts\dev.py", line 266, in _summarise
    _say("\n✓ every gate that ran, passed")
  File "...\scripts\dev.py", line 172, in _say
    print(message, flush=True)
UnicodeEncodeError: 'gbk' codec can't encode character '✓' in position 2: illegal multibyte sequence
Exited with code 1
```

注意崩溃点在**汇总的最后一行**：`ran 10 · passed 10` 已经打印出来了。
所以这不是"门禁没过"，是**门禁过了之后，报告结论的那一行画不出来**。

失败路径同样崩（`✗ FAILED — lint`），也就是说**这个工具从来没有正确报告过一次失败**。

## 根因

本机 `sys.stdout.encoding == 'gbk'`（中文 Windows 默认 cp936）。
逐字符实测（`PYTHONIOENCODING=gbk` 强制复现）：

| 字符 | 写入 GBK 流 |
|---|---|
| `✓` U+2713 | `UnicodeEncodeError` |
| `✗` U+2717 | `UnicodeEncodeError` |
| `⚠` U+26A0 | `UnicodeEncodeError` |
| `→` U+2192 | 正常 |
| `·` U+00B7 | 正常 |

`sys.stdout` 的 `errors` 默认是 `strict`（`sys.stderr` 才是 `backslashreplace`），
所以这三个"判定标记"在一个只增不改的检查输出里恰好是致命的。

### 波及三个工具，两种症状

| 工具 | 输出流 | 症状 |
|---|---|---|
| `scripts/dev.py` | stdout | **崩溃 + 退出码错误** |
| `scripts/check_licenses.py` | stdout | **崩溃（潜伏）** |
| `checks/__main__.py` | stderr | 不崩，但 PASS 标记变成**字面量 `\u2713`** |

`checks` 的症状实测：

```
$ PYTHONIOENCODING=gbk python -m checks --strict
  ran 12 · skipped 0 · crashed 0 · findings 18 (0 error, 0 warning, 18 info)
  \u2713 PASSED            ← 六个字面字符，不是对勾；exit=0
```

> **`check_licenses.py` 那条潜伏缺陷最值得记**：这个工具存在的唯一目的，是在你
> 引入了一个许可证有问题的依赖时告诉你。`✗` 与 `⚠` 只在 FAIL / copyleft 分支打印，
> 而发现当天是 `ok=42 fail=0` 且无 copyleft —— 所以它**恰好会在最该说话的时候崩掉**，
> 报出一个 `UnicodeEncodeError` 而不是那个许可证问题。

## 为什么此前三个月没被发现

`status.md` §三 写的是「`make check` ✅ 已可执行，且已全绿 · **退出码 0**」。

那句话**只在 UTF-8 环境成立**（Git Bash / CI）。本机的 PowerShell 与 Windows
Terminal 默认 cp936 —— 也就是**这个项目自己的开发机**。
换句话说：一个"全绿退出 0"的结论，是在**没有跑过本地门禁的 CI** 里得到的。

这与 `0002`（`constraints.json` 从未被任何程序解析过）是同一类：
**不是写错了，而是从来没有人在这台机器上看它跑。**

## 修复

新增唯一实现 `backend/scripts/_console.py::use_utf8()`（`:50`），
在三个工具的 `main()` 第一行调用：

| 位置 | 行 |
|---|---|
| `backend/scripts/dev.py` | `:316` |
| `backend/scripts/check_licenses.py` | `:138` |
| `backend/checks/__main__.py` | `:60`（`:45` 有一行显式 `sys.path` 桥接，原因写在注释里） |

做法是 `stream.reconfigure(encoding="utf-8", errors="replace")`，
**同时改 stdout 和 stderr** —— 后者不是多余的：`checks` 写 stderr，
不改它就仍然打印字面量 `\u2713`。

`errors="replace"` 是兜底：UTF-8 能编码这三个工具用到的全部字符，
这个标志正常永不触发；它的意义是"将来真出现编不出来的字符时，
**检查工具降级成问号，而不是死掉**"。

### 为什么这里允许静默吞异常

`_console.py:62` 的 `_reconfigure` 吞掉 `ValueError` / `OSError`。
这与"错误必须显式"不冲突：门禁的结论由**退出码**承载，不由能否画出对勾承载。
一个因为画不出标记而拒绝运行的工具，严格地比"能跑但画成问号"更坏 ——
**它就是本缺陷本身，只是换了一顶帽子**。

三种必须容忍的真实情况（都写在 docstring 里）：

| 情况 | 为什么会出现 |
|---|---|
| `sys.stdout is None` | `pythonw.exe` 无控制台 —— **本项目是 pywebview 桌面程序**，这条路迟早会走到 |
| 流没有 `reconfigure` | pytest 的 capture 对象、部分 IDE 包装流 |
| 流已关闭 | `reconfigure` 抛 `ValueError` |

### 顺带修掉的一个同类陷阱

`checks/__main__.py` 有一段**注释里含字面量 `# noqa`** 的话。
ruff 会把它当成真的抑制指令：**每次 lint 都告警，并且静默豁免那一行**。
已改写措辞不再出现该字面量。属同一类问题（工具输出在骗人），
且就在本次改动的文件里，一并修掉并记在这里。

## 回归测试

`backend/tests/unit/test_console_encoding.py`（14 项）

| 用例组 | 挡什么 |
|---|---|
| `TestThePremiseIsReal`（2） | **钉住前提本身**：GBK 写 `✓` 必须抛异常。防止将来有人把这条当成"已过时"顺手清掉 |
| `TestUseUtf8`（6） | 三个标记在 GBK 流上都写得出且字节是 UTF-8；stderr 同样处理；`None` 流 / 无 `reconfigure` / 已关闭 / 重复调用都不抛 |
| `TestTheLicenceGate`（2） | **把潜伏分支造出来**（monkeypatch `scan` 返回一个 GPL finding），断言 `✗` 被打印且返回 1 |
| `TestTheRealProcess`（3） | **真进程 + 真控制台**：`PYTHONIOENCODING=gbk` 下跑 `dev.py check-static` / `checks --strict` / `check_licenses.py`，断言退出码与字节 |

两个设计要点：

1. **GBK 环境是伪造的**（`TextIOWrapper(BytesIO(), encoding="gbk", errors="strict")`），
   所以这些测试在 **UTF-8 的 CI 上照样会红** —— 否则它们只是"这台机器的测试"，
   CI 拿它没办法。
2. **工具契约测试绝不自己调 `use_utf8()`**。第一版我在测试里调了，结果
   `check_licenses` 那条**假绿**了 —— 测试自己把修复应用了一遍，
   于是工具调不调它都通过。改成只调工具的 `main()` / 真进程入口后，
   三条如期变红。**这条写在这里，因为它是本项目最容易犯的测试错误。**

## 变异检查（⚠️ 必填）

把 `use_utf8()` 的函数体替换为 `return`（调用点保留），跑本文件：

| 改坏哪里 | 结果 |
|---|---|
| `use_utf8()` 变成空操作 | **7 failed / 7 passed** |

变红的 7 条（逐条列出，因为"哪几条没红"和"哪几条红了"同样重要）：

```
TestUseUtf8::test_a_tick_survives_a_gbk_stream
TestUseUtf8::test_every_verdict_marker_survives
TestUseUtf8::test_stderr_is_reconfigured_too
TestUseUtf8::test_calling_it_twice_is_harmless
TestTheLicenceGate::test_a_copyleft_finding_is_reported_rather_than_crashing
TestTheRealProcess::test_the_static_checks_exit_zero_and_print_a_real_tick
TestTheRealProcess::test_the_gate_runner_reports_success_instead_of_crashing
```

**没变红的 7 条是应该不变的**：`TestThePremiseIsReal` 断言的是 GBK 的性质，
与本项目代码无关；三条"必须容忍"用例断言的是"不抛异常"，空操作当然也不抛。

## 顺带记录：变异检查的恢复**又**失败了一次

`.ai/regressions/0003` 记过一次"用 `cp` 恢复、没校验，恢复其实没生效"。
本次**按纪律做了 SHA-256 校验，于是真的抓到了** —— 但抓到的不是"没恢复"，
是另一种：

```
before mutation : 4eea00e9…
after  mutation : 9509418f…
mutated run     : 7 failed, 7 passed
after restore   : ff67bd4b…      ← 与 before 不一致
RESTORE VERIFIED: False
```

根因：恢复脚本用了 `Path.write_text()`，而它在 Windows 上**默认把 `\n` 翻译成 `\r\n`**。
本仓库工作区是 **LF**（没有 `.gitattributes`，`git` 一直在告警
"LF will be replaced by CRLF"），所以恢复出来的文件每个字节都变了。

也就是说：**SHA-256 校验本身救了这次场**。若只按 `0003` 的教训去做"校验哈希"，
而不知道校验会因换行而失败，就会误判成"恢复失败、代码被改坏"，
进而去排查一个并不存在的代码问题。

修法：`read_text` / `write_text` 都加 `newline=""`，让换行原样进出。
第二次跑：`RESTORE VERIFIED: True`，文件仍为 LF（`CRLF: 0`）。

> 纪律补一条（已并入 `.ai/regressions/README.md`）：
> **校验哈希之前，先确认"文件本来就该是哪种换行"。**

> ⚠️ 旁证：工作区根目录那个遗留脚本 `_k2_append_rule.py` 的 docstring 写着
> "CRLF preserved"，并且显式设了 `NL = "\r\n"` —— **前任也踩过这一类**，
> 只是当时是在另一个方向上撞到的。

## 是否可被测试固化？

✅ 可以（编码行为是运行时事实，可在任意机器上用伪造流复现）。

## 遗留

- **`scripts/` 仍然不被 mypy 检查。** `pyproject.toml` 的 `files` 是
  `["src","tests","checks"]`。本次只加了 `mypy_path = ["scripts"]` 让测试能
  `import check_licenses`，**没有**把 `scripts/` 纳入类型检查。
  已登记进 `status.md` §五。
- **没有仓库没有 `.gitattributes`。** 换行靠 `core.autocrlf` 兜，
  每次 `git` 都告警。这不是本次引入的，但它是上面那次恢复失败的**共同前提**。
- **未验证：真实交互式控制台下的渲染。** 本次全部通过管道观察，
  管道里看到的是 UTF-8 字节（测试已断言），而 PowerShell 用 OEM 码页解码
  会显示成 `?`。CPython 在真实控制台句柄上走 `WriteConsoleW`，
  按 stdlib 行为应当正常显示对勾 —— **但这一点没有在交互式控制台里亲眼确认过**。
- **未验证：装成 exe 之后（`pythonw.exe`，无控制台）的行为。**
  `_reconfigure` 的 `None` 分支已有测试，但那是伪造的 `None`，
  不是真的 `pythonw.exe` 启动。留到 S5 实测。
