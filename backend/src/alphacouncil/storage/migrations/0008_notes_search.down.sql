-- 0008 · notes_search：回滚（spec 027）
--
-- ⚠️ destructive_down = false，**这是本项目第一次在 notes 上给出可逆的结论**。
--
-- 理由：`notes_fts` 是**派生索引**，它的每一个字节都能从 `notes` 重新算出来
-- （`INSERT INTO notes_fts SELECT id, title, body FROM notes`）。
-- 丢掉索引只是丢掉了检索能力，**用户写下的文字一个字都不会少** ——
-- 而 0007 的 down 会删掉笔记本身，所以那一条必须 destructive。
--
-- **「可逆」不等于「便宜」**：重建索引是 O(总字数)。所以回滚这一条仍然
-- 需要人明确决定，而 `destructive_down: false` 记录的是「用户数据不会丢」
-- 这件事本身，不是「随便跑一下没关系」。

DROP TRIGGER IF EXISTS notes_fts_au;
DROP TRIGGER IF EXISTS notes_fts_ad;
DROP TRIGGER IF EXISTS notes_fts_ai;

DROP TABLE IF EXISTS notes_fts;
