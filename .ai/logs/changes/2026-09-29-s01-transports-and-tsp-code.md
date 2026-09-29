# 2026-09-29 · 读 TSP 的代码，拿到第二份矩阵；顺手照出一个 P0 规则的盲区（spec 042）

> 起因：主人说「好好细致调研，先把代码摸清楚，看 GitHub 有没有最佳实践，
> 再出计划，一步一步推进，企业级落地」。主人说了「可以」，两个裁决按 `plan.md` 的倾向走。
> 执行：OpenCode（Codex）· 模型：Space Bunny Free
> 产出：`references/research/2026-09-29-tsp-feature-matrix.md` · `regressions/0011-*.md`

---

## 一、⭐ Phase 1：读了代码，于是上一轮那个判断被推翻了

上一轮我凭一份**数据层**矩阵说「TSP 的功能大部分不该吸收」。

⭐ 这次读了 `extensions/contracts.py`（**1361 字节**，全文）· `registry.py`（全文）·
`config.py`（全文）· `engine.py` / `monitor.py` / `scoring.py`（结构 + 关键片段），
**加上 `features.md` 全文**。

结论：**上一轮的理由是错的，而且错在机制上** ——
`services/` 65 · `strategy/` 45 · `api/` 30 · `backtest/` 17，
**215 个文件里我读过 12 个**。

## 二、⭐ 最值钱的产出不是功能清单，是四个模式

⭐ **这四条与「吸收哪个功能」完全无关，而且它们不碰任何红线。**

| 模式 | TSP 的做法 | 为什么好 |
|---|---|---|
| ⭐ **暂存区** | `BackendExtensionRegistrar` — 「A failed setup is discarded without partial registration」 | 装到一半失败的插件不留半注册状态 |
| ⭐ **freeze()** | 启动后注册表不可变，读取前未 freeze 直接抛 | 插件不能在请求期间改注册表 |
| ⭐ **版本双检** | 扩展 + 每个实现各查一次 `api_version` | 版本不符在**注册时**发现 |
| ⭐ **稳定兜底排序** | `sort(key=(order, implementation_id))` | `order` 相同时顺序仍然确定 |

⭐ 而 `checks/registry.py` 是**手写**的（spec 015–017）——
⭐ **所以「手写版与上游版」现在第一次有了可比较的两份实现。**

⭐ **另一个直接可吸收的**：`scoring_dependencies()` + `scoring_warmup_bars()`
——「这个判据需要哪些列 / 需要多少预热」**算出来**，
而 spec 040 的 `period` 是**手写**的。
⭐ 差别是可测的：`regressions/0010` 的教训正是「DEA 那个 33 要被核对」，
而依赖自报预热**让那个数字没有第二个人类可以写错**。

## 三、⭐ Phase 2：S-01 的标题比它的实现覆盖得宽

调研 `spec 041` 顺手发现的：**BaoStock 走 socket（10030），而 S-01 拦的是 httpx/requests/aiohttp/urllib3。**

⭐ 而 `notify/email.py` 的 `smtplib` **从 spec 033 就在树里**，同样没人拦。

⇒ `regressions/0011`

### ⭐ 修规则的过程中，改出了产品代码

把 `smtplib` 纳入射程后，规则在**真实代码**上报了两条 ——
`smtplib.SMTP_SSL(...)` / `smtplib.SMTP(...)` constructed in `send_email`。

⭐ **那是一年前写的、当时是绿的代码**，而它在**重试循环里内联**开启会话，
⭐ 所以「开一个会话」和「重试」是同一句话，
而全文件最微妙的第二次 `ehlo` **埋在一个重试会重新进入的分支里**。

改成 `_smtp_session(host, port, security)` 工厂：
* 规则成立，⭐ **而且规则没有为了成立而被放宽**
* 重试循环回到它该管的事
* ⭐ 第二次 `ehlo` 有了恰好一个位置

### ⭐ 而且它立刻报出了**我们自己**的一个缺陷

`urllib` 同一个包里装着解析器和客户端，而 `domain/card.py` 用前者读卡片出处。

```python
# alphacouncil/domain/card.py:29
from urllib.parse import urlparse
```

⭐ 旧规则用 `name.split(".")[0]` 匹配 ⇒ **把本项目的 provenance 代码报成出口。**
⇒ 改成**精确点分名匹配**，并加了两条分开守它的测试。

⚠️ ⭐ **而这与 ADR-0031 是同一个错误形状**：那次用**目录**代替**模块**，
这次用**顶层包**代替**具体能力**。⇒ `F-121`

## 四、⭐ 变异 13 个：两个存活，两个都是真发现

| # | 变异 | 结果 |
|---|---|---|
| 1 | 前缀匹配回来（且集合里有 `urllib`） | **SURVIVED** |
| 2 | `smtplib.SMTP` 从构造器清单删掉 | **SURVIVED** |
| 3–13 | 其余 11 条 | 全部 killed |

⭐ **存活 1 暴露的是我自己的测量错误**：要复现这个缺陷需要**同时**改两处
（集合加 `urllib` + 换回前缀匹配），⭐ **一个合取缺陷没有单点可破** ——
所以它必须由两条**分开**的测试守着。

⭐ **存活 2 是真缺口**，形状很清楚：
「工厂内的合法形态」有测试、「全树安静」有测试，
⭐ **而两者都不能发现构造器清单被清空。**
⇒ `F-122`

## 五、⭐ 读 TSP 的代码，读出了**我们自己**的第二个缺陷

`scoring.py::_ratio`：

```python
pl.when(denominator.is_not_null() & (denominator != 0)).then(num/den).otherwise(None)
```

⭐ 同时查 `is_not_null()` **和** `!= 0`，结果给 `None`。
而 `_relative` **定义在 `_ratio` 之上** —— 比值和相对值不可能各走各的。

对照我自己的 `indicators.py`：

```python
returns.append(0.0 if closes[index - 1] == 0 else math_log(...))
```

⭐ `Quote.close` 是 `ge=0.0` ⇒ **0.0 是 schema 合法的**，
而**零底数的对数收益是未定义的比值**，0.0 说的是「价格没动」。
⭐ **这正是 spec 037 §3 那句「`0` 说的是『均价是零』」，在我自己的文件里。**

改成 `None`，并把 `annualised_volatility` 与 `true_range` 加进
`test_no_indicator_never_invents_a_zero` 的名单 —— ⭐ **它此前不在那张表上，
而那张表是照着模块里的函数名写的，它被漏掉了。**

### ⭐ 而修它的过程里，我自己又犯了两次错

1. ⭐ **只挡了前收盘为 0，没挡收盘为 0** → `math.log(0.0)` 抛 ValueError。
   ⭐ 收盘为 0 时收益是 -inf，方差就是 inf —— **`inf` 和 `0.0` 一样是编造。**
2. ⭐ **`undefined` 滚动计数器连错两次**，症状是**序列被永久遮蔽**而不是报错。

第 2 条的结论是：**聪明的滚动计数就是 off-by-one 的藏身处**。
`period=20` × 320 根 = 6400 次比较，换成窗口内直算，⭐
因为**一个 bar 的错 = 一条再也不画的曲线，且没有任何东西会抛**。⇒ `F-124`

## 六、⭐ 今天我犯的两次同形状错误

| 错误 | 机制 |
|---|---|
| 从 grep 输出断定「两处除法没有守卫」，实际两处都有 | ⭐ **从 grep 下结论而不是读代码** |
| 上一轮从文件数量否掉整个功能面 | ⭐ **用间接证据代替直接阅读** |

⇒ `F-123` 是 `F-117` 的第二条

## 七、外部调研的诚实结果

| 查的 | 结果 |
|---|---|
| 网络出口白名单最佳实践 | ⭐ **一条有用**：Veracode 的 CWE-73 —— ⭐ **白名单必须写成静态分析能解析的形式**（字面量）。而 `CONSTRUCTION_SITES` 正是 `frozenset[Path]` 字面量，**这个设计本来就满足该最佳实践，现在有据可依** |
| PIT 财务数据存储最佳实践 | ⭐ **没带来新东西** —— 检索结果基本是营销内容。⭐ **宪法的 §4.4 已经是对的** |

## 八、门禁

11 步 · **11/11 · 退出码 0**

后端 unit 1071 → **1083**（+12）· S-01 测试 10 → **14** · E2E 89 · 前端 130 · ruff 0 · mypy --strict 0

⚠️ ⭐ **门禁第一次报 `[FAIL] e2e` 而实际 89 全过** —— 那是**输出经过 PowerShell 管道**造成的假红
（`npm run test:e2e` 直接重定向到文件时退出码是 0）。
⭐ **这是 `regressions/0004`「全绿也退出 1」的同一族，而且没有任何测试覆盖它** ——
因为测试和门禁自己都是直接 spawn 进程的，**只有人或 agent 用管道调用时才会出现**。
⇒ 记进 `F-125`，**本轮不修**（修法要单独评估 PowerShell 的管道语义），但**记下来**。

## 九、下一步

⭐ **Phase 3（财务数据源）等决策 1。** 我按 `plan.md` 的倾向走 **A（装 baostock）**，
理由是 B 省下的 112 MiB 里 111.65 MiB 是 pandas，⭐ 而将来做因子/回测 pandas 本来就要进来。

⭐ **决策 2 走「不撞红线的改法」** —— 红线 1 / 9 不动，
把选股引擎的问题从「哪些票会涨」换成「我写下的哪几条判据被越过了」。
