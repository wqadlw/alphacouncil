# 2026-09-29 · 吸收 tick-stock-panel（spec 033）

> 起因：主人给了 `https://github.com/shy3130/tick-stock-panel`，问「本地有没有？
> 把这个项目的功能全部好好吸收，能复制的直接复制」。
> 执行：OpenCode（Codex）· 模型：Space Bunny Free
> 产出：`.ai/references/research/2026-09-29-tsp-capability-matrix.md`（逐条核实）

---

## 一、本地早就有，而且是 MIT

`D:\AAA\A-kew\references\sources\tick-stock-panel` —— **880 文件 / 22.5MB / v0.2.2 / MIT License**。

MIT 允许复制，条件是**保留版权与许可声明**，所以署名进了 `notify/email.py` 的文档字符串，
而不是一个没人会打开的 `NOTICE`。

## 二、⭐ 这份评估不是第一次做，而出处丢了

`providers/base.py` 的模块文档写着：

> **Design borrowed from the TSP review (see ``references/deep-dives/12``)**

⭐ **但 `references/deep-dives/` 不存在**（代码搜索确认）。也就是说「为什么能力是**数据集**
而不是功能」这个问题的唯一答案，活在一句注释里，而它指向的地方是空的。

## 三、⭐ TSP 的招牌架构，AlphaCouncil 早就借走了，而且做得更严

| TSP 的设计 | AlphaCouncil | 位置 |
|---|---|---|
| 能力是一个数据集，不是一个功能 | `Dataset` 枚举 | `providers/base.py` |
| 能力是布尔，状态是枚举 | `ProviderCapabilities.datasets` | 同上 |
| 批量失败语义必须声明 | `BatchSemantics.INDEPENDENT/COLLATERAL` | 同上 |
| 能力路由矩阵为单一权威 | `router.py` | `providers/router.py` |
| 前复权口径 | `adj_factor` + **宪法 4.2 的四种不可互换单位** + `CONTRACT_ADJUST_MISMATCH` | `models/market.py` |

⭐ 最后一行值得单说：**AlphaCouncil 把复权基准写进了宪法**，TSP 只是文档里的一节。

## 四、⭐ TSP 自己的文档互相矛盾，所以逐条按代码核实

| 声称 | 代码实际 |
|---|---|
| README「25 内置策略」 | **26 个 `.py`** |
| features.md「18 个内置策略」 | 同上 |
| secondary-development 列 8 个后端扩展点 | ⭐ **只有 `NotificationFormatter` 真的存在**，其余 7 个（`CandidateFilter`/`ScoringPolicy`/`PositionSizingPolicy`/`RiskPolicy`/`StrategyProvider`/`MonitorConditionEvaluator`/`BacktestCostModel`）**没有任何 class** |

依据它自己 `docs/secondary-development.md` §1 的要求：*AI 必须通过代码搜索确认能力是否已经实现，
不得虚构导入路径或调用结果*。

## 五、逐条裁决

**✅ 直接复制（1）** —— **SMTP 邮件通道**。理由：AlphaCouncil 全仓对
`webhook`/`feishu`/`smtp`/`notify` 四个词 **0 命中**，而红线 7 与 spec 028 都要求系统主动来找你。
⭐ 它只依赖 `smtplib`，**完全不碰 httpx**，所以零 S-01 冲突，现在就落地了（36 条测试）。

**🔧 需改造（1，卡住）** —— **Webhook 通道**（飞书签名 / 企业微信 markdown /
通用 JSON + HMAC-SHA256，16.7KB）。⭐ **S-01 会拦住它**：不在 `providers/` 里 `import httpx`
就是 error，而官方修复建议「走 provider 层」对 webhook 是错的 —— 那是**行情**路由。
所以这需要一次架构决定（spec 033 §2 列了 A/B/C 三个选项），⭐ **而不是悄悄给 P0 规则加白名单**。

**📐 只吸收方法（2）** —— **市场阶段（情绪周期）+ 主线识别**（`market_phase.py` 10.8KB ·
`market_mainline.py` 12KB，真实存在）。⭐ **代码不能抄，因为数据底座完全不存在**：
AlphaCouncil 全仓对 `涨停`/`连板`/`limit_up`/`概念`/`行业`/`consecutive_limit_ups`
**六项全部 0 命中**。它只有关注池里那几只标的。
⭐ **这不是抄代码的问题，是抄一个没有原料的配方。**

而这份文档本身质量很高，方法论值得吸收（D6「市场温度」正写着「指标定义**未定**」）：

- 阈值用 **1454 个交易日**的 p10/p60/p90 分位数标定，常量集中在模块顶部
- 持续性：EMA 平滑 + 2 日确认，平均段长 **9.7 天**（它自己原来那套 5 档 state 只有 1.1–1.5 天）
- **弱档否决**：大盘弱时正向阶段一律降为，修的是「涨停生态强但大盘崩」那类错标
- ⭐ **它诚实标注了自己的偏差**：兜底档占 ~74% 天数（「A股大部分时间没有处于可辨认的周期位置」）；
  概念成分是当前快照回看历史，所以早年有归属漂移，并以 `membership_note` 随 API 返回
- 它自己写着「**不生成任何交易信号，仅供研究分析**」—— ⭐ 与 AlphaCouncil 红线 1 同向

⭐ **那份「诚实的偏差声明」比代码更值得抄。**

**⛔ 不该吸收（7）** —— 选股引擎（26 策略）· 回测引擎（vectorbt）· 因子平台 ·
监控中心 · 异动监控 · 因子挖掘 · ETF 全线支持。

⭐ **理由不是「做不了」，是「做了就不是 AlphaCouncil 了」**：
1. 它的产品定义是**知识管理系统**，上面这一串加起来是**量化终端**
2. 选股 + 回测 + 因子平台组合起来，产物就是预测能力 —— 哪怕每一步都合法
3. 数据底座一个都没有

## 六、⭐ 一句话结论

> **TSP 的招牌架构 AlphaCouncil 早已借走并且做得更严；它剩下的是量化业务，
> 而那部分 AlphaCouncil 明确不该有。真正值得搬的只有推送通道 —— 因为本项目一个通知都没有，
> 而红线 7 已经要求系统主动来找你。**

## 七、我在这次里犯的错

**1. ⭐ 我的测试断言了函数被写成要避免的行为，两次。**
`test_a_missing_field_is_not_ready` 把 `from_address` 放进「缺字段」列表，
而 `is_configured` **故意回退到 `username`** —— 而且**另一条测试正是在断言这个回退**。
⭐ **一条测试和同一函数的另一条测试互相矛盾，那就不是在测这个函数。**
第二次是 `from_address=None` 我期望 False，实际 True —— 同一个原因。

**2. ⭐ 重试测试根本没在测重试。** 我用的 double 只要 `fail_send` 就**每次都失败**，
所以那条测试实际断言的是「建立了两次连接」—— ⭐ 而一个永远不成功的重试循环同样满足它。
改成**只让第一次失败**，它才区分「重试」和「重复」。

**3. ⭐ 一次传输的调用列表断言，意外变成了「断言从不认证」。**
`["send", "quit"]` 这个期望撞上一个填了 username 的 double，于是它顺带断言了登录不会发生。

**4. 我为了「列表看起来完整」往参数化列表里塞了个 `None`**，结果与函数签名不符，
多出一个 mypy 报告为 unused 的 `type: ignore`。⭐ **让列表显得周全，比让契约周全更容易，
而后者才是测试的作用。**

**5. ⭐ 一个我没查的目录。** 我引用了 `alphacouncil/references/deep-dives/12` 才意识到
该目录不存在 —— ⭐ 而这条引用是**唯一**的出处说明。

## 八、验证

* 推送通道 **36 条测试通过** · ruff 0 · mypy --strict 0
* ⭐ 门禁跑 `check-static` 时 **S-14 报出我自己三个未 add 的新文件** ——
  一轮 spec 之前我写的规则，此刻正在抓我
