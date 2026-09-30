-- 0012 · notifications_sent：我们对用户说过什么（spec 044）
--
-- 为什么这张表存在：
-- spec 033 §一 指出「两个承诺都只兑现了一半：排程存在，然后程序等着你去打开那个页面」。
-- 而「等你打开」这件事的另一半是**只说一次**：用户跑两次 `send_due` 就该收到两条一样的话。
--
-- 1. ⭐⭐ **这张表不是缓存，而它长得太像缓存。**
--    ADR-0031 的判定表里写着「缓存 | ⭐ **不要 —— 有害** | 要」，理由是：
--    「⭐ 如果当初没有把 webhook 塞进行情层，就不会有人试图让通知继承数据缓存。
--      那个继承一旦写进去，几乎不可能被审出来 —— 它长得太像『复用了已有的好机制』。」
--    本表记的是「关于**这一件事**，我已经说过了」，不是「我们 5 分钟前取过这个数」。
--    ⭐ 两者都叫「避免重复」，而混起来的后果是同一条：**一条提醒被悄悄丢掉，且看不出丢了**。
--
-- 2. ⭐ **只在送达时写入。**
--    一次投递失败不是「我们说过了」——它是传输层事实，structlog 已经记了。
--    ⭐ 若把失败也写进来，那些行会**永远堆积且永不清理**，
--    而 append-only 又不许 UPDATE 清掉它们。
--    ⭐ 代价要说清：**这张表回答不了「上周那次投递成功了吗」**。
--    它回答的是产品真正要回答的那一个：**「关于这件事，我说过没有」**。
--
-- 2b. ⭐⭐ **本表没有 `delivered` 列。**
--    第一版有，且只有 1 一个合法值，而那一列旁边还写了一段注释解释为什么留着它
--    （「让『成功』成为数据里的一件事，而不是代码里的一个 if」）。
--    ⭐ `constraints.json` 的**形状检查**立刻报出它不属于任何类别——
--    `comparison` 要 `>=`/`>`/`<=`/`BETWEEN`，`forbidden_value` 要 `instr(`，
--    而 `= 1` 两样都不是。⭐ 那个报错是对的：**一个只有一种合法取值的列不是数据，是常量**，
--    ⭐ 而我写的那段注释正是在替一个常量辩护。
--    ⭐ 真要记录失败时再加，那时它会有第二种取值，也就真的成了数据。
--
-- 3. ⭐⭐ **指纹只认判据，不认判据的结论。**
--    主键是 `(channel, fingerprint)`，而 fingerprint 覆盖
--    `(kind, decision_id, metric, operator, threshold, as_of)`，**不含结论**。
--    ⭐ 所以同一条判据只会被说一次：它 `crossed` 之后又 `not_crossed`（价格跌回去了）
--    **不会再发第二条**。⭐ 那不是漏掉，那是「异动提醒」——红线 8 禁的那一类，
--    ⭐ 而且重复发送的代价由用户承担（红线 11「不鼓励频繁操作」）。
--    ⭐ 反过来，`warming → crossed` 会发第一条（因为从未发过），
--    这正是我们想要的：第一次越过必须是新的消息。
--
-- 4. ⭐ **三个「我们不知道」的状态根本不产生通知。**
--    `warming` / `undetermined` / `no_bars` 不是拦截，是**我们没有话说**。
--    ⭐ 若为它们记录指纹，那么一条长期 `warming` 的判据会在某天越过时**永远不再通知**——
--    因为「我已经说过了warming」这句话，会被读成「我已经说过了」。
--    ⭐ 代价要说清：**源挂掉时用户收不到任何消息**，我们选择沉默而不是每天重复同一句
--    「取不到日线」。
--
-- 5. ⭐ **body 逐字存下来。**
--    「我们当时到底说了什么」必须可查。⭐ 这也是把文案从 TypeScript 搬进
--    `domain/criterion_sentence.py` 的第二个理由：不存下来的话，
--    有一天我们会想知道用户收到的那一句和今天渲染的那一句是不是同一句。
--
-- 6. ⭐ append-only，且理由不是「因为它是日志表」：
--    ⭐ **删除这一行 = 让「我们说过」变成没说过**，而那会让同一条判据被反复打扰，
--    或者让一条已经被处理的判据重新冒出来。

CREATE TABLE notifications_sent (
    -- ⭐ 通道名，不是表名的一部分：同一个事实经邮件和 webhook 各说一次，
    -- 是两件不同的事（用户可能只配了一个）。
    channel       TEXT    NOT NULL,
    -- ⭐ SHA-256 的十六进制。**不存原始字段**，因为「同一件事」的定义会变，
    -- 而历史行不该因为定义变了就变得不可解释。
    fingerprint   TEXT    NOT NULL,
    kind          TEXT    NOT NULL CHECK (length(trim(kind)) > 0),
    -- ⭐ 人读的：一行标识这次说的是关于什么的。取标的的全码，如 `600519.SH`。
    subject       TEXT    NOT NULL CHECK (length(trim(subject)) > 0),
    -- ⭐ 逐字存下来的那句话。见文件头第 5 条。
    body          TEXT    NOT NULL CHECK (length(trim(body)) > 0),
    sent_at       TEXT    NOT NULL,
    -- ⭐ **具名**约束，与 `0011_financial_reports` 同一写法。
    -- ⭐ 第一版用的是内联 `CHECK (...)`，而 `constraints.json` 的比对按
    -- 「具名约束」进行 —— ⭐ 于是这五条约束对台账完全不存在，`test_storage.py` 立刻报出
    -- 「notifications_sent is missing from the schema」。⭐ 具名不是啰嗦，是让它们**能被检查**。
    CONSTRAINT notifications_sent_kind_check
        CHECK (length(trim(kind)) > 0),
    CONSTRAINT notifications_sent_subject_check
        CHECK (length(trim(subject)) > 0),
    CONSTRAINT notifications_sent_body_check
        CHECK (length(trim(body)) > 0),
    CONSTRAINT notifications_sent_sent_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', sent_at) = sent_at),
    PRIMARY KEY (channel, fingerprint)
) STRICT;

-- ⭐ 「关于这件事我说过没有」——这是热路径上的那一个查询，
-- 所以索引就是它：先按通道，再按指纹。
-- ⭐ PK (channel, fingerprint) **已经**覆盖它，因此不另建索引：
-- ⭐ 多一个索引就多一个要维护、要变慢、并在 schema 变更时可能忘记的东西。
CREATE INDEX idx_notifications_sent_recent
    ON notifications_sent(channel, sent_at DESC);

-- ⭐ 「上周都说了什么」——给人看的，所以按时间排，且不参与热路径。
CREATE INDEX idx_notifications_sent_sent_at
    ON notifications_sent(sent_at DESC);

CREATE TRIGGER notifications_sent_no_update BEFORE UPDATE ON notifications_sent
BEGIN SELECT RAISE(ABORT, 'notifications_sent is append-only: 改写「已经说过」就是改写用户收到过的历史'); END;

CREATE TRIGGER notifications_sent_no_delete BEFORE DELETE ON notifications_sent
BEGIN SELECT RAISE(ABORT, 'notifications_sent is append-only: 删掉一行会让同一条判据被反复打扰'); END;
