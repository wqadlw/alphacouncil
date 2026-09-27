# 错误码与诊断契约

> **错误码是受管理的命名空间。** 按来源分类 · 每条标 severity · **发布后不改名**。
> 建立：2026-09-26 · 依据 `references/deep-dives/05-openspec.md` 决定 12/13/14 · `10-akshare.md` 决定 1/2

---

## 一、统一诊断信封

**所有对外诊断（CLI 输出 / API 错误体 / 检查脚本结果）必须是同一个形状**：

```json
{
  "severity": "error",
  "code": "DATA_SOURCE_RATE_LIMITED",
  "message": "腾讯行情接口返回空，已切换到新浪",
  "target": "quote:600519",
  "fix": "无需操作；若持续超过 5 分钟，请检查网络"
}
```

| 字段 | 谁读 | 规则 |
|---|---|---|
| `severity` | 程序 | `error` / `warning` / `info` |
| `code` | **程序** | **稳定标识符**，发布后**不得改名**（改名 = 破坏调用方） |
| `message` | **人** | 可改，可本地化 |
| `target` | 程序 + 人 | 出问题的对象（文件 / 记录 / 标的） |
| `fix` | **人** | ⭐ **一句可执行的建议或命令**；**可以为 `null`**（诚实：不是所有问题都能自动修） |

**⚠️ `fix` 为空是合法形态。** 凡涉及"用户必须亲手做"的操作（写决策 / 打分 / 改理由），`fix` 必须是**说明性文字**（如"请你自己写下改变想法的理由"），**不能自动执行**。

### 1.1 `--json` 模式的硬规则

- **stdout 只放一个 JSON 文档。**
- **所有人类文字（提示 / 进度条 / 横幅 / 日志）必须走 stderr。**
- 理由：调用方要能直接 `| jq`，不需要过滤噪声。

---

## 二、错误码命名空间

**格式**：`<来源>_<具体>`

| 前缀 | 来源 | 说明 |
|---|---|---|
| `DATA_SOURCE_*` | 外部数据源 | 取数相关 |
| `DATA_*` | 数据本身 | 数据状态相关（四态） |
| `CONTRACT_*` | 数据契约 | 口径 / 类型 |
| `DECISION_*` | 决策记录 | 门禁 / append-only |
| `AGENT_*` | agent 权限 | 越权 / 草稿 |
| `MIGRATION_*` | 数据库迁移 | |
| `STORAGE_*` | 本地存储 | |
| `CHECK_*` | 检查脚本 | |

### 2.1 `DATA_SOURCE_*`

| code | severity | 含义 | `fix` |
|---|---|---|---|
| `DATA_SOURCE_RATE_LIMITED` | warning | 限流（返回空） | "已自动降速/换源；无需操作" |
| `DATA_SOURCE_IP_BLOCKED` | **error** | ⚠️ **封 IP**（`RemoteDisconnected`） | "请等待约 20 小时或更换网络；**不要重试**" |
| `DATA_SOURCE_FORBIDDEN` | error | 403（风控信号） | "**不重试**。该源暂不可用" |
| `DATA_SOURCE_CIRCUIT_OPEN` | warning | 该源已熔断 | "已跳过该源，使用备胎" |
| `DATA_SOURCE_UNAVAILABLE` | error | 全部源不可用 | "请检查网络连接" |
| `DATA_SOURCE_UNREACHABLE` | error | 传输层故障（超时 / DNS / 连接被中断 / 5xx） | "已尝试换源；若全部失败请检查网络" |
| `DATA_SOURCE_NOT_SUPPORTED` | info | 该源**不声明**支持这个数据集或交易所（**未发请求**） | "已自动换源；这是能力路由，不是故障" |
| `DATA_SOURCE_TICKER_AMBIGUOUS` | error | 代码歧义（`000001`） | "请选择市场：沪市 / 深市" |
| `DATA_SOURCE_TICKER_INVALID` | error | 无法解析 | "请检查代码格式（如 `600519` / `sh600519`）" |

> ⚠️ **限流与封 IP 必须分成两个 code** —— **恢复策略不同**（降速 vs 等 20 小时），程序与用户都需要区分。
> ⚠️ **`DATA_SOURCE_NOT_SUPPORTED` 不是故障** —— 能力路由在**发请求之前**就判定该源不适用（如未声明 `markets` 里的交易所）。
> 把它算成 error 会让"我们没问过它"看起来像"它坏了"。


### 2.2 `DATA_*`（对应宪法 4.6 数据四态）

| code | severity | 对应态 | 含义 |
|---|---|---|---|
| — | — | `ok` | 有数据（无错误码） |
| `DATA_NO_DATA` | info | `no_data` | **确实没有**（业务结果）。**必须带 `reason`** |
| `DATA_FETCH_ERROR` | error | `error` | **取数失败**（系统故障） |
| ⭐ `DATA_UNVERIFIABLE` | warning | **`unavailable`** | **存在但无法验证** |

**⚠️ 关键**：`DATA_NO_DATA` 与 `DATA_FETCH_ERROR` **必须在类型层面就不同** ——
否则调用方会把"接口坏了"当成"确实没有数据"，**产品会安静地失效**。

```python
# 业务结果 → ValueError 的子类（"确实没有"）
class NoDataError(ValueError): ...

# 系统故障 → RuntimeError 的子类（"接口坏了"）
class DataFetchError(RuntimeError): ...
```

**⚠️ 注意**：JSON 解析错误是 `ValueError` 的子类 —— **不转换就会被调用方当成"确实没有数据"**。必须显式包装。

### 2.3 `CONTRACT_*`

| code | severity | 含义 |
|---|---|---|
| `CONTRACT_ADJUST_MISMATCH` | error | 复权口径混用（前复权 + 不复权同序列） |
| `CONTRACT_UNIT_AMBIGUOUS` | error | 百分比单位不明（`0.05` vs `5`） |
| `CONTRACT_CURRENCY_MISSING` | error | 金额缺币种（不存在"裸数字金额"） |
| `CONTRACT_PERIOD_MISSING` | error | 财务缺 `period_end` 或 `announced_at` |

### 2.4 `DECISION_*`

| code | severity | 含义 |
|---|---|---|
| `DECISION_RATIONALE_REQUIRED` | error | 理由必填未填 |
| `DECISION_COUNTER_EVIDENCE_REQUIRED` | error | **反面证据必填未填** |
| `DECISION_APPEND_ONLY` | error | 试图 UPDATE / DELETE 决策记录（**触发器抛出**） |
| `DECISION_CLIENT_SUPPLIED_ID` | error | 客户端试图传入主键（**禁止伪造"结果之前"**） |
| `DECISION_KILL_CRITERIA_REQUIRED` | error | **失效条件为空**，或谓词形状不合法（2026-09-26 随 J1 新增） |
| `DECISION_TEXT_TOO_LONG` | error | 理由 / 反面证据超过 2000 字（2026-09-26 随 J1 新增） |

> **为什么 `DECISION_KILL_CRITERIA_REQUIRED` 需要独立一条**：schema 只能强制
> `kill_criteria` 是 **JSON 数组**，**空数组同样通过**。而"没有任何可证伪条件"正是
> 这个产品存在的意义要防的事，所以在领域层拦。独立成码的理由与反面证据相同 ——
> 「用户多久会记下一条无法被证伪的决策」这个问题必须可统计。
>
> **它为什么不做成 schema 约束**：SQLite 无法给已存在的表加 CHECK，要加就得**重建
> `decisions` 表并重建它的 append-only 触发器**。而宪法规则 21 要求的是失效条件的
> **形式**必须结构化（schema 已强制），**没有**要求最少条数。所以这一条停在领域层，
> 而不是为了一个规格未写明的规则去动表结构。


### 2.5 `CARD_*`（知识卡片）

| code | severity | 含义 |
|---|---|---|
| `CARD_CONTENT_REQUIRED` | error | 卡片主张内容为空 |
| `CARD_SOURCE_URL_REQUIRED` | error | 来源 URL 为空或协议非法（红线 4） |
| `CARD_SOURCE_TITLE_REQUIRED` | error | 来源标题为空 |
| `CARD_NOT_FOUND` | error | 目标卡片不存在 |
| `CARD_ALREADY_VERIFIED` | error | 卡片非 `ai_generated`，无法执行核对升级 |
| `CARD_TEXT_TOO_LONG` | error | 卡片主张内容超过长度上限 |
| `CARD_PRIORITY_INVALID` | error | 卡片优先级超出 1..5 范围 |

### 2.5 `AGENT_*`

| code | severity | 含义 |
|---|---|---|
| `AGENT_TOOL_NOT_FOUND` | error | 试图调用**不存在**的工具（第 ④ 档） |
| `AGENT_DRAFT_NOT_COMMITTED` | info | 草稿未提交（正常流程） |
| `AGENT_WRITE_DENIED` | error | 越权写入（**最高优先级缺陷**） |

### 2.6 `MIGRATION_*` / `STORAGE_*`

| code | severity | 含义 | `fix` |
|---|---|---|---|
| `MIGRATION_SNAPSHOT_FAILED` | error | 迁移前快照失败 | "**迁移已中止**；请检查磁盘空间" |
| `MIGRATION_FAILED` | error | 迁移失败 | "备份位于 `<path>`；可点击重试" |
| `STORAGE_DB_NEWER_THAN_APP` | error | 库版本 > 程序版本 | "**请升级程序**（不支持降级）" |
| `STORAGE_DB_NO_UPGRADE_PATH` | error | 无迁移路径 | "该库版本无法升级到当前程序版本" |

### 2.7 `CHECK_*`（检查脚本的诊断码）

> **一条静态规则一个码**（`S-01` ~ `S-12`），外加两个**不属于任何单条规则**的运行器码。
> 实现：`backend/checks/`（`checks/rules/<slug>.py` 的 `CODE` 常量）。
> **`S-12` 保证本表与 `checks/registry.py` 双向一致** —— 文档列了但代码没实现、或代码实现了但文档没登记，都会让构建失败。

| code | severity | 规则 | 含义 |
|---|---|---|---|
| `CHECK_RAW_HTTP` | error | S-01 | 业务代码里绕过唯一入口直连 HTTP |
| `CHECK_BOOLEAN_STATE` | error | S-02 | 用 ≥2 个布尔值跟踪同一对象的状态 |
| `CHECK_PREDICTION_FIELD` | error | S-03 | 出现预测 / 荐股形状的字段、函数或路由 |
| `CHECK_MISSING_TRIGGER` | error | S-04 | append-only 表缺 `BEFORE UPDATE` / `BEFORE DELETE` 触发器 |
| `CHECK_UNREGISTERED_CODE` | error / warning | S-05 | 错误码未在本文件登记 / 已登记但代码里不存在 |
| `CHECK_CLIENT_SUPPLIED_ID` | error | S-06 | 请求 schema 允许客户端提交服务端赋值的字段 |
| `CHECK_RETURN_RATE_LEAK` | error | S-07 | 首页出现"收益率"类字样（红线 9） |
| `CHECK_IMMATURE_OUTCOME` | error | S-08 | 未成熟结果回退成 `0` 或 `—`（红线 6） |
| `CHECK_TIME_COST_MISSING` | error | S-09 | 止损组件未显示"恢复所需年数"（红线 12） |
| `CHECK_PRINT_STATEMENT` | error | S-10 | 产品代码里出现 `print()`（宪法 7.4） |
| `CHECK_BARE_EXCEPT` | error | S-11 | 裸 `except:` 或空 body 的 `except Exception:`（宪法 7.3） |
| `CHECK_DOC_DRIFT` | error / warning | S-12 | `.ai/checks/static/README.md` 的规则清单与代码不一致 |
| `CHECK_EXEMPTION_UNREASONED` | error | —（运行器） | `# noqa: S-xx` 没写理由 —— **豁免必须有理由** |
| `CHECK_RUNNER_ERROR` | error | —（运行器） | 规则脚本自身崩溃 —— **崩溃与通过无法区分，必须报** |

> ⚠️ **`CHECK_EXEMPTION_UNREASONED` 与 `CHECK_RUNNER_ERROR` 不归属任何单条规则**，
> 因此它们的 `target` 指向脚本自身或那一行豁免注释，而不是产品代码。

### 2.8 `WATCHLIST_*`

> 关注池（D1）的理由规则。**与 `DECISION_*` 分开** —— 两者形状相似但不是同一件事：
> 一个守的是"已经发生的交易"，另一个守的是"还没有交易、只是先关注"。
> 合并会让"用户多久不写理由"这个问题无法统计。
> 实现：`backend/src/alphacouncil/domain/watchlist.py`。

| code | severity | 含义 | `fix` |
|---|---|---|---|
| `WATCHLIST_REASON_REQUIRED` | error | 关注理由缺失或纯空白 | "请你自己写下为什么关注它 —— 这是将来复盘时的对照物" |
| `WATCHLIST_REASON_TOO_LONG` | error | 理由超过 2000 字符 | "请精简到 2000 字以内；`thesis.md` 才是展开论证的地方" |
| `WATCHLIST_NOT_FOLLOWED` | error | 对**从未加入**的标的改理由 / 移出（HTTP 404） | "先把它加入关注池" |
| `WATCHLIST_ALREADY_REMOVED` | error | 最新一条事件是移出，不能再改（HTTP 409） | "它已经被移出；重新加入而不是修改" |

> ⚠️ **`WATCHLIST_REASON_REQUIRED` 的 `fix` 必须是说明性文字** ——
> 对应 §一 的红线：凡是"用户必须亲手做"的操作，`fix` 不能是可自动执行的建议。
>
> ⚠️ **`WATCHLIST_NOT_FOLLOWED` 与 `WATCHLIST_ALREADY_REMOVED` 必须分开。**
> "从没加过"与"加过又移出"对应不同的用户文案 —— 一个提示"加入"，一个提示"重新加入"。
> 合并成一个码，前端就只能从英文句子里把区别读出来。
>
> ⚠️ **HTTP 状态码不写在领域层。** 领域抛带 `code` 的错误，API 在
> `api/errors.py` 的 `_STATUS_BY_CODE` 里映射（其余一律 400）。这样同一个失败
> 不会因为"哪一层先发现"而变成两种形状。

### 2.9 `INSTRUMENT_*`

> 关于**标的本身**，而不是用户与它的关系。实现：
> `backend/src/alphacouncil/domain/instrument.py` +
> `backend/src/alphacouncil/storage/repositories/instruments.py`。

| code | severity | 含义 | `fix` |
|---|---|---|---|
| `INSTRUMENT_ASSET_TYPE_CONFLICT` | error | 同一个 `(market, code)` 被断言为两种类型（HTTP 409） | "先确认它是股票 / 指数 / ETF 中的哪一个 —— 同一个代码只能有一个答案" |

> ⚠️ **为什么不静默取其一**：保留旧值会**隐藏用户的错误**，采用新值会**改写别的记录
> 已经依赖的事实**。两者都是"看起来合理的错答案"，所以抛错。

---

## 三、退出码契约

| 退出码 | 含义 |
|---|---|
| `0` | **执行成功** —— ⚠️ **注意："发现健康问题"仍然是 0** |
| `1` | 执行失败（内部错误） |
| `2` | 用法错误（参数不合法） |
| `130` | 用户取消（Ctrl-C） |

**⚠️ 关键区分**：
> **"检查运行成功"与"检查通过"是两件事。**
> `make check` 的退出码 = **0 只表示"我跑完了"**；**是否通过要看输出里的汇总行**。

---

## 四、错误呈现的 UI 规则（对应宪法 12.1 与红线 10）

| 规则 | 说明 |
|---|---|
| **错误信息禁止省略 / 截断 / 折叠** | "Do not ellipsize embedded messages"；所有文案与标识符必须换行不溢出 |
| ⭐ **提示时长按"别处能否找到"判定** | 能 → 6/8 秒自动消失；**不能 → 必须手动关** |
| ⭐ **唯一恢复入口的错误必须持久** | 不允许自动消失 |
| **提示不许抢焦点** | 悬停 / 键盘聚焦时**暂停计时** |
| **对话框内提交失败 → 在该对话框显示** | **不弹第二个框** |
| **有归属页面的错误不许用全局浮层** | 就地显示 |
| **缺凭据不能显示成"空但成功"的列表** | 必须显式报错 |
| **一次查询失败不能替换有效记录** | 有可用数据时，刷新失败降级为**小提示** |
| **原始内部错误不直接显示给用户** | 转成诊断信封 |

---

## 五、维护规则

1. **新增错误码必须在本文件登记**（前缀 + severity + 含义 + fix 形态）。
2. **已发布的 code 不得改名**；需要变更语义时**新增一个 code**，旧码保留（可标记 deprecated）。
3. **每个 `error` 级错误码必须有一个测试覆盖它被抛出的路径。**
4. **本文件与代码中的错误类必须一一对应** —— 用静态检查保证（`.ai/checks/static/`）。

---

*本文件随错误码增减更新。**未登记的 code 不得出现在代码里。***
