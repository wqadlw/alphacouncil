-- 0009 · note_schedule：回滚（spec 028）
--
-- ⚠️ destructive_down = true
--
-- notes / note_note_symbols / note_tags / note_links **全部不受影响** ——
-- 用户的笔记一个字都不会少，这条与 0008 不同（0008 丢的只是可重建的索引）。
--
-- 丢的是「笔记的复习史」：note_reviews 里每一条**重读、评分、推迟、重写**的记录。
-- 而本产品的核心命题是「投资无法从经验中学习，因为没有记录」——
-- 学习的尝试史就是产品本身。**回滚这一条就是删掉那份史。**
--
-- 迁移器在未显式传 --allow-destructive 时拒绝执行它（ADR-0012 规则 2）。

DROP INDEX IF EXISTS idx_note_reviews_reviewed_at;
DROP INDEX IF EXISTS idx_note_reviews_note;
DROP INDEX IF EXISTS idx_note_schedule_due;

DROP TRIGGER IF EXISTS note_reviews_no_delete;
DROP TRIGGER IF EXISTS note_reviews_no_update;

DROP TABLE IF EXISTS note_reviews;
DROP TABLE IF EXISTS note_schedule;
