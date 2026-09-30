-- 0012 · down：删掉 notifications_sent
--
-- 一次不可逆的删除：全部「我们说过什么」的记录消失。工具默认要求 --allow-destructive。
--
-- ⚠️ 与 financial_reports 的 down 不同，那一条丢的是可重新抓的数据；
-- ⭐ **这一条丢的是「用户收到过什么」这份证据本身**，而且重抓不回来 ——
-- 一行删掉之后，同一条判据会**再次**被通知，而用户上一次已经看过了。
DROP TABLE notifications_sent;
