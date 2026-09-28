-- 0005 down · 丢弃复习排程
--
-- destructive：card_schedule（每张卡的当前排程）与 card_reviews（全部复习流水）都会消失。
-- cards / card_events 不受影响 —— 卡还在，来源与生命周期历史还在，
-- **只是「这张卡什么时候该复习、复习过几次」没有了**。那正是这批数据不可替代的地方，
-- 所以要退回请从 VACUUM INTO 快照恢复，不要跑这个文件。

DROP TRIGGER card_reviews_no_delete;
DROP TRIGGER card_reviews_no_update;
DROP INDEX idx_card_reviews_reviewed_at;
DROP INDEX idx_card_reviews_card;
DROP TABLE card_reviews;
DROP INDEX idx_card_schedule_due;
DROP TABLE card_schedule;
