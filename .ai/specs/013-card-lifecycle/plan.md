# Plan 013 · K2 卡片生命周期 — 技术方案

## 施工顺序（每层闭环，逐层验证）

1. **领域层**：`CardEventType` + 两个错误类；新增错误码三处登记。
2. **迁移 0004**：`card_events` 表 + 触发器 + 索引；登记 manifest / constraints；up/down。
3. **仓储层**：`CardEventRow` + `list_events`；改造 `verify`、新增 `converge`；读取加载 events；补仓储测试。
4. **API**：PATCH converge；CardRead 增 events；verify 自动写事件；补 API 测试。
5. **前端**：收敛操作 + 已收敛区域 + 状态历史；补组件/E2E。
6. **门禁与归档**：`dev.py check` 10 道；status.md；四段式变更日志；提交推送。

## 关键技术决策

- **状态真源与历史分离**（沿用 ADR-0014 思路）：当前态在 `cards`（权威、查询快），流转历史在
  `card_events`（append-only）。不用「从事件推导当前态」，避免一次删除/乱序改变状态。
- **同事务双写**：`cards` 的 UPDATE 与 `card_events` 的 INSERT 在一个 `transaction()` 内，
  保证状态与事件原子一致。API 层已有 `with transaction(connection)`，仓储函数在其内执行。
- **append-only 落第④层**：触发器物理拦截 UPDATE/DELETE，不靠人记（ADR-0016 / 规则分层 0.2）。
- **收敛理由必填落数据库**：`event_type!='converged' OR reason IS NOT NULL`，
  领域层再做非空白校验（数据库只能拦 NULL，拦不住纯空格）。
- **事件读取沿用 K1 模式**：逐行加载（与 symbols 一致），个人级数据量、无额外进程，接受 N+1。
- **converged 卡沉底弱化而非隐藏**：红线 10 要求用户看得到放弃过什么；不做自动折叠到底。

## 新增错误码

- `CARD_NOT_ACTIVE`：对非 active 卡收敛。
- `CARD_CONVERGE_REASON_REQUIRED`：收敛缺非空白理由。

登记三处：`core/error_codes.py` 枚举 · `.ai/error-codes.md` · 检查器（CARD 前缀已在 CODE_PATTERN，无需改规则）。

## 验证策略

- 仓储测试：verify 写事件、converge 成功/非 active/理由空白/不存在、事件排序、同事务原子性。
- API 测试：converge 200/409/400/404、events 回读、verify 后事件存在。
- 行为测试：card_events 的 UPDATE/DELETE 被触发器拒绝。
- 迁移集成：0003→0004 升级、期望版本=4、约束计数更新。
- 变异：M1 断开事件写入（converge 只改状态）→ 测试须红；M2 去掉触发器 → append-only 行为测试须红。
- E2E：新增一条收敛闭环（收敛按钮→填理由→卡进入已收敛区域）。
