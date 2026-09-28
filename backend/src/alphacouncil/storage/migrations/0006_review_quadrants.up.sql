-- 0006 · decision_review_state + reviews：复盘与四象限（spec 020 · J3）
--
-- 为什么是两张表而不是一张（ADR-0014，已采纳）：
--   decision_review_state = 「是否已复盘」与「什么时候到期」的**唯一真源**，可写。
--   reviews               = 复盘事实，**append-only**，一条决策可复盘多次。
--
-- ⭐ 硬规则：**「是否已复盘」绝不从 reviews 是否存在推断。**
-- 派生量会被"删掉一行 review"悄悄改变 —— 而"我复盘过"这个事实不该被任何人悄悄改掉。
--
-- ⭐ 而 review_count **可以**从 reviews 数出来，因为 reviews 是 append-only 的。
-- 这两句话看起来矛盾，其实不是：一个是从**可变**存储推断状态（不可靠），
-- 一个是从**不可变**存储数出个数（可靠）。这一段写在这里，
-- 否则下一个读到这里的人会以为其中一条是笔误，然后"顺手统一"掉其中一条。
--
-- ⭐ outcome 是**分类**（good / bad / failed），**不是数字**（项目总纲 P0-3 硬门禁）。
-- 原因：红线 10 要求"坏决策+好结果时**不显示盈利数字**"。
-- 如果表里存的是收益率，那"不显示"就只是一条渲染时的隐藏规则 ——
-- 而**已经存在的数字会泄漏**：日志里、导出里、将来任何一个新增的 API 字段里。
-- 所以这里根本没有数字可显示。**少一列不是 bug，是红线 10 落在数据模型上的样子。**
--
-- ⭐ 结果分到期硬门禁下沉到 CHECK（宪法第零条 0.2「能移就必须移」）：
-- ISO-8601 时间戳是可字典序比较的字符串，所以把到期时刻复制进 review 行，
-- 就能让**绕过领域层的调用**也被数据库挡住。

CREATE TABLE decision_review_state (
    decision_id  TEXT NOT NULL PRIMARY KEY,
    due_at       TEXT NOT NULL,
    -- 到期前必须为 NULL。红线 6：未成熟结果留空，**绝不预填 0**。
    reviewed_at  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    CONSTRAINT decision_review_state_due_required_check
        CHECK (length(trim(due_at)) > 0),
    -- 可空，且**永不为 0**：一条还没到期复盘的决策，它的"是否已复盘"就是没有。
    CONSTRAINT decision_review_state_reviewed_blank_or_real_check
        CHECK (reviewed_at IS NULL OR reviewed_at != ''),
    CONSTRAINT decision_review_state_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at),
    CONSTRAINT decision_review_state_updated_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', updated_at) = updated_at),
    -- 不可能在到期之前就复盘。state 表自己也拒。
    CONSTRAINT decision_review_state_not_reviewed_early_check
        CHECK (reviewed_at IS NULL OR reviewed_at >= due_at),
    FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_decision_review_state_due ON decision_review_state(due_at);

CREATE TABLE reviews (
    id              TEXT    NOT NULL PRIMARY KEY,
    decision_id     TEXT    NOT NULL,
    -- 过程分 1..5，由**用户自己**写（红线 15：判断必须由用户下，系统不打分）。
    process_score   INTEGER NOT NULL,
    -- ⭐ 分类，不是数字。见文件头。
    outcome         TEXT,
    reviewed_at     TEXT    NOT NULL,
    -- 写入时从 decision_review_state 复制的到期时刻：硬门禁的锚。
    due_at_snapshot TEXT    NOT NULL,
    note            TEXT,
    created_at      TEXT    NOT NULL,
    CONSTRAINT reviews_id_check
        CHECK (GLOB('review_[0-9]*', id)),
    CONSTRAINT reviews_decision_required_check
        CHECK (length(trim(decision_id)) > 0),
    CONSTRAINT reviews_process_score_check
        CHECK (process_score BETWEEN 1 AND 5),
    CONSTRAINT reviews_outcome_shape_check
        CHECK (outcome IS NULL OR outcome IN ('good', 'bad', 'failed')),
    -- ⭐ 硬门禁：结果分在到期前必须留空（项目总纲 P0-3）。
    -- ISO-8601 字符串可字典序比较，所以这条能由数据库执行，
    -- 而**绕过领域层的调用也躲不过它**。
    CONSTRAINT reviews_not_scored_early_check
        CHECK (outcome IS NULL OR reviewed_at >= due_at_snapshot),
    CONSTRAINT reviews_outcome_needs_reviewed_at_check
        CHECK (outcome IS NULL OR reviewed_at IS NOT NULL),
    CONSTRAINT reviews_due_snapshot_required_check
        CHECK (length(trim(due_at_snapshot)) > 0),
    CONSTRAINT reviews_note_shape_check
        CHECK (note IS NULL OR length(trim(note)) > 0),
    CONSTRAINT reviews_note_length_check
        CHECK (note IS NULL OR length(note) <= 1000),
    CONSTRAINT reviews_reviewed_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', reviewed_at) = reviewed_at),
    CONSTRAINT reviews_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at),
    FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_reviews_decision ON reviews(decision_id);
CREATE INDEX idx_reviews_reviewed_at ON reviews(reviewed_at);

CREATE TRIGGER reviews_no_update BEFORE UPDATE ON reviews
BEGIN SELECT RAISE(ABORT, 'reviews is append-only: 复盘不可修改'); END;

CREATE TRIGGER reviews_no_delete BEFORE DELETE ON reviews
BEGIN SELECT RAISE(ABORT, 'reviews is append-only: 复盘不可删除'); END;
