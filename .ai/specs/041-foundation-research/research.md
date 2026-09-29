# 调研记录 · 财务数据源与 TSP 代码摸底

> 日期：2026-09-29 · 执行：OpenCode（Codex）
> ⭐ **本文件只写实测到的和查到原文的。** 没测到的写「未测」，不写「应该可以」。

---

## 一、TSP 后端代码结构（我上一轮只看了 docs）

| 目录 | .py 数量 | 上一轮是否看过 |
|---|---|---|
| `services/` | **65** | ❌ |
| `strategy/` | **45** | ❌ |
| `api/` | 30 | ❌ |
| `backtest/` | 17 | ❌ |
| `data_providers/` | 12 | ✅ 只看了这个 |
| `tickflow/` | 8 | ❌ |
| `custom/` | 7 | ❌ |
| `plugins/` | 6 | ❌ |
| `factors/` | 5 | ❌ |
| `extensions/` | 4 | ❌ |
| `indicators/` | 3 | ❌ |
| `jobs/` | 2 | ❌ |

⭐ **这是「大部分不该吸收」那个判断最直接的反驳材料**：我当时只读过 `docs/features.md`
的文字描述和 `data_providers` 的结构，**而 110 个文件在 services / strategy / backtest 里没读过一行。**

---

## 二、外部案例：数据源风险不是假设

**Tushare Pro 停运事件**（财联社 2025-08-26 原文，53 万阅读）：

> 8月18日 TusharePro 因**数据托管机房代理商与运营商纠纷**停运，8月23日全部恢复。
> 停运一周「让量化圈重视数据源稳定性以及**单一数据源的风险隐患**」。

⭐ 这正是宪法 §4.5「三源互备」要回答的事，而它**不是理论风险**。
⭐ 而 Tushare 的**财务指标接口需要 2000 积分**（官方文档），对自托管桌面应用是门槛。

---

## 三、四个免费源，四个独立来源的口径

| | 优点（引用） | 缺点（引用） |
|---|---|---|
| **AKShare** | 开源免费、覆盖品种广 | 「数据偶有缺失，需要用户自行清洗」「实时接口延迟约 500 毫秒」；⭐ **宪法 v2→v3 已明文移除**（178 个依赖 / 近半 GB） |
| **Tushare 基础版** | 免费 | 「部分数据更新存在延迟，数据细节处理偶有争议」；财务指标要 2000 积分 |
| **efinance** | 开源免费、支持 A股/美股 | 「接口数量相对较少，文档也不够详尽」；⭐ **1 分钟数据仅能获取当天的** |
| **BaoStock** | ⭐ **「无需注册」**、日/周/月/分钟线、财务报表+财务指标 | 「数据稳定性高，很少出现缺失或错误」（正面） |

⭐ **四份来源里只有 BaoStock 被点名为「稳定」，且是唯一无需注册的。**

---

## 四、BaoStock 实测（一次性 venv，2026-09-29）

### 4.1 依赖与体积 —— ⭐ 两个不同的轴

```
baostock                                0.39 MiB
pandas                                 59.41 MiB
pandas.libs                             0.55 MiB
numpy                                  30.84 MiB
numpy.libs                             20.18 MiB
python_dateutil / six / tzdata          0.57 MiB
──────────────────────────────────────────────
整个 venv                            124.35 MiB
```

| | BaoStock | AKShare（宪法记录） |
|---|---|---|
| **依赖个数** | **6** | 178 |
| **体积** | **124.35 MiB** | 「接近半 GB」 |
| **其中 baostock 自己** | **0.39 MiB** | — |

⭐ **依赖个数赢了 30 倍，体积输了。** 而 ⭐ **体积的 99.9%（111.65 MiB）是 pandas + numpy，
baostock 自己只有 0.39 MiB。**

⚠️ **`pandas` 是硬依赖。** 删掉它之后：

```
File "baostock\data\resultset.py", line 9, in <module>
    import pandas as pd
ModuleNotFoundError: No module named 'pandas'
```

⭐ **`import baostock` 就炸，pandas 装不上就用不了。**

### 4.2 财务数据：红线 17 有解 ✅

6 组 API，⭐ **全部带 `pubDate` + `statDate`**：

| API | 内容 | 关键字段 |
|---|---|---|
| `query_profit_data` | 盈利能力 | `pubDate` `statDate` `roeAvg` `npMargin` `gpMargin` `netProfit` `epsTTM` `MBRevenue` `totalShare` `liqaShare` |
| `query_operation_data` | 营运能力 | 各类周转率/天数 |
| `query_growth_data` | 成长能力 | `YOYEquity` `YOYAsset` `YOYNI` `YOYEPSBasic` |
| `query_balance_data` | 偿债能力 | `currentRatio` `quickRatio` `liabilityToAsset` |
| `query_cash_flow_data` | 现金流 | `CFOToNP` `CFOToOR` … |
| `query_dupont_data` | 杜邦 | `dupontROE` `dupontPalm` … |

**实测（sh.600519，2024 年报）**：

```python
{'code': 'sh.600519', 'pubDate': '2025-04-03', 'statDate': '2024-12-31',
 'roeAvg': '0.384283', 'npMargin': '0.522734', 'gpMargin': '0.919312',
 'netProfit': '89334728025.900000', 'epsTTM': '68.642173',
 'MBRevenue': '170611838052.020000', ...}
```

⭐ `statDate` = 报告期，`pubDate` = 公告日 —— **正是红线 17 要的 `period_end` + `announced_at`，
而且值是对的**（A股年报须 4/30 前披露，4/03 合理）。
⭐ 而这直接让 PIT 可实现：**一个 2025-01-01 写下的判据不能看到这份数据，因为它 04-03 才公告。**

### 4.3 ⭐ 估值逐日 PIT（这是我最担心的一条，它过了）

日线字段里带 `peTTM` / `pbMRQ` / `turn` / `isST` / `tradestatus`。
红线 9 明确允许展示「估值」，⭐ **所以它到底是不是 PIT 就不 academic 了** ——
一个用今天净资产回填 2024 年的 PB，是**看不见的前视偏差**。

实测：

| bar | close | peTTM | pbMRQ |
|---|---|---|---|
| **2024-01-02** | 1685.01 | **29.73** | **9.72** |
| 2024-01-05 | 1663.36 | 29.35 | 9.59 |
| **2026-09-29** | 1235.58 | **18.97** | **6.15** |

⭐ **2024-01-02 的 PE 是 29.73 而不是 18.97**，所以**不是回填**。
旁证：1685 ÷ 29.73 ≈ 56.7，正是茅台 2023 年 EPS 量级。
⭐ **结论：baostock 的估值字段逐日 PIT，可以直接用。**

### 4.4 附带解决的两个现存缺口

* ⭐ **`query_trade_dates` 给官方交易日历，含节假日。** 实测 2026-09-25/26/27 = 非交易日
  （农历八月十五）。比现在「探测」可靠。
* ⭐ **`query_stock_basic` 有 `ipoDate` / `outDate` / `status`** —— 新股识别有解了。
  ⭐ 这正是 spec 040 里「`warming` 状态在生产里只能由新股触发」那个观察的答案。

### 4.5 风险（必须一起说）

| | 出处 |
|---|---|
| ⭐ **`error_code 10001011` = IP 已加入黑名单** | 官方 API 文档。**它会封 IP** |
| `Development Status :: 3 - Alpha` | 自己的 dist-info |
| **非线程安全**，并行要**多进程** | 官方文档 |
| ~~财务数据**滞后约 2 个月**（季报发布后）~~ | 官方文档。⭐ **2026-09-30 实测推翻：这只是个区间，不是一个常数** —— 2026Q1 **25 天** / 2026Q2 **46 天** / 2024 年报 **93 天**。文档那个数字接近**年报**，把它套到季报上是错的 |
| 协议是**私有 socket**（端口 10030） | 官方文档 |

许可：**BSD License**（`License:` metadata 字段）。
⚠️ ⭐ **dist-info 里没有 LICENSE 文件**，只有 metadata 那一行 ——
⭐ **门禁 L-06 的扫描器要看 metadata，不能只找文件。**

---

## 五、⭐ 一个被新需求暴露出来的既有盲区：S-01 管不到 socket

BaoStock 走的是 **socket 协议（端口 10030），不是 HTTP。**

S-01 拦的是 `httpx` / `requests` / `aiohttp` / `urllib3` 的 import
（`RAW_HTTP_MODULES`，见 spec 039）。
⭐ **一个 socket 客户端在 `providers/` 之外 import，S-01 一声不响。**

⭐ 而 S-01 的前提是「**唯一入口**」。**唯一入口只覆盖了 HTTP 这一种出口。**

⚠️ **这不是「可以绕过去」** —— 这是 S-01 的一个已存在的覆盖缺口，
被一个真实需求照出来了。**需要一个决定**，见 `plan.md` §决策 2。

---

## 六、明确未测的

* ⭐ **未测**：BaoStock 在本项目实际并发下的稳定性、限流阈值
* ⭐ **未测**：BaoStock 断线/重连行为
* ⭐ **未测**：`services/` / `strategy/` / `backtest/` 的**代码质量** ——
  我这一轮只数了文件，**没读实现**。读代码是 Phase 1 的事。
* ⭐ **未测**：pandas 3.0.6 与本项目 Python 3.12 的兼容性（装上是好的，但项目 venv 未装）
