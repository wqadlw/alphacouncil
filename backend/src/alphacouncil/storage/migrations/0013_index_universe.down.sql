-- 0013 · 回滚：删掉两张成分表
--
-- ⚠️ 为什么这一份可以是 non-destructive
--
-- `0002_market_cache` 的 down_note 是「只丢弃可再生缓存，用户记录不受影响」，
-- 而 `0011_financial_reports` 必须标 destructive —— 因为公司重述过的那些历史版本
-- **再抓不回来了**（抓到的永远是重述后的）。
--
-- ⭐ 本表的数据是**可再生的**：成分史是按日期查出来的，重跑一次扫描会得到同样的
-- 观察窗口（§ 时点性成立，所以「2025-06-16 那天的名单」今天查还是那份）。
-- ⇒ 所以标 `destructive_down: false`，代价写在下面。
--
-- ⚠️ **但它不是零代价，说清是哪一种**：
-- 1. 重跑扫描会重新出网 1083 次，约 45 分钟（实测），而 §2.5 记录了这个源会断连。
-- 2. ⚠️ **实测那个源有洞**：`2007-07-23` 返回成功且零行（那一格没有入库批次）。
--    重跑会**再遇到同一个洞**，而洞的那一格仍然是空的 —— 所以这一点是可重复的。
-- 3. ⭐ **`failures` 计数会归零重数。** 如果上一次扫描有 12 个失败格、这一次因网络
--    原因跳过了 40 个，「我们知道了多少」这个历史就变了。⇒ 那是一个**关于我们知道
--    多少**的损失，而它不是可再生的。

DROP TRIGGER IF EXISTS index_constituents_no_update;
DROP TRIGGER IF EXISTS index_constituents_no_delete;
DROP TRIGGER IF EXISTS index_universe_sweeps_no_update;
DROP TRIGGER IF EXISTS index_universe_sweeps_no_delete;

DROP INDEX IF EXISTS idx_index_constituents_grid;
DROP INDEX IF EXISTS idx_index_constituents_code;
DROP INDEX IF EXISTS idx_index_universe_sweeps_latest;

DROP TABLE IF EXISTS index_universe_sweeps;
DROP TABLE IF EXISTS index_constituents;