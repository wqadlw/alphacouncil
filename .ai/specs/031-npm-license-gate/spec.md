# spec 031 —— 让 209 个还没被门禁看过一眼的 npm 包进门禁

> 状态：**已实现** · 2026-09-29
> 相关：ADR-0024（L-06 许可扫描）· `.ai/error-codes.md` · 门禁第 6 步
> 上一篇：spec 030（教训转卡）—— 那是「经验」线，本篇是**护栏**线，两条线互不依赖

---

## 一、门禁已经在承诺一件它没有做的事

`constitution.md` 的 L-06 与 ADR-0024 都写着「依赖许可扫描」，门禁第 6 步也确实在跑
`scripts/check_licenses.py`，退出码也确实拦得住东西。

但那个脚本第 115 行是：

```python
for dist in distributions():
```

`importlib.metadata.distributions()` **只枚举 Python 包**。

前端有 **209 个 npm 包**（含传递依赖 338 个）。⭐ **它们从来没有被门禁看过一眼。**
我手扫过一次，结论是「314 宽松 / 24 MPL-2.0（全是 lightningcss）/ 0 传染性」——
⭐ **手扫不构成护栏**：结论会过期，而过期的护栏比没有更坏，因为它让人以为有人在看。

⭐ **这件事和 `regressions/0005` 是同一类**：规范承诺过、门禁没兑现，中间靠人的记性。

---

## 二、调研（2026-09-29）

查了 npm 生态的既有做法，三条结论直接改变了设计。

### 2.1 `license-checker` 是事实标准，但它的用法提醒了一件更重要的事

社区标准做法是 `license-checker`，配合 `--failOn` / `--onlyAllow`（两者都要求 SPDX 合法的值）：

```bash
npx license-checker --production --failOn "GPL-2.0;GPL-3.0;AGPL-3.0;LGPL-2.0"
```

⭐ 里面的 **`--production` 才是重点**：`devDependencies` 里的 AGPL 不产生义务，因为构建工具、
测试运行器、linter **不会随产品发布**。我们这个项目是 Vite 打包的桌面应用，
**`dependencies` 会进产物，`devDependencies` 不会** —— 所以「随产品发布」的边界是真实存在的，
不是形式主义。

### 2.2 ⭐ 真实的坑：`OR` 表达式

调研里有一个具体案例：`jszip` 的许可证字段是

```
(MIT OR GPL-3.0-or-later)
```

朴素检测器在这里判错 —— ProGet 就把它标成了 MIT 不合规。

⭐ **为什么子串匹配在这里是错的**：`OR` 表示**你可以选一个**。你选 MIT，义务就全部结清。
一个只判断「字符串里有没有 GPL」的扫描器，会把一个**你完全可以用**的包判成传染性。

⭐ **这比「漏报」严重得多**。一个误报的护栏会怎样？**第一次被误报的人会把它关掉。**
护栏的价值不在于它从不误报，而在于它一直还在跑。

### 2.3 SPDX 是规范词汇表，但不是每个字段都符合它

`SEE LICENSE IN LICENSE.txt`、`{"type": "MIT", "url": ...}`、
`Apache-2.0 WITH LLVM-exception` 都是现实里出现的写法。所以解析必须承认「看不懂」，
而不是猜。

---

## 三、决定：不引入 `license-checker`，扩展现有的 `classify()`

调研推荐的工具是 `license-checker`，本篇**不用它**，理由三条：

1. ⭐ **词汇表只能有一个。** 项目已经手写了 Python 侧
   （`PERMISSIVE` / `WEAK_COPYLEFT` / `Verdict`）。再引入一个自带判断逻辑的扫描器，
   就有了**两个**「这算不算可以」的答案 —— 而本项目的纪律里，一个概念只能有一个家。
   ⭐ 与其绕路，不如让 `classify()` 变对，然后两边共用它。
2. 依赖纪律（ADR-0024）要求新增依赖有理由；⭐ **一个许可扫描器本身也是依赖**，
   而它的价值恰恰在于「依赖清单是可信的」。
3. 离线确定性。门禁不该依赖一次网络解析。

⭐ 结果：**`classify()` 变成一个 SPDX 表达式解析器，Python 侧和 npm 侧共用同一个判断。**
这既满足「一个教训只有一个家」，也让今天侥幸没踩到的 Python 侧一起变对。

---

## 四、⭐ SPDX 表达式：`OR` 取最宽松，`AND` 取最严格

这是本篇的核心。**判断的是表达式，不是子串。**

| 表达式 | 语义 | 判定 |
|---|---|---|
| `MIT` | 单选 | `OK` |
| `MIT OR GPL-3.0-or-later` | **你可以选一个** | ⭐ `OK`（选 MIT） |
| `MIT AND GPL-3.0-only` | **两个义务同时成立** | ⭐ `FAIL` |
| `Apache-2.0 WITH LLVM-exception` | 例外**放宽**条款 | 按 `Apache-2.0` 判定 → `OK` |
| `UNLICENSED` / 空 / `SEE LICENSE IN …` | 看不懂 | `WARN`（**不是 `OK`**） |

**为什么 `AND` 取最严格而 `OR` 取最宽松**：

- `OR` 是**授权人的选择权**。选宽松的那个，所有义务一次性结清 —— 这也是 SPDX 的定义。
- `AND` 是**叠加**。选宽松的那个**不能取消**另一个，宽松分支在 `AND` 里不构成豁免。

⭐ **`WITH` 例外按基础许可判定**，因为例外的作用是**放宽**而不是加重。
⚠️ 这是**刻意的简化**，理由写在这里：把例外当成加重条件会让 `Apache-2.0 WITH LLVM-exception`
（一个非常宽松的组合）变成误报，而**误报是这个门禁最不能犯的错**（见 §2.2）。
例外原文会**完整保留在报告里**，所以真有一条例外有问题时，人能看到它。

⭐ **`OR` 分支的判定必须逐支进行**，不是「先看有没有宽松的」——
`MIT OR AGPL-3.0` 应当是 `OK`，而 `AGPL-3.0 AND MIT` 应当是 `FAIL`。
同一个「宽松 + 传染性」的组合，`OR` 和 `AND` 的答案必须不同，
⭐ **否则这个特性就没被实现，而只是看起来像实现了**（这也是变异检查要盯的那一处）。

---

## 五、「随产品发布」的边界：production 闭包

按 §2.1，`devDependencies` 不随产品发布。但**传递依赖**会让人搞错边界：
一个只在 `devDependencies` 里的包，它的**传递依赖也不发布**。

所以要算 **production 闭包**而不是「顶层依赖」：

```
package.json 的 dependencies
  → 读 node_modules/<name>/package.json
    → 读它的 dependencies
      → 递归
```

Node 的扁平 `node_modules` 布局让查表变成三行代码；遇到版本冲突时向下找嵌套的
`node_modules`，找不到就记一条 `WARN`。⭐ **解析不到的包必须显式报出来** ——
⭐ 一个静默丢弃的扫描器会退化成仪式：数字好看，而漏掉的东西没人知道。

报告里两个数字分开打：

```
production closure: 214 packages   ok=214
dev only:           124 packages   ok=120 warn=4
```

门禁**只对 production 闭包里的 `FAIL` 返回 1**。

---

## 六、报告与退出码

沿用现有的形状，新增的只有行数，不改既有格式：

```
scanned 338 packages (214 in the production closure)

  FAIL  some-copyleft-pkg 1.2.3  ->  GPL-3.0-only
  warn  unclear-licence 0.0.1  ->  SEE LICENSE IN LICENSE.txt
  ok=212  warn=2  fail=0
```

---

## 七、验收

1. `classify("(MIT OR GPL-3.0-or-later)")` 是 `OK`，`("(MIT AND GPL-3.0-only)")` 是 `FAIL`
   —— ⭐ **同一个组合，两个答案**，这一条是本篇的核心断言
2. npm 侧扫描到的包数 ≥ 209（否则说明漏扫了）
3. `devDependencies` 里的 `FAIL` **不**让门禁失败，但**出现在报告里**
4. 现有 Python 侧结论不变（没有回归）
5. 造一个假的 `node_modules` 树，能让 production 闭包与顶层依赖产生差异

---

## 八、明确不做

- **不做**解析器生成、license header 校验、NOTICE 汇总 —— 那是分发义务，本项目不发布
- **不做**「把 npm 包列进 `requirements.txt`」—— ⭐ 门禁扫的是磁盘上真实安装的东西，
  不是某个声称的清单；⭐ **声称的清单正是可以骗过扫描器的东西**
- **不改** constitution / ADR-0024 —— 本篇是让门禁**兑现**已有承诺，不是新增承诺
