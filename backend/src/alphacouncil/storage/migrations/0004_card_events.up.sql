-- 0004 · card_events：卡片状态事件流（spec 013 · K2）
--
-- 为什么这张表存在：
-- K1 卡片的来源/状态可变（核实升级、收敛退出），与「只增不改」冲突。
-- 每次状态流转追加一条不可改、不可删的事件，使「这张卡为什么是现在的状态」
-- 可追溯（ADR-0022 升级留痕；ADR-0021 S-01 收敛出口）。
--
-- 核心设计：
-- 1. 事件两型：verified（核实升级 ai_generated -> user_written）
--             converged（收敛退出 active -> converged）。
-- 2. converged 必须带理由（条件必填 CHECK）；verified 理由可选。
-- 3. append-only：触发器拒绝 UPDATE / DELETE。
-- 4. 归属卡片：card_id 外键，卡片删除时级联。

CREATE TABLE card_events (
    id         TEXT    NOT NULL PRIMARY KEY,
    card_id    TEXT    NOT NULL,
    event_type TEXT    NOT NULL,
    reason     TEXT,
    created_at TEXT    NOT NULL,
    CONSTRAINT card_events_id_check
        CHECK (GLOB('event_[0-9]*', id)),
    CONSTRAINT card_events_card_required_check
        CHECK (length(trim(card_id)) > 0),
    CONSTRAINT card_events_type_check
        CHECK (event_type IN ('verified', 'converged')),
    CONSTRAINT card_events_reason_not_blank_check
        CHECK (reason IS NULL OR length(trim(reason)) > 0),
    CONSTRAINT card_events_reason_length_check
        CHECK (reason IS NULL OR length(reason) <= 500),
    CONSTRAINT card_events_converge_reason_check
        CHECK (event_type != 'converged' OR reason IS NOT NULL),
    CONSTRAINT card_events_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at),
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_card_events_card ON card_events(card_id);

CREATE TRIGGER card_events_no_update BEFORE UPDATE ON card_events
BEGIN SELECT RAISE(ABORT, 'card_events is append-only: 状态变更不可修改'); END;

CREATE TRIGGER card_events_no_delete BEFORE DELETE ON card_events
BEGIN SELECT RAISE(ABORT, 'card_events is append-only: 状态变更不可删除'); END;

