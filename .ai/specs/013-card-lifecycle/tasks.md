# Tasks 013 · K2 卡片生命周期

## T1 · 领域层与错误码
- [x] `domain/card.py`：新增 `CardEventType`（verified/converged）
- [x] 新增错误类 `CardNotActiveError` / `CardConvergeReasonRequiredError`
- [x] `core/error_codes.py`：新增 `CARD_NOT_ACTIVE` / `CARD_CONVERGE_REASON_REQUIRED`
- [x] `.ai/error-codes.md`：登记两个新码
- [x] 更新 `__all__` 导出

## T2 · 迁移 0004
- [x] `0004_card_events.up.sql`：建表 + 条件必填 CHECK + 两条 append-only 触发器 + 索引
- [x] `0004_card_events.down.sql`：DROP TRIGGER / TABLE
- [x] `manifest.json`：登记 version 4
- [x] `constraints.json`：登记 card_events（append_only=true）全部约束
- [x] 迁移集成测试：0003→0004 升级、期望版本 4
- [x] `test_storage.py`：约束计数更新

## T3 · 仓储层
- [x] `CardEventRow` dataclass
- [x] `list_events(connection, card_id)`
- [x] 改造 `verify`：同事务写 verified 事件
- [x] 新增 `converge(connection, card_id, reason)`：校验 + UPDATE + converged 事件
- [x] 读取路径（get/list/query/list_all）加载 events
- [x] 仓储测试（含 append-only 触发器行为、同事务原子性）

## T4 · API
- [x] `CardConvergeRequest`（extra forbid，reason）
- [x] `CardEventRead` + `CardRead.events`
- [x] PATCH `/{id}/converge`
- [x] verify 端点行为（自动事件，接口不变）
- [x] 各 to_read 填充 events
- [x] API 测试

## T5 · 前端
- [x] `api.ts`：CardEventType/CardEvent 类型、Card.events、convergeCard
- [x] CardSection：收敛按钮 + 理由内联输入
- [x] active 当前主张 / converged 沉底弱化区域
- [x] 卡片状态历史展示
- [x] vitest / tsc / oxlint / build
- [x] E2E：收敛闭环一条

## T6 · 门禁与归档
- [x] `dev.py check` 10 道全绿
- [x] 变异检查 M1 / M2 全红
- [x] `status.md` 同步
- [x] 四段式变更日志
- [x] 提交并经 Git Data API 推送
