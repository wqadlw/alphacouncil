-- 0014 的回滚：⭐⭐ **删除整张 `decision_scratch_events`。** ⭐⭐
--
-- ⭐⭐ **这丢的是读者自己按下的动作，⭐⭐ 所以 `destructive_down: true`。** ⭐⭐
-- ⭐⭐ 理由与 0012 `notifications_sent` 同族：⭐⭐ 那一行记的是「我标记过这条」，
-- ⭐⭐ 删掉之后**没法重新推导** —— ⭐⭐ 因为它是**他的动作**，⭐⭐ 而不是我们算出来的东西。
-- ⭐⭐ ⇒ 回滚会让一条被他自己声明为「试验记录」的决策，⭐⭐ 重新进入今日页的队列
-- ⭐⭐ 和复盘的四象限，⭐⭐ **而他当时按下开关的理由已经不在任何地方了。**
--
-- ⭐⭐ `decisions` / `reviews` / `decision_review_state` **都不受影响。**

DROP INDEX decision_scratch_events_by_decision;

DROP TRIGGER decision_scratch_events_no_delete;
DROP TRIGGER decision_scratch_events_no_update;

DROP TABLE decision_scratch_events;