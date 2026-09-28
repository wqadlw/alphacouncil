# Plan 014 · 门禁工具的控制台编码

> ⚠️ **本文件对审查者隐藏**（`agent-guide.md` §一）。知道意图的审查者会"拿代码对照计划"，
> 而不是"判断代码对不对"。

## 一、动手前必须先证伪的三件事

1. **确认 `sys.stdout` 在本机真的是 `gbk`**，而不是我记错了 CP936 的默认值。
2. **确认 `_console.py` 真的能被 `checks/__main__.py` 导入** —— 它以 `python -m checks`
   运行，`sys.path[0]` 是 `backend/`，所以要显式把 `backend/scripts` 加进去。
   这条加错了会变成 `ImportError`，而那正好是 §2.2 说的"更坏的失败模式"。
3. **确认 `check_licenses.main()` 没有参数**（spec §三 AC-3 的前提）。

## 二、实现顺序

1. 写 `scripts/_console.py`（纯函数，无依赖，先能单测）
2. 写单测 —— **先让它们红**（此时 `dev.py` 还没调用 `use_utf8`）
3. 接三个调用方
4. 单测转绿
5. **实机复跑 `dev.py check`**，确认退出码 0（AC-8）

> 第 2 步的顺序是刻意的：先写测试再改实现，红→绿才说明测试真的在测东西。
> 如果先改实现再补测试，就无法区分"测试有效"和"测试恰好通过"。

## 三、测试怎么搭 GBK 环境

不能用真的改 `sys.stdout.encoding`（那是只读属性）。做法：

```python
stream = io.TextIOWrapper(io.BytesIO(), encoding="gbk", errors="strict")
monkeypatch.setattr(sys, "stdout", stream)
```

`BytesIO` + 显式 `encoding="gbk"` 精确复现了本机的失败条件，
而且**在 UTF-8 机器上也照样能复现** —— 这一点很重要：否则这条测试只在这台
中文机器上有效，CI（UTF-8）会静默放过它。

断言必须**写死字面量**（`regressions/README.md` 硬性规则 1）：
不 `from _console import MARKERS`，而是在测试里直接写 `"\u2713"`。

## 四、`checks/__main__.py` 的 sys.path 处理

`_write_human` 往 stderr 写。要在测试里直接调它，就必须能 import `checks.__main__`。
测试侧靠 `pyproject.toml` 已有的 `pythonpath = ["."]`（`backend/` 已在路径上）。

生产侧 `checks/__main__.py` 顶部需要：

```python
sys.path.insert(0, str(BACKEND_ROOT / "scripts"))
from _console import use_utf8   # noqa: E402
```

`BACKEND_ROOT` 已在该文件第 41 行算好。注释必须写明**为什么需要这一行**
（`python -m checks` 时 `scripts/` 不在路径上），否则下一个人会当成冗余删掉。

## 五、变异检查怎么做（AC-7）

把 `use_utf8()` 的函数体替换成 `return`，让调用点还在但不生效。
预期 AC-1/2/3/4 全红。

**并且先确认变异真的生效**：用 SHA-256 记录改前文件哈希，改完再哈希确认不同，
恢复后确认哈希回到原值。项目有过"恢复没生效"的教训（`0003`）。
