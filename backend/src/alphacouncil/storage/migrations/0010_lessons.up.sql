-- 0010 · lessons：教训，以及红线 7 要求的调度项（spec 030 · J5）
--
-- 为什么这些表存在：
-- 主人的原话是「要可以记录任何和金融股市相关的知识和经验」。spec 026-028 补上了
-- **知识**（记下来 -> 找得到 -> 会自己回来找你）。**经验**这一半一直没有入口，
-- 而 `constitution.md` 第 7 条已经把要求写死了：
--
--     教训必须能再次遇到 · **每条教训必须生成一条调度项（FSRS）**
--
-- `.ai/eval/redlines.json` 记着自己的缺口：「机制有了，每条教训自动生成还没有。
-- 本项目没有教训这个类型，J5 未开工」。⭐ 关键词是**自动** —— 今天的排程是用户点
-- 一下才发生的，红线要的是每条教训自动产生一条调度项。
--
-- 1. ⭐ **教训不放在 `cards` 里**，这是被纠正过一次的设计。第一稿想放松
--    `source_url` / `source_title` 为可空、加一个 `review_id`、让出处变成
--    「URL 或复盘」。听起来 provenance rule 反而更强了（一次复盘比一个链接更说明
--    你当时怎么想的），但两个 `NOT NULL` 在 SQLite 里**改不掉** —— 除非重建整张
--    `cards` 表，而它被 `card_schedule` / `card_events` / `note_links` 外键引用。
--    **重建不是重点，重点是它把 spec 026 整个反过来**：`status.md` 里当初建笔记
--    的诊断是「`cards` 三条锁死 -> 宏观判断、方法论、**教训**、读书笔记全都记不
--    下」。教训就是当初建笔记的原因之一。⭐ 教训没有 URL 可给，**这不是缺陷，这
--    是它的定义** —— 它的出处是一次真实发生过的、你自己的判断失误。
-- 2. 与 0005 / 0009 同构：schedule 是「现在怎么样」的真源（每条一行，可变），
--    reviews 是 append-only 的流水（每次交互一行）。一种形状一张表，不合并
--    （ADR-0014）。
-- 3. ⭐ **`lesson_reviews` 没有 `reset`。** `note_reviews` 需要它，是因为笔记可变
--    （spec 028）：队列里的笔记被改写后，FSRS 的记忆强度还挂在**已经不存在的文
--    本**上，那是排程器在说谎。教训不可变 —— 你不会去改一条教训，因为改完它就不
--    是那条教训了，你会写另一条 —— 所以它挂着的文本永远存在，**没有东西需要重
--    启**。现在三套流水：两张不可变的两套没有 reset，一张可变的有。
--    ⭐ 这个不对称是「教训和卡片同一类」的直接证据，不是巧合。
-- 4. outcome 多一个 `enrolled`（不是 reset）：红线让入队成为强制，所以「这条为什
--    么在队列上」必须有一行可以审计，而不是只存在于变更日志里。
-- 5. state 是我们的四态枚举，比 fsrs 的三态多一个 `deferred` —— 理由同 0005。
-- 6. state_json 存 fsrs.Card.to_dict() 原文，不拆成 7 列：算法升级时不需要迁移。
-- 7. duration_ms 存「重读花了多久」，**只用于自省**（红线 11 明文禁止排名/打卡）。
--
-- ⭐ `lessons` 表**没有 decision_id**：教训属于哪次决策可以 join `reviews` 得到。
-- 存一份就是多一份可能与第一份不一致的副本 —— 那正是这套 append-only 纪律要防的
-- 东西，只是换了个新地方。这是本轮设计**比直觉更小**的一处。

CREATE TABLE lessons (
    lesson_id  TEXT    NOT NULL PRIMARY KEY,
    review_id  TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    CONSTRAINT lessons_id_check
        CHECK (GLOB('lesson_[0-9]*', lesson_id)),
    CONSTRAINT lessons_review_required_check
        CHECK (length(trim(review_id)) > 0),
    -- 正文按原样存（notes 同样不 trim），空的是用 trim 判的：一条全空格的教训
    -- 不是教训。
    CONSTRAINT lessons_content_required_check
        CHECK (length(trim(content)) > 0),
    CONSTRAINT lessons_content_length_check
        CHECK (length(content) <= 1000),
    CONSTRAINT lessons_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at),
    -- ⭐ RESTRICT，不是 CASCADE：一次复盘被删掉，挂在它上面的教训不该跟着消失。
    -- 那条教训是读者自己的判断，而复盘是它的**证据** —— 证据没了不等于事实没了。
    FOREIGN KEY (review_id) REFERENCES reviews(id) ON DELETE RESTRICT
) STRICT;

-- ⭐ **教训不可变 是结构性的，不是约定。**
--
-- 本迁移的全部推理建在一件事上：**教训不可变 ⇒ 不需要 `reset`**，
-- 所以 `lesson_reviews` 只有三个 outcome。但那句话每一个字都落在「教训不可变」上，
-- 而不可变一开始只是一个**约定**：一个未来的 `update_lesson()` 会改掉正文，
-- 把 FSRS 的记忆强度留在**已经不存在的文本**上 —— 正是 spec 028 为笔记队列修掉的那个失败。
--
-- 和 `note_schedule` 为什么要单独建表是同一个理由：它让「笔记可变 ⇒ 需要 reset」也成为一条推理，
-- 而那一条是有力的。
CREATE TRIGGER lessons_no_update BEFORE UPDATE ON lessons
BEGIN SELECT RAISE(ABORT, 'lessons is immutable: 教训不可改——不同意就另写一条'); END;

-- 教训是读者对自己失误的记录。外键已经用 `ON DELETE RESTRICT` 阻了删它的复盘，
-- 所以不加这两个触发器的下地是：可以把教训删掉而留下复盘，记录就不再是证据了。
CREATE TRIGGER lessons_no_delete BEFORE DELETE ON lessons
BEGIN SELECT RAISE(ABORT, 'lessons is immutable: 教训不可删——它是你对那次失误的记录'); END;

CREATE TABLE lesson_schedule (
    lesson_id    TEXT    NOT NULL PRIMARY KEY,
    fsrs_card_id INTEGER NOT NULL,
    state_json   TEXT    NOT NULL,
    state        TEXT    NOT NULL,
    due_at       TEXT    NOT NULL,
    enrolled_at  TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    CONSTRAINT lesson_schedule_lesson_required_check
        CHECK (length(trim(lesson_id)) > 0),
    -- fsrs 只接受 int 的 card_id，而我们的主键是 TEXT；这是无语义内部句柄。
    CONSTRAINT lesson_schedule_fsrs_id_check
        CHECK (fsrs_card_id > 0),
    CONSTRAINT lesson_schedule_state_check
        CHECK (state IN ('learning', 'review', 'relearning', 'deferred')),
    CONSTRAINT lesson_schedule_state_json_valid_check
        CHECK (json_valid(state_json) AND json_type(state_json) = 'object'),
    CONSTRAINT lesson_schedule_due_at_check
        CHECK (length(trim(due_at)) > 0),
    CONSTRAINT lesson_schedule_enrolled_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', enrolled_at) = enrolled_at),
    CONSTRAINT lesson_schedule_updated_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', updated_at) = updated_at),
    CONSTRAINT lesson_schedule_updated_not_before_enrolled_check
        CHECK (updated_at >= enrolled_at),
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id) ON DELETE CASCADE
) STRICT;

-- 到期队列的主查询路径：due_at <= as_of。
CREATE INDEX idx_lesson_schedule_due ON lesson_schedule(due_at);

CREATE TABLE lesson_reviews (
    id          TEXT    NOT NULL PRIMARY KEY,
    lesson_id   TEXT    NOT NULL,
    outcome     TEXT    NOT NULL,
    rating      TEXT,
    reviewed_at TEXT    NOT NULL,
    duration_ms INTEGER,
    from_due_at TEXT    NOT NULL,
    to_due_at   TEXT    NOT NULL,
    from_state  TEXT    NOT NULL,
    to_state    TEXT    NOT NULL,
    CONSTRAINT lesson_reviews_id_check
        CHECK (GLOB('lesson_review_[0-9]*', id)),
    CONSTRAINT lesson_reviews_lesson_required_check
        CHECK (length(trim(lesson_id)) > 0),
    -- ⭐ **三个值，没有 'reset'。** 理由见文件头第 3 条：教训不可变。
    CONSTRAINT lesson_reviews_outcome_check
        CHECK (outcome IN ('enrolled', 'reviewed', 'deferred')),
    CONSTRAINT lesson_reviews_rating_shape_check
        CHECK (rating IS NULL OR rating IN ('again', 'hard', 'good', 'easy')),
    -- 条件必填（ADR-0016 标准写法，不用 CASE WHEN）：只有真复习才有评分。
    CONSTRAINT lesson_reviews_reviewed_needs_rating_check
        CHECK (outcome != 'reviewed' OR rating IS NOT NULL),
    -- ⭐ 入队那一次**没有评分、没有耗时**：红线让入队成为强制，而被强制入队的用户
    -- 还没有回忆过任何东西。记一个 'good' 上去等于替他作了一次他没做的判断。
    CONSTRAINT lesson_reviews_enrolled_has_no_rating_check
        CHECK (outcome != 'enrolled' OR rating IS NULL),
    CONSTRAINT lesson_reviews_enrolled_has_no_duration_check
        CHECK (outcome != 'enrolled' OR duration_ms IS NULL),
    -- 推迟同样没有评分、没有耗时：那是「还没想清楚」，不是一次失败。
    CONSTRAINT lesson_reviews_deferred_has_no_rating_check
        CHECK (outcome != 'deferred' OR rating IS NULL),
    CONSTRAINT lesson_reviews_deferred_has_no_duration_check
        CHECK (outcome != 'deferred' OR duration_ms IS NULL),
    -- 「未成熟留空，绝不填 0」（红线 6）：耗时要么有值要么为 NULL。
    -- ⭐ 上面四条说的是耗时**能不能存在**（入队、推迟都不行），
    -- 这条说的是存在时**必须是什么**。两个问题，只有一个是冗余的
    -- （被删掉的那条「只有真复习才可能带耗时」就是第三份副本）。
    -- 没有它，一行 ``duration_ms = -5`` 就能进库。同规则 0005 / 0009 都有。
    CONSTRAINT lesson_reviews_duration_positive_check
        CHECK (duration_ms IS NULL OR duration_ms > 0),
    CONSTRAINT lesson_reviews_reviewed_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', reviewed_at) = reviewed_at),
    CONSTRAINT lesson_reviews_from_state_check
        CHECK (from_state IN ('learning', 'review', 'relearning', 'deferred')),
    CONSTRAINT lesson_reviews_to_state_check
        CHECK (to_state IN ('learning', 'review', 'relearning', 'deferred')),
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_lesson_reviews_lesson ON lesson_reviews(lesson_id);
CREATE INDEX idx_lesson_reviews_reviewed_at ON lesson_reviews(reviewed_at);

CREATE TRIGGER lesson_reviews_no_update BEFORE UPDATE ON lesson_reviews
BEGIN SELECT RAISE(ABORT, 'lesson_reviews is append-only: 教训复习流水不可修改'); END;

CREATE TRIGGER lesson_reviews_no_delete BEFORE DELETE ON lesson_reviews
BEGIN SELECT RAISE(ABORT, 'lesson_reviews is append-only: 教训复习流水不可删除'); END;

-- ⭐ 转卡是一行**事实**，不是一个状态字段。
--
-- 「这条教训已经变成卡片了」不能是 `lessons` 上的一个列，因为教训不可变（那是
-- 上面的第 3 条推出来的）。写成一行，它就是 append-only 的证据；而「已转过」这个
-- 信息在几个月后仍然可查，而不是只存在于某次变更日志里。
--
-- 两个唯一约束是这张表最强的部分：
--   · lesson_id 是主键  -> 「每条教训最多转一次」是**键本身**，不是 somebody 记得
--     跑的检查；
--   · card_id UNIQUE    -> 「一张卡片只来自一条教训」，所以不会有两张卡片同时声称
--     同一份出处。
CREATE TABLE lesson_promotions (
    lesson_id   TEXT NOT NULL PRIMARY KEY,
    card_id     TEXT NOT NULL UNIQUE,
    promoted_at TEXT NOT NULL,
    CONSTRAINT lesson_promotions_lesson_id_check
        CHECK (GLOB('lesson_[0-9]*', lesson_id)),
    CONSTRAINT lesson_promotions_card_id_check
        CHECK (GLOB('card_[0-9]*', card_id)),
    CONSTRAINT lesson_promotions_promoted_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', promoted_at) = promoted_at),
    -- ⭐ RESTRICT 两边：转过卡的教训不能被删（否则卡片失去出处），已转过的卡片也
    -- 不能被删（否则这条出处变成一个指向不存在的东西的承诺）。
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id) ON DELETE RESTRICT,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX idx_lesson_promotions_card ON lesson_promotions(card_id);

CREATE TRIGGER lesson_promotions_no_update BEFORE UPDATE ON lesson_promotions
BEGIN SELECT RAISE(ABORT, 'lesson_promotions is append-only: 转卡记录不可修改'); END;

CREATE TRIGGER lesson_promotions_no_delete BEFORE DELETE ON lesson_promotions
BEGIN SELECT RAISE(ABORT, 'lesson_promotions is append-only: 转卡记录不可删除'); END;
