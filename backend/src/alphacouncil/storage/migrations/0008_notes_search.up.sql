-- 0008 · notes_search：知识库全文检索（spec 027）
--
-- 为什么这张表存在：
-- spec 026 补上了「记录知识」的能力，但**记了却找不到**。
-- `references/research/02` 说得直接：「真正难的不是"能链接"，是"链接什么"」——
-- 而比链接更难的是「你三个月前写的那句判断现在在哪」。
-- 一个只能列出、不能检索的知识库，规模一大就等于没有。
--
-- ⭐ 为什么是 FTS5 而不是 `LIKE`：
-- FTS5 是 SQLite **内置**的（`sqlite3.sqlite_version >= 3.53.1` 实测），
-- 零依赖 —— 不引入任何库，不违反宪法 §3.2.1 的依赖预算。
-- 实测版本：SQLite 3.53.1 · FTS5 available · trigram tokenizer available。
--
-- ⭐⭐ 为什么 `tokenize='trigram'`：中文没有空格。
-- 默认的 `unicode61` 会把一整段 CJK 当**一个** token，于是
-- `MATCH '流动性'` 什么也匹配不到。`trigram` 索引**重叠的 3 字序列**，
-- 是 SQLite 官方给 CJK 的答案（3.34+）。
--
-- ⭐⭐⭐ **但 trigram 有 3 个字的下限，而中文最常搜的就是两个字**。实测：
--     2 chars  MATCH '利率'   -> 0 hit(s)      ⭐
--     2 chars  MATCH '白酒'   -> 0 hit(s)      ⭐
--     2 chars  MATCH '估值'   -> 0 hit(s)      ⭐
--     3 chars  MATCH '现金流' -> 1 hit(s)
-- 「利率」「白酒」「估值」「宏观」「渠道」全是两个字，**而那恰好是这个领域里
-- 最自然的检索词**。一个对「利率」返回空结果的搜索框，比没有搜索框更坏：
-- 没有搜索框，用户知道没有；搜索框返回空，用户会以为**那条笔记不存在** ——
-- 而那条笔记可能就在屏幕上。
-- → 仓储里 **≥3 字走本表，<3 字走 LIKE**，两条路都有测试。
-- `LIKE` 在这个规模下不是妥协：宪法 §规模是「个人级几千张卡」，
-- 几千条 × 约 1KB ≈ 1–2 MB 全表扫，SQLite 里是亚毫秒级。
-- FTS5 的价值是「不随规模线性劣化」，不是「LIKE 慢到不能用」。
--
-- ⭐ 为什么索引由**触发器**维护，不由仓储维护：
-- 1. 仓储里手写 `INSERT INTO notes_fts`，就多了一条「绕过仓储直接写库」的路，
--    而那条路**没人会记得同步索引**。触发器对每条写路都生效。
-- 2. 索引不同步是这个功能**最坏的失败方式**：笔记就在屏幕上，搜索说它不存在。
-- 3. `test_the_index_follows_an_edit` 钉的就是这个：编辑后**旧词搜不到、新词搜得到**。
--
-- ⭐ 为什么 UPDATE 触发器是「先 DELETE 再 INSERT」而不是 UPDATE：
-- **FTS5 虚拟表不支持 UPDATE**。只插不删会留下一条「正文已改、索引仍是旧文」
-- 的行，而那种行搜旧词会命中、搜新词搜不到 —— 看起来像随机丢结果，很难归因。
--
-- ⭐ 为什么不用 `bm25()` 相关度排序：
-- 列表的顺序是 `updated_at DESC`，这是一个**承诺**（笔记库的价值是「我最近写了
-- 什么」，不是「哪条最匹配」）。打了字就换成相关度排序，会让同一批数据
-- **因输入长短呈现两种顺序** —— 那种「说不清哪里怪」的不一致比没有排序更坏。
-- → 检索**只过滤，不重排**。`bm25()` 存在且可用（实测），这里主动不用。

CREATE VIRTUAL TABLE notes_fts USING fts5(
    note_id UNINDEXED,
    title,
    body,
    tokenize='trigram'
);

-- ⭐ `note_id` 必须 UNINDEXED：它是回查 notes 的连接键，不是搜索对象。
-- 把它也索引进去意味着「搜一个 note_1789…」能命中，而没有人会搜一个 id。

CREATE TRIGGER notes_fts_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts (note_id, title, body)
    VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER notes_fts_ad AFTER DELETE ON notes BEGIN
    DELETE FROM notes_fts WHERE note_id = old.id;
END;

CREATE TRIGGER notes_fts_au AFTER UPDATE ON notes BEGIN
    DELETE FROM notes_fts WHERE note_id = old.id;
    INSERT INTO notes_fts (note_id, title, body)
    VALUES (new.id, new.title, new.body);
END;
