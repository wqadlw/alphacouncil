-- 0004 回滚：删除卡片状态事件流（不影响 cards 内容）
DROP TRIGGER IF EXISTS card_events_no_delete;
DROP TRIGGER IF EXISTS card_events_no_update;
DROP TABLE IF EXISTS card_events;
