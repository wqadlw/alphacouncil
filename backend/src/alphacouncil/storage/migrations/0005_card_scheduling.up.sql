-- 0005 · card_schedule + card_reviews：FSRS 复习排程（spec 018 · K3）
--
-- 为什么这两张表存在：
-- 红线 7「教训必须能再次遇到」要求每条教训生成一条调度项。K1/K2 把卡片做成了
-- 知识与生命周期，但**没有任何机制让一张卡在合适的时候重新出现**。
-- 这一迁移补上那个机制，并且刻意不碰 K1/K2 的任何东西。
--
-- 为什么是两张表而不是并进 card_events（ADR-0014 的先例：分开，不合并）：
--   card_events（K2）= 生命周期事件：罕见、带散文理由（converged 必填理由）。
--   card_reviews（本迁移）= 复习事实：高频、每卡每次交互一行、字段全是结构化的。
-- 一种形状一张表。合并会让条件必填的 CHECK 爆炸，而 CHECK 一多就等于没有。
--
-- 核心设计：
-- 1. card_schedule 是「现在怎么样」的真源，每卡一行，**可变**（与 cards.status 不是一回事：
--    一张 converged 的卡仍可有排程行，只是不再进队列）。
-- 2. state 是**我们的**四态枚举，比 fsrs 的三态多一个 deferred —— 因为
--    Scheduler.reschedule_card 的用途是「换调度器时重算」，不是「推迟」（2026-09-28 实测）。
--    **推迟只改 state 与 due_at，state_json 一个字节都不动**：「现在不是时候」
--    不是一次失败，不该污染记忆强度。
-- 3. state_json 存 fsrs.Card.to_dict() 原文（实测 to_dict→from_dict 无损往返），
--    不拆成 7 列：算法升级时不需要迁移。
-- 4. card_reviews append-only：复习流水只增不改不删。
-- 5. duration_ms 存「写下回答花了多久」，**只用于自省**（红线 11 明文禁止排名/打卡）。

CREATE TABLE card_schedule (
    card_id      TEXT    NOT NULL PRIMARY KEY,
    fsrs_card_id INTEGER NOT NULL,
    state_json   TEXT    NOT NULL,
    state        TEXT    NOT NULL,
    due_at       TEXT    NOT NULL,
    enrolled_at  TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    CONSTRAINT card_schedule_card_required_check
        CHECK (length(trim(card_id)) > 0),
    -- fsrs 只接受 int 的 card_id，而我们的主键是 TEXT；这是无语义内部句柄。
    CONSTRAINT card_schedule_fsrs_id_check
        CHECK (fsrs_card_id > 0),
    -- 比 fsrs 的三态多一态：deferred 是队列语义，不是记忆状态。
    CONSTRAINT card_schedule_state_check
        CHECK (state IN ('learning', 'review', 'relearning', 'deferred')),
    CONSTRAINT card_schedule_state_json_valid_check
        CHECK (json_valid(state_json) AND json_type(state_json) = 'object'),
    -- due_at 是带偏移的 ISO datetime（fsrs 的 to_dict 产出的就是这种形状）。
    CONSTRAINT card_schedule_due_at_check
        CHECK (length(trim(due_at)) > 0),
    CONSTRAINT card_schedule_enrolled_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', enrolled_at) = enrolled_at),
    CONSTRAINT card_schedule_updated_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', updated_at) = updated_at),
    CONSTRAINT card_schedule_updated_not_before_enrolled_check
        CHECK (updated_at >= enrolled_at),
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
) STRICT;

-- 到期队列的主查询路径：due_at <= as_of。
CREATE INDEX idx_card_schedule_due ON card_schedule(due_at);

CREATE TABLE card_reviews (
    id          TEXT    NOT NULL PRIMARY KEY,
    card_id     TEXT    NOT NULL,
    outcome     TEXT    NOT NULL,
    rating      TEXT,
    reviewed_at TEXT    NOT NULL,
    duration_ms INTEGER,
    from_due_at TEXT    NOT NULL,
    to_due_at   TEXT    NOT NULL,
    from_state  TEXT    NOT NULL,
    to_state    TEXT    NOT NULL,
    CONSTRAINT card_reviews_id_check
        CHECK (GLOB('review_[0-9]*', id)),
    CONSTRAINT card_reviews_card_required_check
        CHECK (length(trim(card_id)) > 0),
    CONSTRAINT card_reviews_outcome_check
        CHECK (outcome IN ('reviewed', 'deferred')),
    CONSTRAINT card_reviews_rating_shape_check
        CHECK (rating IS NULL OR rating IN ('again', 'hard', 'good', 'easy')),
    -- 条件必填（ADR-0016 标准写法，不用 CASE WHEN）：
    -- 真复习必须有评分；推迟既没有评分也没有耗时。
    CONSTRAINT card_reviews_reviewed_needs_rating_check
        CHECK (outcome != 'reviewed' OR rating IS NOT NULL),
    CONSTRAINT card_reviews_deferred_has_no_rating_check
        CHECK (outcome != 'deferred' OR rating IS NULL),
    CONSTRAINT card_reviews_deferred_has_no_duration_check
        CHECK (outcome != 'deferred' OR duration_ms IS NULL),
    -- 「未成熟留空，绝不填 0」（红线 6）：耗时要么有值要么为 NULL。
    CONSTRAINT card_reviews_duration_positive_check
        CHECK (duration_ms IS NULL OR duration_ms > 0),
    CONSTRAINT card_reviews_reviewed_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', reviewed_at) = reviewed_at),
    CONSTRAINT card_reviews_from_state_check
        CHECK (from_state IN ('learning', 'review', 'relearning', 'deferred')),
    CONSTRAINT card_reviews_to_state_check
        CHECK (to_state IN ('learning', 'review', 'relearning', 'deferred')),
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_card_reviews_card ON card_reviews(card_id);
CREATE INDEX idx_card_reviews_reviewed_at ON card_reviews(reviewed_at);

CREATE TRIGGER card_reviews_no_update BEFORE UPDATE ON card_reviews
BEGIN SELECT RAISE(ABORT, 'card_reviews is append-only: 复习流水不可修改'); END;

CREATE TRIGGER card_reviews_no_delete BEFORE DELETE ON card_reviews
BEGIN SELECT RAISE(ABORT, 'card_reviews is append-only: 复习流水不可删除'); END;
