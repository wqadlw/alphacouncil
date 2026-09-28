# Tasks 014 · 门禁工具的控制台编码

## T1 · 机制
- [x] `backend/scripts/_console.py`：新增 `use_utf8()`（唯一实现）
- [x] `_reconfigure()` 容忍 `None` 流 / 无 `reconfigure` / 已关闭
- [x] 注释写明**为什么允许静默**（退出码承载结论，不由对勾承载）

## T2 · 测试（先红）
- [x] `tests/unit/test_console_encoding.py` · GBK stdout 夹具（`TextIOWrapper(BytesIO(), encoding="gbk", errors="strict")`）
- [x] AC-1 `✓`/`✗`/`⚠` 不抛异常且字节为 UTF-8
- [x] AC-2 `dev.py` 单门禁入口在 GBK 真实进程下退出 0
- [x] AC-3 `check_licenses` 的 copyleft 分支（monkeypatch `scan` 造出 FAIL）
- [x] AC-4 `checks --strict` 真进程输出真 `✓`，非字面量 `\u2713`
- [x] AC-5 `stdout=None` / 无 `reconfigure` / 已关闭 / 重复调用
- [x] 期望值全部写死字面量（`TICK = "\u2713"`，不从被测代码 import）
- [x] **确认先红**：接入前 3 failed（`check_licenses` copyleft / `checks` 子进程 / `dev.py` 子进程）

> ⚠️ **第一版测试是假绿的**：我在测试里调了 `use_utf8()`，等于自己把修复应用了一遍，
> 于是 `check_licenses` 那条通过了。改成只走工具自己的入口后如期变红。
> 已写成 `regressions/README.md` 规则 8。

## T3 · 接入三个调用方
- [x] `scripts/dev.py::main`（`:316`）
- [x] `scripts/check_licenses.py::main`（`:138`）
- [x] `checks/__main__.py::main`（`:60`，`:45` 为 `sys.path` 桥接 + 原因注释）
- [x] `pyproject.toml`：`pythonpath` 加 `scripts` · `mypy_path = ["scripts"]` · `checks/**` 加 `E402`
- [x] 测试转绿（14 passed）

## T4 · 变异检查
- [x] `use_utf8()` 改成空操作
- [x] 确认 **7 / 14 变红**（逐条列在 `regressions/0004`）
- [x] SHA-256 校验改前/改后/恢复后三态
- [x] 第一次恢复**校验未通过**（`write_text` 把 LF 写成 CRLF）→ 加 `newline=""` 后 `RESTORE VERIFIED: True`
- [x] 临时脚本用完即删，不留 `.bak`

## T5 · 回归记录与台账
- [x] `.ai/regressions/0004-console-encoding.md`
- [x] `.ai/regressions/index.md` 登记 0004 + 第 5 轮变异检查
- [x] `.ai/regressions/README.md` 补规则 7 / 规则 8 + §五 状态表
- [x] 四段式变更日志 `.ai/logs/changes/2026-09-28-console-encoding.md`
- [x] `status.md` 同步（含 `scripts/` 未纳入 mypy 的新登记）
- [x] 实机 `dev.py check` 10 道全过**且退出码 0**（AC-8）
