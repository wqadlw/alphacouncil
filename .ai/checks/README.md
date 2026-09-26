# `.ai/checks/` —— 检查子系统

> **"报告问题"不够，必须"报告问题 + 怎么修"。**
> 建立：2026-09-26 · 依据 `references/deep-dives/08-portfolio-performance.md` 决定 · `09-primitives.md` 决定 8 · `11-open-science.md`

---

## 一、为什么必须分两类

> ⭐ **"某段代码不该存在"这类缺陷，测试永远抓不住** —— 测试只能证明"跑到的路径是对的"。

| 目录 | 检查对象 | 何时跑 | 抓什么缺陷 |
|---|---|---|---|
| **`data/`** | **运行时扫库**（数据内容） | `make check-data` · 用户可手动触发 | **数据本身不一致**（缺字段 / 悬空引用 / 口径混用） |
| **`static/`** | **编译期扫代码**（源码 AST） | `make lint` 之后、`build` 之前 | ⭐ **某段代码不该存在**（裸 HTTP / 布尔状态 / 预测字段） |

**两者不可互相替代。**

---

## 二、统一契约

**所有检查必须返回统一诊断信封**（见 `.ai/error-codes.md` 第一节）：

```json
{
  "severity": "error",
  "code": "CHECK_DANGLING_REFERENCE",
  "message": "决策 #1042 引用的标的 (SH, 600519) 不存在",
  "target": "decisions:1042",
  "fix": null
}
```

### 2.1 `Issue` 的形状（借 portfolio-performance）

```python
@dataclass(frozen=True)
class Issue:
    date: date | None
    entity: str              # 出问题的对象（"decisions:1042"）
    amount: Decimal | None
    label: str               # 给人读的一句话
    available_fixes: list[Fix]   # ⚠️ 可以为空
```

### 2.2 ⭐ `available_fixes` 可以为空（诚实）

**不是所有问题都能自动修。** 允许返回空列表 —— **假装能修比不能修更糟**。

| `Fix.kind` | 含义 | 谁执行 |
|---|---|---|
| `AUTO` | 可自动修复 | 程序 |
| ⭐ `MANUAL` | **只能人做** | **用户**（写决策 / 打分 / 改理由 → **必须是 `MANUAL`**） |
| `SUGGEST` | 给出建议命令，由人确认后执行 | 用户 |

> ⚠️ **凡涉及"用户必须亲手做"的操作，`fix.kind` 必须是 `MANUAL`** —— 否则就绕过了红线 13（索取在先）。

---

## 三、运行方式

```bash
python scripts/dev.py check          # 全部门禁（lint + typecheck + licenses + check-static + test）
python -m checks                     # 只跑 static/（编译期扫代码）
python -m checks --strict            # 同上，但有问题就退出 1（门禁用这个）
python scripts/dev.py check-data     # 只跑 data/（运行时扫库）
python scripts/dev.py check-data-fix # 尝试自动修复（只做 AUTO 类）
```

> ⚠️ **本机没装 `make`**（2026-09-26 实测）—— 上面这些是真实现。
> `Makefile` 只是薄包装，且**它引用的目标在未装 make 的机器上从未被执行过**。
> 宪法第九条"一切命令走 `make`"已修正为"一切命令走 `scripts/dev.py`"。

**退出码**（见 `.ai/error-codes.md` 第三节）：

| 码 | 含义 |
|---|---|
| `0` | **执行成功** —— ⚠️ **"发现健康问题"仍然是 0** |
| `1` | 执行失败 |
| `130` | 用户取消 |

**⚠️ 注意**：`0` 只表示"跑完了"。**是否通过要看输出里的汇总行**（含 `发现 N 个问题`）。
门禁需要"通过/不通过"这个信号，所以静态检查另有一个 **`--strict`** 开关：**有 error 或有规则没跑 → 退出 1**。
它是 opt-in 的，只有 `scripts/dev.py` 使用 —— **改行为要显式要求，不偷偷改契约**。

---

## 四、CI 位置

```
Lint  →  Typecheck  →  check-static  →  Test  →  Build
                        ↑ 早失败：不用等测试跑完
```

**理由**：`static/` 检查是秒级的，**放在测试之前能最早退出**。

---

## 五、维护规则

1. **每个新检查必须回答**：① 它抓的缺陷**具体是什么** ② 为什么**测试抓不住**（否则它应该是一个测试）。
2. **每个检查必须有自己的测试** —— 用一个 fixture 数据/代码，**确认它会报错**。
3. **`data/` 检查必须能处理"空数据库"** —— 新用户第一次打开时不能报错。
4. **`static/` 脚本头部必须写明三件事**（见 `static/README.md`）。

---

*本目录与 `.ai/error-codes.md` 同步维护。*
