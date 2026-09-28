-- 0010 · down：删掉教训的四张表
--
-- 删 `lesson_promotions`（无被引用）→ `lesson_reviews` → `lesson_schedule` →
-- `lessons`。
--
-- 顺序不能反：`lessons` 被前两张表外键引用，而 `lesson_promotions` 同时引用
-- `cards`（0003）—— **不回滚 `cards`**。这是一次不可逆的删除：教训、它的复习流水、
-- 它的调度项，以及所有「这条教训已经变成卡片」的记录全部消失。工具默认要求
-- --allow-destructive。
DROP TABLE lesson_promotions;
DROP TABLE lesson_reviews;
DROP TABLE lesson_schedule;
DROP TABLE lessons;
