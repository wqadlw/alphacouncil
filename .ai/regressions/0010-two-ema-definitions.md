# 回归 0010 · 同一个文件里有两个 EMA 定义，而文档描述的是第三个

**发现**：2026-09-29，spec 038（指标上屏）—— ⭐ **不是被测试抓到的，是被「数真实响应里的
非空值」抓到的**
**状态**：已修 · 根因已定位 · 代码、文档、测试三处已一致

---

## 一、现象

spec 038 把指标接到页面上，第一件事是拿真实响应数一遍每条序列的非空值：

```
dif  warmup=25
dea  warmup=25      ← 应该 33
```

而 `macd()` 的 docstring 写着：

> ⭐ The signal (DEA) is an EMA of DIF, so it inherits `ema`'s recursive seeding — and
> it is aligned back to the input, meaning its first `signal - 1`` entries are `None`
> **on top of whatever MACD's own warm-up already leaves empty.**

**三个东西，三个说法。**

| | DEA 怎么播种 | DEA 预热 |
|---|---|---|
| docstring 说 | 继承 `ema` | 25 + 8 = **33** |
| `ema()` 实际 | 前 `period` 个值的 **SMA** | — |
| `macd()` 实际 | **第一个值** | **25** |

## 二、为什么 34 条测试全绿

因为**没有任何一条断言 DEA 的预热长度**。

`TestMaturityIsTheConstitution` 有一个参数化表，逐条钉死每个指标的预热段：

```python
(lambda values: sma(values, 20), 19),
(lambda values: ema(values, 20), 19),
(lambda values: rma(values, 20), 19),
(lambda values: macd(values).dif, 25),
(lambda values: rsi(values, 14).rsi, 14),          # ← dea 不在表里
...
```

`dif` 在，`dea` **不在**。

⭐ 而 `test_no_indicator_ever_invents_a_zero` 里 `dea` **是**在的。
一个在场一个不在场，说明写测试的时候知道 `dea` 归一化不出 33，
于是没往参数表里放 —— ⭐ **表沉默，文档继续说 33，而代码继续给 25。**

三处本该一致的地方，只有代码和「表没写」一致。

## 三、根因

⭐ **「一个教训只有一个家」在同一个文件里破掉，是最难看见的一种。**

`ema` 和 `dea` 的递归都是 EMA。写在同一个文件里、都在 `macd` 附近、
都短到能一眼读完 —— **两个定义看起来都局部、都合理、都像是这个函数的一部分。**
「一个家」的规则通常防的是跨文件复制；这里没有复制，是**同一份文件里的两次实现**。

具体的分叉是**播种**：`ema` 用前 `period` 个值的 SMA（`sum(seed)/period`），
手写的 `dea` 用第一个值。⭐ 这在 EMA 里不是细节 —— 播种决定了第 0 根到第 `period-1` 根
的每一个数，也决定了此后所有根的起点。

而 spec 037 的分叉表（6 行：EMA / RSI / KDJ / ATR / 布林 / 年化波动）
**根本没有这一行**。⭐ 播种方式是这个文件里真实存在的第 7 个分叉，
它改变每一个数字，而它没有家。

## 四、修法

`dea` 变成对 `ema` 的**调用**：

```python
mature = [value for value in dif if value is not None]
pad: list[Indicator] = [None] * (len(dif) - len(mature))
dea: list[Indicator] = pad + ema(mature, signal)
```

⭐ 文件里 EMA 的定义从 2 个变成 1 个，docstring 里那句「inherits `ema`'s seeding」
**从此为真**，预热变成 25 + 8 = 33。

## 五、终值没变，所以只有数非空值才看得见

真实数据（茅台 215 根）：

| | 修前 | 修后 |
|---|---|---|
| DIF 末值 | -15.94 | -15.94 |
| DEA 末值 | -11.78 | -11.78 |
| 柱 末值 | -4.16 | -4.16 |
| **DEA 预热** | **25** | **33** |

⭐ 末值一模一样 —— 182 根的 EMA9 把种子洗掉了。
**变的只有头部 8 根**，而头部 8 根正是图上「这条线从哪里开始画」的那几根。

⭐ 所以**看图看不出来、看末值看不出来、看任何聚合值都看不出来**。
唯一能看见它的是「数一数有多少个 `None`」—— 一个没人会主动做的动作。

## 六、教训

1. ⭐ **文档里写下一个数字，就是一个有人得去核对的断言。**
   核对它最便宜的方式不是读代码，是**把它断言出来**。
   `dea` 现在在参数表里，值 33 —— 而这张表是红的那个。

2. ⭐ **参数表里少一行，和多一行同样是一种声明。**
   `dif` 在、`dea` 不在，这个不对称是唯一暴露问题的线索。
   一张表和一个函数应该一一对应，**少的那行要说得出来为什么少**。

3. ⭐ **「一个概念一个家」也要管住同一个文件里的两次实现。**
   跨文件复制容易看见，同一文件里重写一遍不会。

4. ⭐ **只有渲染出来/数出来的东西才会自相矛盾。**
   这一条已经是本项目的纪律，而这一回是它**第四次**兑现：
   前三次分别是空图表、契约错误、门禁从未跑过的集成测试。

## 七、相关

* `failure-modes.md` F-112（文档里的数字是断言）
* `spec 038` §七
