-- 0006 down · 丢弃复盘
--
-- destructive：`reviews`（全部复盘流水）与 `decision_review_state`（到期与已复盘状态）
-- 都会消失。`decisions` 不受影响 —— 用户当初写下的原始记录还在，
-- **但"我复盘过"这件事没了**。而那正是这张表存在的理由。
-- 要退回请从 VACUUM INTO 快照恢复，不要跑这个文件。

DROP TRIGGER reviews_no_delete;
DROP TRIGGER reviews_no_update;
DROP INDEX idx_reviews_reviewed_at;
DROP INDEX idx_reviews_decision;
DROP TABLE reviews;
DROP INDEX idx_decision_review_state_due;
DROP TABLE decision_review_state;
