# TSP 能力矩阵 · 2026-09-29

> 源：`D:\AAA\A-kew\references\sources\tick-stock-panel`（**本地已有**）· v0.2.2 · MIT License
> 核实方式：**逐条代码搜索**，不采信文档数字（依据其 `docs/secondary-development.md` §1：
> 「AI 必须通过代码搜索确认能力是否已经实现……不得虚构导入路径或调用结果」）
> 执行：OpenCode（Codex）· 模型：Space Bunny Free

---

## 零、⭐ 先说最重要的一件事：这份评估不是第一次做

`alphacouncil/backend/src/alphacouncil/providers/base.py` 的模块文档写着：

> **Design borrowed from the TSP review (see ``references/deep-dives/12``)**

也就是说 **D3 行情层的能力路由模型本来就是从 TSP 借来的**，而且借的是它最核心的那一块：

| TSP 的设计 | AlphaCouncil 的实现 | 位置 |
|---|---|---|
| 「一个能力是一个**数据集**，不是一个功能」 | `Dataset` 枚举（DAILY/REALTIME/ADJ_FACTOR/FINANCIAL/INSTRUMENTS） | `providers/base.py` |
| 能力是布尔，状态是枚举 | `ProviderCapabilities.datasets: frozenset[Dataset]` | 同上 |
| 批量失败语义必须声明 | `BatchSemantics.INDEPENDENT / COLLATERAL` | 同上 |
| 能力路由矩阵为单一权威 | `router.py` + `ProviderCapabilities` | `providers/router.py` |

⚠️ **但 `references/deep-dives/` 目录不存在。** 我用代码搜索确认过：整个 `alphacouncil/references/`
下没有 `deep-dives`，`alphacouncil/references/` 本身也不存在（该目录在仓库外一级：
`A-kew/references/`）。⭐ **所以产品源码里有一条指向不存在文档的引用**，而那条引用是**唯一的**
出处说明——「为什么这套设计是这样」这个问题的答案，实际只存在于一句注释里。

📌 **待办**：补 `references/deep-dives/12`，或把那句引用改指到真实存在的地方。
这不是学术问题：下一次有人要改 `Dataset`，就会找不到当初为什么是这五个。

---

## 一、逐条核实的结果

### 1.1 ⭐ TSP 自己的文档互相矛盾

| 声称来源 | 数字 | 代码实际 |
|---|---|---|
| `README.md` | 25 个内置策略 | **26 个 `.py` 文件** |
| `docs/features.md` | 「18 个内置策略」 | 同上 |
| 代码 `backend/app/strategy/builtin/*.py` | — | **26** |

⭐ **三处不一致。** 我按 `secondary-development.md` §1 的要求以代码为准，记 26。

策略清单（26）：`active_limit_gene` · `boll_breakout` · `breakout_new_high_60d` ·
`broken_board_recovery` · `bullish_alignment` · `consecutive_limit_ups` ·
`factor_rank_research` · `high_turnover_surge` · `limit_up_momentum` ·
`long_lower_shadow_reversal` · `low_volatility_leader` · `ma_convergence_breakout` ·
`ma_golden_cross` · `macd_below_zero_revival` · `macd_golden` · `n_day_low_reversal` ·
`near_limit_up` · `oversold_bounce` · `oversold_reversal` · `platform_consolidation_breakout` ·
`pullback_ma20_bounce` · `pullback_to_support` · `rsi_midline_pullback` · `strong_open` ·
`trend_breakout` · `volume_price_surge`

### 1.2 ⭐ 八个「扩展点」里，只有一个真的存在

`docs/secondary-development.md` §4.1 列出八个建议的后端继承点。我逐个搜了 `class X`：

| 文档声称 | 代码实际 |
|---|---|
| `NotificationFormatter` | ✅ **已实现**（`app/extensions/contracts.py`） |
| `CandidateFilter` · `ScoringPolicy` · `PositionSizingPolicy` · `RiskPolicy` · `StrategyProvider` · `MonitorConditionEvaluator` · `BacktestCostModel` | ⭐ **只有设计规范，没有任何类** |

⭐ **这七个必须按「不存在」对待。** 它自己是分得很清的（文档用表格区分「已可用/按需扩展」），
但那句「后端优先使用小粒度策略接口和依赖注入」很容易让人以为可以直接继承它们。

---

## 二、能力逐条裁决

裁决四档：**✅ 直接复制** · **🔧 需改造** · **📐 只吸收方法** · **⛔ 不该吸收**

### 2.1 ✅ 直接复制（1 项）

| TSP 功能 | 证据 | 为什么值得 |
|---|---|---|
| **SMTP 邮件通道** | `app/services/email_adapter.py` 3.5KB，仅依赖 `smtplib` + 标准库 | ⭐ AlphaCouncil **整个仓库没有任何推送代码**（`webhook`/`feishu`/`smtp`/`notify` 四个词 0 命中）。而红线 7 要求教训自动排程、spec 028 要求笔记会自己回来找你 —— **「该复习了」现在只在页面里等你去点**。推送「你该复盘了」不是荐股，与宪法同向 |

它带着一个真实缺陷类的修复，值得原样保留：**`QUIT` 失败不得重试**，
否则「邮件已送达 + 收件人收到两封」。

### 2.2 🔧 需改造（1 项，且卡在一个架构决定上）

| TSP 功能 | 证据 | 障碍 |
|---|---|---|
| **Webhook 通道**（飞书签名 / 企业微信 markdown / 通用 JSON + **HMAC-SHA256**） | `app/services/webhook_adapter.py` 16.7KB · 含 `hmac`+`sha256`+`feishu` | ⭐ **S-01 会拦住它**：不在 `providers/` 里 `import httpx` 就是 `CHECK_RAW_HTTP` error，官方修复建议是「走 provider 层」。而 provider 层是**行情**路由，把 webhook POST 塞进去是错的 |

⭐ **所以我不能直接抄，也不打算偷偷给 `no_raw_http` 加豁免。**
这需要一次真实的架构决定（HTTP 出口的归属），按本项目纪律先出 spec。→ **spec 033**

代码质量值得记录的部分（即便要改造也该保留）：
- ⭐ **4xx 不重试 / 5xx 与网络错误退避重试**，理由写在代码里：*告警冷却在事件生成时即打戳，
  一次瞬时 5xx 若不重试，该告警会被冷却窗口压掉，离屏用户彻底收不到*
- ⭐ **企业微信 markdown 按字节截断**（上限 4096 **字节**不是字符，中文每字 3 字节）
- ⭐ `is_valid_custom_url` 拒绝**带用户名密码的 URL**（`not parsed.username`）
- 飞书签名算法：`hmac.new(f"{ts}\n{secret}".encode(), digestmod=sha256).digest()` → base64

⚠️ **复制时必须改的三处品牌**：`User-Agent: TickFlow-Webhook/1.0` ·
`X-TickFlow-Timestamp` / `X-TickFlow-Signature` · 截断提示里的「回到 TickFlow 应用内查看」。

### 2.3 📐 只吸收方法，不复制代码（2 项）

| TSP 功能 | 证据 | 为什么不能复制代码 |
|---|---|---|
| **市场阶段（情绪周期）+ 主线识别** | `market_phase.py` 10.8KB · `market_mainline.py` 12KB —— **真实存在** | ⭐ **数据底座完全不存在**：AlphaCouncil 全仓对 `涨停` / `连板` / `limit_up` / `概念` / `行业` / `consecutive_limit_ups` 六个关键词 **0 命中**。它只有关注池里那几只标的的行情。而它明确写着**「不生成任何交易信号，仅供研究分析」** |

这份文档本身质量很高，**方法论值得吸收**（D6「市场温度」正写着「指标定义**未定**」）：

- ⭐ **阈值用真实数据标定**：1454 个交易日的 p10/p60/p90 分位数，常量集中在模块顶部
- ⭐ **持续性设计**：EMA 平滑（alpha=1/3）+ 2 日确认，平均段长 **9.7 天**（对比它自己原来那套 5 档 state 的 1.1–1.5 天）
- ⭐ **弱档否决**：大盘弱时正向阶段一律降为 —— 修的是「涨停生态强但大盘崩」那类错标（2024-01 微盘危机）
- ⭐ **它诚实标注了自己的偏差**：兜底档占 **~74%** 天数（「A股大部分时间没有处于可辨认的周期位置」）；
  概念成分是**当前快照回看历史**，所以早年主线有归属漂移，并以 `membership_note` 字段随 API 返回

⭐ **这份「诚实的偏差声明」本身就是 AlphaCouncil 该学的** —— 比代码更值得抄。

### 2.4 ⛔ 不该吸收（5 项）

选股引擎（26 策略）· 回测引擎（vectorbt）· 因子平台（DSL/IC/Newey-West/BH-FDR）·
监控中心（4 类规则 + 弹窗 + 语音）· 异动监控（竞价/盘中/偏移三档）· 因子挖掘 · ETF 全线支持

**理由不是「做不了」，是「做了就不是 AlphaCouncil 了」：**

1. AlphaCouncil 的产品定义是**知识管理系统**（`.ai/status.md`：「我们是一个知识管理系统」）。
   上面这一串加起来是**量化终端**。
2. 宪法红线 1/2 禁止荐股与预测。TSP 自己守住了（「不对标同花顺/通达信，不内置 AI 荐股/涨停预测」），
   ⭐ **但选股 + 回测 + 因子平台组合起来，产物就是预测能力** —— 哪怕每一步都合法。
3. 它的数据底座（全市场日 K、涨停梯队、概念成分、分钟 K 落盘）AlphaCouncil **一个都没有**。
   ⭐ **这不是「抄代码」的问题，是「抄一个没有原料的配方」。**

---

## 三、一句话结论

> **TSP 的招牌架构（能力路由 / 三源互备 / 复权 / 熔断 / 四态契约）AlphaCouncil 早已借走并且做得更严；
> 它剩下的是量化业务，而那部分 AlphaCouncil 明确不该有。
> 真正值得直接搬过去的只有一样东西：推送通道 —— 因为 AlphaCouncil 一个通知都没有，
> 而红线 7 与 spec 028 已经要求系统主动来找你。**

📌 已落 `.ai/specs/033`（推送通道，含 S-01 的 HTTP 出口归属决定）。


---

## 补记（2026-09-29 晚）：分钟 K 的**实测**结论

⭐ **这一节记的是量出来的事实，不是读文档得来的结论。** 代码没有落地
（原因见最后一节），但下一次做这件事时不必重新试错。

### 三个免费源的实测（2026-09-29，本机）

| 源 | 结果 | 行的形状 |
|---|---|---|
| **新浪** | ✅ HTTP 200 · 45,782 B · 320 根 | `{"day":"2026-09-28 13:37:00","open":"1236.400","high":"1237.000","low":"1236.400","close":"1237.000","volume":"6924","amount":"8…"}` —— ⭐ **完整 OHLC** |
| **腾讯** | ✅ HTTP 200 · 10,874 B | `"0930 1244.60 311 38707059.80"` —— ⭐ **只有价格/量/额，没有 OHLC** |
| **东财** | ❌ `RemoteDisconnected` | 与 `status.md` 记的「本机被封」一致 |

### 四条由此定死的结论

**1. ⭐ `MinuteBar` 必须要求完整 OHLC，所以腾讯出局。**
造一根 `open=low=high=close=price` 的假 bar 就是**让估计穿着测量的外套**
—— 与 `Quote.amount` 保持 nullable 是同一个理由。
⭐ 代价要写清楚：**MINUTE 这个数据集只有一源，不是三源。**
router 的价值是第二个意见，而这个数据集没有第二个意见。
把「三源互备」写在文档里而某个数据集悄悄只有一源，
⭐ 正是本项目在自己的测试与 fixture 里反复抓的那类失败。

**2. ⭐ `bar_time` 必须是「naive 的 Asia/Shanghai 墙钟」，而且要给它换个名字。**
`base.now()` 拒绝 naive datetime，理由是「墙钟读数不是时间点」—— ⭐ 但 `09:31` **不是时间点，
是交易时段里的一个位置**，它的时区是交易所的，固定，与服务器无关。
所以字段叫 `bar_time` 而不是 `timestamp`，把这个区别做进类型里。
另外：**用固定 `+08:00` 偏移而不是 `zoneinfo`** —— 后者在没装 tzdata 的 Windows 上
**首次使用即失败**，而这个项目要打成 exe；中国自 1991 年无夏令时，固定偏移不是简化，是全部事实。

**3. ⭐ 只取已收盘的分钟。** 实时行情最后一根是**正在形成的价格**，
画出来是一根会在读者眼前变化的蜡烛 —— 这是「把缓存日线当今天收盘价」的盘中孪生兄弟。

**4. 新浪的响应在 JSONP 之前有一段脚本前缀**，解析器必须容忍：
`/*<script>location.href='//sina.com';</script>*/\nx([{…}])`。
⭐ 实测这样写解析器能拿到全部 320 条。（`hq.sinajs.cn` 需要的 Referer 对
`quotes.sina.cn` **不适用**，两个 host 要分别处理。）

### ⭐ 两个「类型系统会教你的事」

**A. `Protocol` 的默认实现只对显式子类生效。**
把 `get_minute` 的默认值写进 `MarketDataProvider` 之后，`mypy --strict` 仍然报
三个 provider「缺少 `get_minute`」—— 因为它们是**结构化**满足协议的，
而结构化检查看的是**类上有没有这个属性**，协议的默认值不会凭空加上。
⭐ 正确的形状是一个共享基类（`NoMinuteBars`），让不能提供分钟线的 provider **显式继承**它 ——
**在类型系统里说「我决定了，决定是不」，而不是在注释里说三次。**

**B. 给 `Dataset` 加一个成员会打破既有测试。**
`Dataset` 从 5 个变 6 个时，两个能力相关测试直接红了（它们断言的是**精确的集合**）。
⭐ 这不是「测试太严」——它是一条真实的提醒：**能力矩阵是被断言的，加一格要连带改断言**。

### 这一节为什么没有落地代码

`SinaProvider.get_minute` 写完之后，**真实请求返回 `no_data`**，
而传输与解析**单独验证都通过**（320 条解析成功）。⭐ **根因我没有定位到**，
所以没有提交一个「看起来能用」的实现。

⭐ 而且我为修 `NoMinuteBars` 的类型错误加的 `name: ClassVar[str]`
**反而制造了新错误**（子类里 `name` 是 property，mypy 报
「不能用只读 property 覆盖可写属性」）。

⭐ 树已回退干净（**999 通过 · ruff 0 · mypy 0**）。
**一个红的树留在那里，比晚一天做完更糟** —— 因为下一次动手的人
分不清哪些是既有的、哪些是我留下的。
