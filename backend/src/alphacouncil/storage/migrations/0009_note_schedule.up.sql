-- 0009 · note_schedule：笔记的复习队列（spec 028）
--
-- 为什么这两张表存在：
-- spec 026 让「记录知识」成为可能，spec 027 让它可以被找到。剩下的最后一环是
-- **它得自己回来找你** —— `前端设计系统与功能规划` §A2 的原话：
-- 「收藏 500 篇文章不等于拥有知识。SRS 才是把信息转化为长期记忆的机制。」
-- 没有这张表，笔记库就只是一箱文本。
--
-- ⭐ **为什么不并进 `card_schedule`（spec 026 已裁定，这里给出决定性的理由）**：
-- 形状相同，但**可变性不同**，而可变性逼出了第三个 outcome：
--   · 卡片**不可变** —— K1 刻意不给编辑动词，所以「我当时复习的那条」永远是同一条；
--   · 笔记**可变** —— spec 026 给了 `PATCH`。
-- 于是队列里的笔记被改写后，FSRS 的记忆强度还挂在**已经不存在的文本**上：
-- 假设 9 月入队评了 3 次 good，10 月正文整段重写，11 月到期 resurfacing 时
-- 用户被要求回忆一段他从没复习过的文字，而排程器以为他记得很牢。
-- ⭐ **那是排程器在说谎**，而本项目的立论是「你的记录是你唯一能信的东西」。
-- → 改写 = 重启排程（`outcome = 'reset'`），**流水一行不删**。
-- ⭐ 这个第三态是**笔记独有的**：不可变的卡片永远不需要它。
-- 也就是说 —— 如果两者真的一样，`reset` 就该是两者的共同能力，**而它不是**。
-- 这条不对称是「分开建表」最强的证据。
--
-- 1. 与 0005 同构：schedule 是「现在怎么样」的真源（每条一行，可变），
--    reviews 是 append-only 的流水（每次交互一行，字段全是结构化的）。
--    一种形状一张表，不合并（ADR-0014）。
-- 2. state 是我们的四态枚举，比 fsrs 的三态多一个 `deferred` —— 理由同 0005：
--    「现在不是时候」不是一次失败，不该污染记忆强度。对笔记来说它有一个更
--    具体的含义：**「我的想法还没定」**。
-- 3. state_json 存 fsrs.Card.to_dict() 原文，不拆成 7 列：算法升级时不需要迁移。
-- 4. duration_ms 存「重读花了多久」，**只用于自省**（红线 11 明文禁止排名/打卡）。
-- 5. `reset` 既没有评分也没有耗时：那次重写里用户没有回忆任何东西。

CREATE TABLE note_schedule (
    note_id      TEXT    NOT NULL PRIMARY KEY,
    fsrs_card_id INTEGER NOT NULL,
    state_json   TEXT    NOT NULL,
    state        TEXT    NOT NULL,
    due_at       TEXT    NOT NULL,
    enrolled_at  TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    CONSTRAINT note_schedule_note_required_check
        CHECK (length(trim(note_id)) > 0),
    -- fsrs 只接受 int 的 card_id，而我们的主键是 TEXT；这是无语义内部句柄。
    CONSTRAINT note_schedule_fsrs_id_check
        CHECK (fsrs_card_id > 0),
    CONSTRAINT note_schedule_state_check
        CHECK (state IN ('learning', 'review', 'relearning', 'deferred')),
    CONSTRAINT note_schedule_state_json_valid_check
        CHECK (json_valid(state_json) AND json_type(state_json) = 'object'),
    CONSTRAINT note_schedule_due_at_check
        CHECK (length(trim(due_at)) > 0),
    CONSTRAINT note_schedule_enrolled_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', enrolled_at) = enrolled_at),
    CONSTRAINT note_schedule_updated_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', updated_at) = updated_at),
    CONSTRAINT note_schedule_updated_not_before_enrolled_check
        CHECK (updated_at >= enrolled_at),
    FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
) STRICT;

-- 到期队列的主查询路径：due_at <= as_of。
CREATE INDEX idx_note_schedule_due ON note_schedule(due_at);

CREATE TABLE note_reviews (
    id          TEXT    NOT NULL PRIMARY KEY,
    note_id     TEXT    NOT NULL,
    outcome     TEXT    NOT NULL,
    rating      TEXT,
    reviewed_at TEXT    NOT NULL,
    duration_ms INTEGER,
    from_due_at TEXT    NOT NULL,
    to_due_at   TEXT    NOT NULL,
    from_state  TEXT    NOT NULL,
    to_state    TEXT    NOT NULL,
    CONSTRAINT note_reviews_id_check
        CHECK (GLOB('note_review_[0-9]*', id)),
    CONSTRAINT note_reviews_note_required_check
        CHECK (length(trim(note_id)) > 0),
    CONSTRAINT note_reviews_outcome_check
        CHECK (outcome IN ('reviewed', 'deferred', 'reset')),
    CONSTRAINT note_reviews_rating_shape_check
        CHECK (rating IS NULL OR rating IN ('again', 'hard', 'good', 'easy')),
    -- 条件必填（ADR-0016 标准写法，不用 CASE WHEN）：
    -- 只有真复习才有评分。推迟与重写都没有 —— 推迟是「还没想清楚」，
    -- 重写是「换了内容」，两次都没有回忆任何东西。
    CONSTRAINT note_reviews_reviewed_needs_rating_check
        CHECK (outcome != 'reviewed' OR rating IS NOT NULL),
    CONSTRAINT note_reviews_deferred_has_no_rating_check
        CHECK (outcome != 'deferred' OR rating IS NULL),
    CONSTRAINT note_reviews_deferred_has_no_duration_check
        CHECK (outcome != 'deferred' OR duration_ms IS NULL),
    -- ⭐ reset 同样没有评分、没有耗时。它和 deferred 的区别不是"程度"，
    -- 是**方向**：deferred 往后推，reset 往回退。
    CONSTRAINT note_reviews_reset_has_no_rating_check
        CHECK (outcome != 'reset' OR rating IS NULL),
    CONSTRAINT note_reviews_reset_has_no_duration_check
        CHECK (outcome != 'reset' OR duration_ms IS NULL),
    -- 「未成熟留空，绝不填 0」（红线 6）：耗时要么有值要么为 NULL。
    CONSTRAINT note_reviews_duration_positive_check
        CHECK (duration_ms IS NULL OR duration_ms > 0),
    CONSTRAINT note_reviews_reviewed_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', reviewed_at) = reviewed_at),
    CONSTRAINT note_reviews_from_state_check
        CHECK (from_state IN ('learning', 'review', 'relearning', 'deferred')),
    CONSTRAINT note_reviews_to_state_check
        CHECK (to_state IN ('learning', 'review', 'relearning', 'deferred')),
    FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_note_reviews_note ON note_reviews(note_id);
CREATE INDEX idx_note_reviews_reviewed_at ON note_reviews(reviewed_at);

CREATE TRIGGER note_reviews_no_update BEFORE UPDATE ON note_reviews
BEGIN SELECT RAISE(ABORT, 'note_reviews is append-only: 复习流水不可修改'); END;

CREATE TRIGGER note_reviews_no_delete BEFORE DELETE ON note_reviews
BEGIN SELECT RAISE(ABORT, 'note_reviews is append-only: 复习流水不可删除'); END;
