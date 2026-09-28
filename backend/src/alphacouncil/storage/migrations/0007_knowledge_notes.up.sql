-- 0007 · knowledge_notes：知识笔记、标签与互链（spec 026）
--
-- 为什么这三张表存在：
-- 知识层此前只有 `cards` 一张表，而它的每一行都被三条硬约束锁死：
--   source_url 必填（http/https）、source_title 必填、symbols 前端硬编码一只票。
-- 于是"流动性收紧时周期股先跌"（宏观）、"我的估值框架"（方法论）、
-- "我第 3 次因为只看 PE 错过"（经验）——**全都记不下来**。
-- 结果是这个产品能"复习知识"却没有"记录知识"的能力：它有一个队列，没有一个知识库。
--
-- ⭐ **provenance rule 一点没有放松。**
-- `cards` 仍然必须带来源，那条规则是对的：放松它会让"我以为我记住了，
-- 其实我在引用一段我没读过的东西"变得无法察觉。
-- 加笔记不是为了让卡片可以没有出处，**是给"确实没有出处"这件事一个正当的容器**。
-- 规范原话（基础功能打磨与AI桥接 §2.1）：「**不是**笔记。笔记可以没有来源；
-- **卡片必须有**」—— 卡片与笔记是两种东西，这里把后者补回来。
--
-- 核心设计：
-- 1. notes 与 cards **并列**，不是它的变体。所以 notes 没有 claim_type
--    （笔记不是主张，没有"支持/质疑"）、没有 status（收敛是对主张的处置）。
-- 2. body 是 **Markdown 原文**，原样存原样取：不 trim、不规范化、不转义。
--    任何"顺手清理一下"都会让用户下次打开看到自己没写过的话。
-- 3. note_tags **一表多行，不塞逗号串**。这是本文件最容易被"优化"掉的一处：
--    逗号串会让 `WHERE tag LIKE '%宏观%'` 命中 `宏观债` —— 一个查标签
--    查出了错误结果的 bug，而且它只在标签前缀重叠时才发作。
-- 4. note_links 是**互链骨架**，目标可以是笔记/卡片/决策/标的/教训。
--    ⭐ 不给 to_id 加外键：那五类主键分属五张表，SQLite 无法对多态外键建约束，
--    与其写一个永远不生效的 REFERENCES，不如**把校验放在仓储层并用测试钉住**。
--    （这是本文件唯一一处"约束在 Python 而不在 SQL"，明确记在这里。）
-- 5. 没有 note_schedule。笔记的复习队列是**下一轮**（spec 026 §六）：
--    `domain/scheduling.py` 已经是通用的，但还需要两张表 + 一个仓储。
--    **不建用不到的表** —— 空表比缺表更坏，它会让人以为功能已经存在。

CREATE TABLE notes (
    id         TEXT    NOT NULL PRIMARY KEY,
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    as_of      TEXT,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    CONSTRAINT notes_id_check
        CHECK (GLOB('note_[0-9]*', id)),
    -- 标题必填：**空标题的笔记在列表里无法被认出**，而认出它是知识库的前提。
    -- 正文只要求非全空白，不要求非空 —— 允许先存一个标题再补正文，
    -- 那是"我先记一句免得忘了"这个真实动作。
    CONSTRAINT notes_title_required_check
        CHECK (length(trim(title)) > 0),
    CONSTRAINT notes_title_length_check
        CHECK (length(title) <= 200),
    CONSTRAINT notes_body_not_blank_check
        CHECK (length(trim(body)) > 0),
    -- as_of 是"数据截至哪天"，不是"我什么时候写的"。PIT 纪律（宪法 4.2）在
    -- 笔记上同样成立：「截至 2026-08 的渠道库存」与「我 2026-09 记的」是两件事，
    -- 混起来会让半年后的自己误以为当时就能看到后来的数据。
    -- ⭐ 它必须落库：`NoteRow.as_of` 在 dataclass 里，不建这一列，
    -- 它就是一个**永远返回 None 的字段** —— 那比没有这个字段更坏，
    -- 因为调用方会把"没有 as_of"读成"确实没有数据截止日"。
    CONSTRAINT notes_as_of_check
        CHECK (as_of IS NULL OR strftime('%Y-%m-%d', as_of) = as_of),
    CONSTRAINT notes_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at),
    CONSTRAINT notes_updated_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', updated_at) = updated_at),
    CONSTRAINT notes_updated_not_before_created_check
        CHECK (updated_at >= created_at)
) STRICT;

CREATE INDEX idx_notes_created_at ON notes(created_at);
CREATE INDEX idx_notes_updated_at ON notes(updated_at);

-- 笔记可以挂标的地，也可以一个都不挂（宏观 / 方法论就没有标的）。
-- ⭐ 与 note_links 的**不对称是刻意的**：这里有真实的复合外键，数据库能管；
-- note_links 指向五张表，SQLite 管不了，所以那个校验放在 Python 层。
CREATE TABLE note_note_symbols (
    note_id    TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    market     TEXT NOT NULL,
    code       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (note_id, market, code),
    FOREIGN KEY (market, code) REFERENCES instruments(market, code) ON DELETE RESTRICT,
    CONSTRAINT note_note_symbols_market_check
        CHECK (market IN ('sh', 'sz', 'bj')),
    CONSTRAINT note_note_symbols_code_check
        CHECK (GLOB('[0-9][0-9][0-9][0-9][0-9][0-9]', code)),
    CONSTRAINT note_note_symbols_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at)
) STRICT;

CREATE INDEX idx_note_note_symbols_instrument ON note_note_symbols(market, code);

CREATE TABLE note_tags (
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    PRIMARY KEY (note_id, tag),
    CONSTRAINT note_tags_tag_required_check
        CHECK (length(trim(tag)) > 0),
    -- 40 字符：够写「白酒/渠道库存」这类标签，又短到能在列表里一行显示。
    CONSTRAINT note_tags_tag_length_check
        CHECK (length(tag) <= 40),
    -- ⭐ 标签里不许有逗号：逗号串是本文件明确拒绝的形状，禁掉它，
    -- 一个"顺手改成逗号串"的迁移就写不出来了。
    CONSTRAINT note_tags_no_comma_check
        CHECK (instr(tag, ',') = 0),
    -- 去掉首尾空白后必须与原值相同：标签是集合成员，不该有两个长得一样的。
    CONSTRAINT note_tags_trimmed_check
        CHECK (tag = trim(tag))
) STRICT;

-- 反查用：一个标签下有哪些笔记。没有这个索引，按标签筛选就是全表扫。
CREATE INDEX idx_note_tags_tag ON note_tags(tag);

CREATE TABLE note_links (
    from_note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    to_kind      TEXT NOT NULL,
    to_id        TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (from_note_id, to_kind, to_id),
    CONSTRAINT note_links_to_kind_check
        CHECK (to_kind IN ('note', 'card', 'decision', 'instrument', 'lesson')),
    CONSTRAINT note_links_to_id_required_check
        CHECK (length(trim(to_id)) > 0),
    CONSTRAINT note_links_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at),
    -- 不许自链。允许它没有任何用处，只会让"这条笔记引用了自己"这种脏数据
    -- 在图谱里变成一个自指的圈。
    CONSTRAINT note_links_no_self_check
        CHECK (NOT (to_kind = 'note' AND to_id = from_note_id))
) STRICT;

CREATE INDEX idx_note_links_to ON note_links(to_kind, to_id);
