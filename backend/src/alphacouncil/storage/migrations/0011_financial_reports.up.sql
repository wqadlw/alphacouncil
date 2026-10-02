-- 0011 · financial_reports：PIT 财务数据（spec 043 · D4）
--
-- 为什么这张表存在：
-- 主人的原话是「财务数据源也很重要」，而 `constitution.md` 早在 spec 001 就为它写好了规则，
-- 只是一直没有实现的数据源。`status.md` 的「公告与财务数据源未接入（D4 / D5）」就是这一行。
--
-- 1. ⭐ **主键带 `announced_at`，因为公司会重述。**
--    §4.4：「历史财务数据不得被后续修订覆盖 —— 保留 `announced_at`，按
--    `announced_at <= as_of` 查询」。一家公司可以重述某个季度的财报，而重述是
--    **一个更晚的 `announced_at` 的新版本**。如果主键只有 (market, code, period_end)，
--    重述就只能**覆盖**原值 —— 而 2024-01-01 看到的和 2024-06-01 看到的必须是两个不同的数：
--    第二个人看到的是被重述过的数字，回看第一段历史的人应该看到当时那个。
--    ⭐ **两个版本并存，查询按 `announced_at <= as_of` 取最新。这就是 PIT 的定义，
--    也是这张表存在的全部理由。**
-- 2. ⭐ **主键是 `(market, code)` 而不是 `code`** —— 红线 15，因为 `000001` 在沪市是
--    上证指数、在深市是平安银行，**代码→市场是一对多**。这条写进了 CHECK 而不是靠
--    约定，因为约定正是要防的东西。
-- 3. ⭐ **`period_end` 与 `announced_at` 分开两个列，不是合成一个日期** —— 红线 17。
--    合成一个就分不出「这份报告说的是哪段时间」和「你什么时候才知道它」。
-- 4. ⭐ **`source` 存是谁给的**，而**不存**「我们信不信它」。来源是事实，信任是判断，
--    而这张表只该存事实。
-- 5. ⭐ **`fetched_at` 记的是**我们什么时候抓到的**，不是公告日。两者可能差两个月
--    （实测：baostock 的季报数据滞后约 2 个月），⇨ 混为一谈会让 PIT 查询把「我们知道
--    的时候」当成「它公开的时候」。
-- 6. ⭐ **本表 append-only。** 触发器不是「因为日志表要加触发器」，而是红线 17 的
--    直接后果：**一次 UPDATE 就是一次静默的重写历史**，而 PIT 的全部价值在于
--    「当时看到的就是当时的」。
-- 7. ⭐ **指标列全部可空，且没有默认值。** 红线 6：未成熟结果留空，绝不填 0。
--    一家刚上市的公司没有 `gpMargin`，而 `0.0` 会说「它的毛利率是零」。
-- 8. 一次 `query_profit_data` 返回 10 个指标（spec 043 §三）—— 所以**一张宽表**，
--    而不是「一个指标一张表」。理由是节流：一次往返十个数，而拆成十张表就是十次往返。

CREATE TABLE financial_reports (
    market       TEXT    NOT NULL,
    code         TEXT    NOT NULL,
    -- ⭐ 报告期。**不是**唯一时间键的另一半 —— 同一个报告期可以有多个
    -- announced_at（见文件头第 1 条）。
    period_end   TEXT    NOT NULL,
    -- ⭐ 公告日。这是这张表存在的理由，也是 PIT 查询的 `as_of` 比较对象。
    announced_at TEXT    NOT NULL,
    -- ⭐ 一行 = 一次抓取。同一份 (period_end, announced_at) 被两个源分别报过时，
    -- 两条都在，而「我们用哪一条」是消费方的事而不是表的唯一性约束的事。
    source       TEXT    NOT NULL,
    fetched_at   TEXT    NOT NULL,
    -- ⭐ 以下八个字段来自一次 `query_profit_data`（实测 2026-09-29，sh.600519 2024Q4）。
    -- 全部可空：没有任何一个能对所有报告期成立，而 `0.0` 会说「它是零」。
    roe_avg      REAL,
    np_margin    REAL,
    gp_margin    REAL,
    net_profit   REAL,
    eps_ttm      REAL,
    revenue      REAL,
    total_shares REAL,
    float_shares REAL,
    CONSTRAINT financial_reports_symbol_check
        CHECK (market IN ('sh', 'sz', 'bj')),
    CONSTRAINT financial_reports_code_check
        CHECK (length(trim(code)) > 0),
    -- ⭐ 报告期是月末日。不是一个「大概季度末」—— 判它是因为**乱填的 period_end
    -- 会让两份不同报告期的数据看起来是同一期**，而那正是本表要防的事。
    --
    -- ⭐ **两个条件，不是一个。** 第一版只写了 GLOB，而 GLOB 只看**形状**不看**日历**：
    -- `2024-13-45` 是十个字符里的九个数字加两个横线，它稳稳通过。
    -- ⭐ 补的那半个是 `date(...) IS NOT NULL` —— SQLite 的 `date()` 对非法日期返回 NULL，
    -- 而 **CHECK 遇 NULL 判为通过**，所以必须显式断言「不是 NULL」。少了 `IS NOT NULL`
    -- 的 `date(period_end)` 是一条**永远为真**的约束。
    --
    -- ⭐ 注释放在 CONSTRAINT 之**上**而不是名字与 CHECK 之间：`tests/unit/test_storage.py`
    -- 读的是落库后的 DDL，它按 `CONSTRAINT <name> CHECK` 连续匹配。SQLite 自己不介意
    -- 中间的注释（实测落库 9 条约束全在），但那条测试代表的是本项目的**体例**，
    -- 而这份 SQL 是唯一的例外 —— 与其放宽体例，不如改成合群的那一个。
    CONSTRAINT financial_reports_period_end_check
        CHECK (period_end GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
               AND date(period_end) IS NOT NULL),
    -- ⭐ 公告日的两个条件理由**与 `period_end` 不同**，而且不是抄它：
    -- ⭐ 这一列是 PIT 查询真正拿去比较的那一列，所以它的形状**直接决定查询的正确性**。
    -- 第一版用 `strftime('%Y-%m-%d', announced_at) = announced_at`，实测 `2025/04/03` 能过 ——
    -- SQLite 把 `/` 也当日期分隔符，`strftime` 归一化之后等于原串的比较居然成立。
    -- ⭐ **一个宽松的公告日格式不是风格问题**：它让同一个报告日有两种拼法，
    -- 而 `announced_at <= ?` 是**字符串比较**，`2025-04-03` 与 `2025/04/03` 谁大取决于
    -- 字符表 —— 那等于让 PIT 的边界由运气决定。
    CONSTRAINT financial_reports_announced_at_check
        CHECK (announced_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
               AND date(announced_at) IS NOT NULL),
    -- ⭐ **公告日不早于报告期。** 一个「报告期在公告日之后」的行意味着有人在说谎，
    -- 而它是 PIT 查询的输入 —— 一条撒谎的 announced_at 会让一份还没公开的财报
    -- 在它公开之前就可被读到。
    -- ⭐ 注释掉的第二行是这一条**曾经的样子**：
    --     -- CHECK (date(announced_at) >= date(period_end))
    -- ⭐ 即便形状已被上面两条钉死，比较仍然用原字符串，因为 GLOB 保证了格式唯一，
    -- 字符串比较与日期比较此时等价 —— 而原字符串比较不需要两边的 `date()` 都是非 NULL，
    -- 一个失败的日期已经由 `announced_at_check` 挡掉了。
    CONSTRAINT financial_reports_announced_after_period_check
        CHECK (announced_at >= period_end),
    -- ⭐ 同理，`fetched_at` 是带时刻的 ISO-8601，形状必须**精确**到秒与毫秒。
    -- ⭐ `strftime('%Y-%m-%dT%H:%M:%fZ', ...) = fetched_at` 这一句本身已经既管形状又管
    -- 日历（`2026-02-30` 会归一化成 `2026-03-02` 从而对不上），所以这里只需要它一个条件。
    CONSTRAINT financial_reports_fetched_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', fetched_at) = fetched_at),
    -- ⭐ **「我们抓到它时，公告日已经过了」不是错** —— baostock 实测滞后约 2 个月，
    -- 而那份滞后是**它自己的入库延迟**，不是公告被压着。唯一的硬要求是
    -- 「抓到的时刻不早于公告的时刻」，因为在公告之前抓到它意味着我们看到的是
    -- 未来。⭐ 这里用 `date()` 而不是原字符串：抓取带时刻、公告不带，
    -- 字符串比较会因为 `'T'` 而把**同一天**判成「抓到得比公告晚」。
    CONSTRAINT financial_reports_fetched_after_announced_check
        CHECK (date(fetched_at) >= date(announced_at)),
    -- ⭐ 负的比率是可能的（亏损公司的 np_margin），所以只挡真正不可能的值。
    -- ⭐ **不挡 `0.0`** —— 一个真的为零的毛利率是数据，而「用 0 代替缺失」才是错，
    -- 而这个问题由「可空」解决，不由「值域检查」解决。红线 6 说的是后者。
    CONSTRAINT financial_reports_shares_positive_check
        CHECK (total_shares IS NULL OR float_shares IS NULL OR float_shares <= total_shares),
    -- ⭐ **`fetched_at` 也在主键里，而且这是被一个测试逼出来的。**
    --
    -- 第一版的主键到 `source` 就结束了，于是「同一天同一家源把同一份公告又报了一遍」
    -- 撞主键。⭐ 而 `INSERT OR IGNORE` **不能**用来解决它：SQLite 的 `OR IGNORE`
    -- 把**任何**约束冲突都变成静默跳过，包括上面那些 CHECK —— 于是「公告早于报告期」
    -- 这种行会被悄悄丢掉而不是被拒。
    -- ⭐ 所以正确的做法是承认「再抓一次」是一次**新的观察**，让它有自己的主键位置。
    -- 这也让下面那个索引的末位 `fetched_at` 有了意义：同一 `announced_at` 下有两个源时，
    -- 「取最新」需要一个**全序**，否则两个同值的行之间顺序由 SQLite 决定。
    PRIMARY KEY (market, code, period_end, announced_at, source, fetched_at)
) STRICT;

-- ⭐ PIT 查询的主路径：`announced_at <= as_of` 取最新。
-- ⭐ **索引顺序是 (announced_at) 在后而不是在前**，因为查询的驱动条件是
-- `market = ? AND code = ?`，而 announced_at 只是在这两行内部排序。
-- ⭐ 把它放第一位会让每一个标的的查询都扫过全表。
--
-- ⭐⭐ **末位 `fetched_at DESC` 是承重的，不是锦上添花。**
-- `announced_at` 单独**不是全序**：两家源可以在同一天发布同一份报告。
-- 变异检查把 repository 查询里的 `, fetched_at DESC` 删掉之后，测试**全部照过** ——
-- 因为 SQLite 就是沿着本索引扫描的，而本索引本身按 `fetched_at DESC` 排。
-- ⭐ 也就是说「取最新」的确定性来自**这个索引**，不是来自查询语句；两者都在时无法互相
-- 区分，删掉其中一个另一个会补上。
-- ⭐ **两个都留着**（查询显式写出来，索引让代价为零），但依赖必须写在明处：
-- 改掉末位那一列，「取最新」就不再确定了。
CREATE INDEX idx_financial_reports_pit
    ON financial_reports(market, code, announced_at DESC, fetched_at DESC);

-- 「这个票有哪些报告期」—— 目录页与「最近一期是什么期」用。
CREATE INDEX idx_financial_reports_period
    ON financial_reports(market, code, period_end DESC);

-- ⭐ **append-only 是结构性的，不是约定。**
--
-- 红线 17 / §4.4 的要求是「不得被后续修订覆盖」，而一句写在文档里的要求拦不住
-- 一条 `UPDATE`。⭐ 更要紧的是：**一次 UPDATE 是一次静默的重写历史**，
-- 而本表全部的价值在于「当时看到的就是当时的」—— 一次 UPDATE 不会让任何查询报错，
-- 它只会让一段历史变成一段看起来仍然合理的假历史。
CREATE TRIGGER financial_reports_no_update BEFORE UPDATE ON financial_reports
BEGIN SELECT RAISE(ABORT, 'financial_reports is append-only: 重述必须作为新的 announced_at 插入一行，改写旧行就是伪造历史'); END;

CREATE TRIGGER financial_reports_no_delete BEFORE DELETE ON financial_reports
BEGIN SELECT RAISE(ABORT, 'financial_reports is append-only: 已公告的财务数据不可删除 —— 判据的依据会随它一起消失'); END;
