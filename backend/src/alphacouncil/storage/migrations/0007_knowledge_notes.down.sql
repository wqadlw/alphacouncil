-- 0007 · knowledge_notes：回滚（spec 026）
--
-- ⚠️ destructive_down = true。
-- notes / note_tags / note_links 里全是**只有用户有、任何数据源都算不出来**的东西：
-- 他自己写下的文字。回滚这个迁移就是**删掉他的笔记**，无法从任何快照之外恢复。
--
-- 迁移器在未显式传 --allow-destructive 时拒绝执行它（ADR-0012 规则 2：
-- 确实不可逆时必须显式声明，而不是假装可逆）。

DROP INDEX IF EXISTS idx_note_links_to;
DROP INDEX IF EXISTS idx_note_tags_tag;
DROP INDEX IF EXISTS idx_notes_updated_at;
DROP INDEX IF EXISTS idx_notes_created_at;
DROP INDEX IF EXISTS idx_note_note_symbols_instrument;

DROP TABLE IF EXISTS note_links;
DROP TABLE IF EXISTS note_tags;
DROP TABLE IF EXISTS note_note_symbols;
DROP TABLE IF EXISTS notes;
