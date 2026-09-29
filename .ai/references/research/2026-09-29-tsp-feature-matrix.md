# TSP 功能面能力矩阵（第二份）

> 日期：2026-09-29 · **这份矩阵替代的是「我读过 features.md 就否掉了全部」那个判断**
> 第一份仍在 `2026-09-29-tsp-capability-matrix.md`，它关于**数据层**的部分仍然准确
> ⭐ **两份都要留着**：删掉第一份会丢掉数据层的实测，而它的失误是**没有覆盖功能面**。

## 一、⭐ 这份矩阵的证据基础，以及它的短板

| | 覆盖 |
|---|---|
| `docs/features.md` 全文（209 行） | ✅ |
| `extensions/{contracts,registry,loader}.py` | ✅ **逐行读完**（3.9 KB） |
| `strategy/{config,scoring,engine,monitor}.py` | ✅ **结构**（类与函数签名 + 关键片段） |
| `strategy/builtin/*` 45 个 | ⚠️ **只看文件名与体量** |
| `services/*` 65 个 | ❌ **只看文件名与体量** |
| `backtest/` 17 个 | ❌ 未看 |

⭐ **所以这是一份「边界已读、实现未读」的矩阵。** 它足以判断**架构**可不可吸收，
不足以判断**实现**质量。凡是依赖实现细节的结论，下面都标了「未验证」。

---

## 二、⭐ 四个可以直接吸收的**模式**（与功能无关）

这一节是这一轮最值钱的产出，因为它们**不碰任何红线**。

### 2.1 扩展注册表：staging + freeze + 版本双检

`extensions/registry.py` 134 行，四件事：

```python
class BackendExtensionRegistrar:      # 暂存区
    """Staging area: a failed setup is discarded without partial registration."""

class BackendExtensionRegistry:
    def register(self, registrar):    # 先全量校验，再改注册表
    def freeze(self):                 # 启动后不可变
        if not self._frozen: raise RuntimeError("must be frozen before use")
```

| 模式 | 为什么好 | AlphaCouncil 有没有 |
|---|---|---|
| ⭐ **暂存区**：全部校验通过才提交 | 一个装到一半失败的插件不会留下半注册状态 | ❌ |
| ⭐ **`freeze()` 后读取即抛** | 插件不能在请求期间改注册表 | ⚠️ `checks/registry.py` 是模块级的，没有 freeze |
| ⭐ **API 版本双检**（扩展 + 每个实现） | 版本不符在**注册时**发现，不是调用时 | ❌ |
| ⭐ **重复检测同时看已注册与暂存** | 同一扩展内部的重名也能抓到 | 未验证 |
| ⭐ **`sort(key=(order, id))`** | `order` 相同时的**稳定兜底**，避免启动顺序不确定 | 未验证 |

⭐ **这五条与「吸收哪个功能」完全无关，而它们是这一轮最值得拿走的东西。**
`checks/registry.py` 与 `extensions/registry.py` 是同一个问题的两份答案，
⭐ 而 `checks/` 那份是**手写**的（spec 015–017）—— ⭐ **所以「手写版与上游版谁更好」这个问题，
现在第一次有了可比较的两份实现。**

### 2.2 判据的「依赖 + 预热」两个函数 ⭐ 直接可吸收

`strategy/scoring.py`：

```python
def scoring_dependencies(scoring) -> set[str]:   # 这个判据需要哪些列
def scoring_warmup_bars(scoring) -> int:          # 这个判据需要多少预热
```

⭐ **这两个函数就是 `metrics.py` 缺的那一半。**

spec 040 的目录是「名字 → 函数 + 一个手写的 `period`」。
而 `scoring_warmup_bars` 是**算出来的**：遍历判据用到的每个因子，
取各自 `warmup_bars` 的最大值。

⭐ 差别是可测的：spec 040 里 MACD 的 DEA 我手写了 `34`（= 26+9-1），
⭐ **而 `regressions/0010` 的教训正是「这个数字要被核对」**。
TSP 的做法是让依赖声明自己的预热，**于是那个数字没有第二个人类可以写错**。

⇒ **这是一个具体、可落地、且能修掉一类已发生缺陷的吸收项。**

### 2.3 判据状态签名

`strategy/monitor.py`：

```python
def _rule_state_signature(rule: dict) -> tuple[Any, ...]:
```

⭐ 「这条规则的内容变了没有」的签名。用途是**避免重复评估**。
spec 040 的 `/today` 现在每次请求都重算全部到期判据 —— ⭐ **而一个签名能让它跳过没变的。**

### 2.4 数据源作为可调用注入

```python
class MonitorRuleEngine:
    def set_history_loader(self, fn): ...
    def set_history_loader_etf(self, fn): ...
```

⭐ 监控引擎**不 import 数据源**，它接收一个 callable。
⇒ 形态可吸收：**判据求值器接收一个「取日线」的 callable**，
于是测试里塞 fixture、生产里塞 router，而 `criterion_eval.evaluate(bars)` 现在是**直接吃列表**，
⭐ 那个签名是本轮唯一一个**我写着就后悔了的决定**（它让调用方必须自己 fetch）。

---

## 三、功能面逐项判断

⭐ **「是否可吸收」与「以什么形态吸收」分开写** —— 因为这次的核心发现是
**很多功能换一个问法就完全不撞红线**。

| TSP 的功能 | 实现体量 | 撞什么 | 可吸收的形态 |
|---|---|---|---|
| **选股引擎** | `strategy/engine.py` 75 KB + `builtin/` 45 文件 | 🔴 **红线 1**（问「哪些票会涨」） | ⭐ **同一个引擎，把问题换成「我关注的十几只里，我写下的哪几条判据被越过了」** —— 不撞任何红线 |
| **监控中心** | `monitor.py` 81 KB + `monitor_rules.py` 24 KB | 🔴 **红线 8**（异动提醒 / 机会推送） | ⭐ **规则引擎可吸收，通知形态不可**。「一条规则 + 冷却 + 严重级」是纯逻辑；「命中就弹窗」是红线 8 |
| **指标流水线** | `indicators/` 3 文件 | ✅ 不撞 | ✅ **已吸收**（spec 037/038）⭐ 本轮发现它的 `scoring_dependencies` 仍值得吸收 |
| **盘中信号（分钟 K）** | `intraday_features.py` 7.8 KB + `intraday_signals.py` 7.5 KB | ⏸ **分钟 K 端到端未通** | ⏸ 阻塞在 `5c5f90f` |
| **9 类关键价位** | `stock_analyzer.py` 19 KB | 🔴 **红线 3** | ❌ 以市场数据为输入，不是以记录为输入 |
| **AI 四维分析** | `ai_provider.py` 41 KB | 🔴 红线 15（agent 只做抽取） | ❌ 它生成判断。⭐ 且 AlphaCouncil 的 agent 层还没启用（ADR-0027） |
| **连板梯队 / 概念轮动 / 龙虎榜 / 盘前风向标** | 4 个文件 ~50 KB | ⛔ **数据源未接** | ⛔ fuyao / ths 源一个都没有 |
| **外部推送渠道** | `webhook_adapter.py` 16.7 KB + `wecom_bot_service.py` 12 KB | ⏸ 阻塞在 S-01 | ⏸ **S-01 的架构障碍已由 ADR-0031 拆掉**（`spec 039`），可以开始 |
| **数据源插件化** | `plugins/` 6 文件 + `data_providers/` 12 文件 | ✅ 不撞 | ✅ **部分已吸收**（`Dataset` / `ProviderCapabilities` / router 已是这个形状） |
| **第三方数据接入（Tushare/CSV）** | `ext_data.py` 32 KB + `ext_pull.py` 24 KB | ⚠️ 加源要过 §4.5 | ⏸ 取决于决策 1 |
| **盘后定时管道** | `pipeline_jobs.py` 24 KB + `jobs/` 2 文件 | ⛔ **§4.5 封禁风险** | ⛔ 全市场定时拉取正是招来 IP 封禁的做法。**不做** |
| **回测引擎** | `backtest/` 17 文件 | 🔴 **红线 9** | ❌ 收益率是回测的本质，**没有不碰红线的近亲**（见 `plan.md` §三的边界说明） |
| **因子平台** | `factors/` 5 文件 | ⚠️ 无直接红线 | ⏸ 为选股找因子而存在。不做选股就没有下游 ⭐ ——**但它的「因子自报预热与依赖」可单独吸收**（见 2.2） |
| **ETF 支持** | 散布在各文件 | ✅ 不撞 | ⏸ 只是一个资产类型，没有它就缺的独立能力 |
| **市场阶段 / 主线识别** | `regime_builder.py` 31 KB + `market_mainline.py` 12 KB | 🔴 红线 8 + ⛔ 需 `limit_up` / `consecutive_limit_ups` 字段（**全库 0 个**） | ❌ 双重阻塞 |

---

## 四、⭐ 本轮从 TSP 读代码时，发现的**我们自己**的问题

这一节是「吸收」二字的另一面：⭐ **读别人的代码读出了自己的缺陷。**

### 4.1 ⭐ `annualised_volatility` 在前收盘为 0 时返回 `0.0`

```python
returns.append(0.0 if closes[index - 1] == 0 else math_log(closes[index] / closes[index - 1]))
```

而 `Quote.close` 是 `Field(ge=0.0)` ⭐ —— **0.0 是 schema 合法的**。

TSP 的写法（`scoring.py::_ratio`）：

```python
pl.when(denominator.is_not_null() & (denominator != 0)).then(num/den).otherwise(None)
```

⭐ **它在同样情况下给 `None`（没有答案），我给 `0.0`（一个答案）。**
而 spec 037 §三的原话是「`0` 说的是『均价是零』」—— ⭐ **同一个形状，我自己的文件里。**

⚠️ 真实数据到不了（A股最小价格 0.01），⭐ **但它从 schema 到达。**
⇒ 修法：改成 `None`，并把 `annualised_volatility` 加进
`test_no_indicator_ever_invents_a_zero` 的名单（⭐ 它现在不在那个名单里）。

### 4.2 ⭐ 我今天犯的两次同形状错误

| 错误 | 机制 |
|---|---|
| 上一轮用一份**数据层**矩阵否掉整个功能面 | **没读** |
| 本轮从 grep 输出断定「两处除法没有守卫」 | ⭐ **从 grep 下结论而不是读代码** —— 而实际两处都有守卫 |

⭐ 两次都是**用间接证据代替直接阅读**。⇒ `F-117` 的第二条

---

## 五、结论

1. ⭐ **4 个模式可以直接吸收**（注册表 5 条、判据自报预热/依赖、规则状态签名、数据源注入），
   **且都不碰任何红线**
2. ⭐ **1 个大功能可以在不碰红线的前提下吸收**（选股引擎换个问法）
3. ⭐ **2 个明确不做**（回测撞红线 9 且无近亲；盘后全市场定时管道撞 §4.5）
4. ⭐ **1 个真缺陷从对照中浮出来**（`annualised_volatility` 的 `0.0`）
5. ⭐ **本矩阵的实现层覆盖仍不完整**（`services/` 65 个文件未读）——
   任何关于「实现质量」的判断现在都还是猜测，⭐ **包括这一份里所有 ⬜ 未验证的格子**
