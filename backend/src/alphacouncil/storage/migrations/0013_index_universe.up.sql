-- 0013 · index_constituents + index_universe_sweeps：指数成分史（spec 052 · universe）
--
-- 为什么这两张表存在
--
-- 主人的原话是「做一个板块把沪深300 的所有股票信息导入到一个股票池里面」，
-- 第二轮收窄成「**只要是在沪深300 的榜单出现的**，把K线成交量，等等拉过来」。
-- ⭐ **「出现过的」这三个字把范围从 300 变成了并集**，而这一条决定了下面几乎所有设计：
-- 一只票 2019 年在指数里、2023 年被摘出去，**它仍然在池子里** ——
-- 因为读者 2019 年的决策还要能显示它的名字。
--
-- 1. ⚠️⭐ **这张表没有 effective_from / effective_to，而这是一个决定，不是一个省略**
--    我们观察得到的是一个**窗口**：first_observed_on（第一次在网格里看见它）到
--    last_observed_on（最后一次看见它）。⭐ **生效日落在这两个日期之间的某一天，
--    而我们不知道是哪一天。**
--
--    实测依据（2026-10-03，baostock 0.9.4）：
--    · ✅ 时点性成立 —— 探针 2025-06-13 vs 2025-06-16 换入换出 7 只，
--      2025-12-12 vs 2025-12-15 换 11 只，两次都精确对上中证指数《编制方案》6.1
--      「每年 6 月和 12 月的第二个星期五的下一交易日」。
--    · ⚠️ **但源给的 updateDate 不能当生效日**：探针 2025-06-16 -> 2025-06-16、
--      2025-12-15 -> 2025-12-15，**两次都精确等于那个生效日**，我当时判断「就是它」。
--      而第五个样本 2025-07-11 -> 2025-07-07 就推翻了 —— 那天是周一，不是任何调整日。
--      真正的形状是：**五个 updateDate 全是周一**，它是每周一批的入库戳；前两次
--      「吻合」只因为那两天的生效日本身落在周一。
--      ⇒ 所以 vendor_update_date 原样存、**不解释**（列注释里写了这句话）。
--
--    ⚠️ 写 effective_from = first_observed_on 会让读者以为「它是这天进的指数」。
--    **合成日期会丢信息**（0011 已经为此把 period_end 与 announced_at 拆成两列），
--    ⭐ **而推算日期会造信息 —— 后者更坏，因为它不可见。**
--
-- 2. ⚠️ **`first_observed_on` 进主键**，否则一只票 2019 进、2023 出、2025 又进
--    会在第二次进的时候撞主键，**而那是三个不同的区间**。
--    `fetched_at` 进主键的理由与 0011:112-120 完全相同：「再抓一次」是一次**新的观察**，
--    它该有自己的主键位置。⭐ 而这也让下面的索引末位 `fetched_at` 有了意义 ——
--    同一区间被两个源分别报过时，两条都在，「我们用哪一条」是消费方的事。
-- 3. ⚠️ **名字是时点事实，所以它在这张表里而不在 instruments.name。**
--    `repositories/instruments.py:7-12`：「**A row is never amended.**」
--    而一只票被判 ST 时 `code_name` 会变（闻泰科技 -> ST闻泰），摘帽又变回来。
--    ⭐ **把一个会变的事实放进一个不许变的列，它进去那天就开始撒谎。**
--    列名 `name_as_observed` 而不是 `name`，因为它只承诺**那次观察里**源报的名字。
--    ⚠️ 已知缺口：区间**中途**改名又改回，本表表达不了（spec 052 §十-3）。
-- 4. **append-only 触发器**与 0011:144-154 同理由：一次 UPDATE 就是一次静默的重写历史。
-- 5. ⚠️ **成份变动有三种节奏，不是一种**（中证指数《编制方案》）：
--    定期 = 每年 6 月和 12 月第二个星期五的下一交易日（§6.1）；
--    临时 = 退市/分立/破产/长期停牌，**任何时候**（§7.3~§7.6）；
--    风险警示剔除 = **每月**第二个星期五的下一交易日（§7.7）。
--    ⭐ 所以成员集合的边界不由日历决定，由事件决定，
--    而 `last_observed_on` 可能是月中某一天。
-- 6. ⚠️ **网格是周分辨率，而这是源的能力上限，不是我们的取舍。**
--    实测 2025-07-07（周一，非调整日）到 07-11 四个工作日的 updateDate 全是 07-07、
--    集合完全相同 ⇒ 答案是一个阶跃函数，台阶落在周一。
--    ⚠️ **周三的一次临时调整对任何调用者都不可见，直到下周一** ——
--    所以更细的网格救不了它，而按周探 1083 次与按天探 5000 次返回同一答案。
-- 7. **本表不是「当前 300 只」**，它是区间历史。而「当前」由第二张表定义（见下）。

CREATE TABLE index_constituents (
    index_code   TEXT NOT NULL,
    market       TEXT NOT NULL,
    code         TEXT NOT NULL,
    -- ⚠️ 「**在 last_observed_on 那次观察里**，源报的名字」—— 一个窄承诺。
    -- 区间中途的改名不在本表的能力内，而列名要让人不可能误读成「它一直叫这个」。
    name_as_observed TEXT NOT NULL,
    -- ⚠️⭐ 这两列是**观察窗口**，不是生效区间。见文件头第 1 条。
    first_observed_on TEXT NOT NULL,
    last_observed_on  TEXT NOT NULL,
    source     TEXT NOT NULL,
    -- ⚠️ 原样存、**不解释**。它是源的每周入库戳，不是生效日（文件头第 1 条）。
    -- 可空：某些源不提供它，而「没提供」不能写成某个日期。
    vendor_update_date TEXT,
    fetched_at TEXT NOT NULL,
    -- ⚠️ `first_observed_on` 进主键，理由见文件头第 2 条。
    -- ⚠️ **`fetched_at` 在末位**而不是像 0011 那样只作 tie-break ——
    -- 0011 的注释（:129-136）警告过「两个都留着时无法互相区分，删掉另一个会补上」。
    -- ⭐ 这里末位那一列**是**承重的：同一区间两次扫描，`fetched_at` 决定它们是
    -- 两条观察而不是一条被静默合并的观察。
    PRIMARY KEY (index_code, market, code, first_observed_on, source, fetched_at),
    -- ⚠️ **指数代码是白名单，而白名单比 `data-sources.md:120` 那六个短。**
    -- 那一行列了 {"000300","000905","000016","000688","000852","000010"} 且全仓零引用，
    -- ⭐ 而已装的 baostock 只服务其中三个（`query_hs300_stocks` / `query_zz500_stocks` /
    -- `query_sz50_stocks`，`sectorinfo.py:97/227/162`）。⇒ 000688 / 000852 / 000010
    -- **没有源**，而不是「源还没接」。⚠️ 写进 CHECK 而不是留给调用方，是因为
    -- 「这个指数我们没有」必须是**不可表达**的，而不是一条运行时错误。
    CONSTRAINT index_constituents_index_check
        CHECK (index_code IN ('000300', '000905', '000016')),
    -- ⚠️ 与 `financial_reports_symbol_check` 同一份枚举。红线 15：000001 在沪市是
    -- 上证指数、在深市是平安银行，**代码→市场是一对多**。而沪深300 里没有北交所成分
    -- ——⭐ **那是关于世界的事实，不是「没有源声明」**，所以枚举仍然三个值。
    CONSTRAINT index_constituents_symbol_check
        CHECK (market IN ('sh', 'sz', 'bj')),
    CONSTRAINT index_constituents_code_check
        CHECK (length(trim(code)) > 0),
    -- ⚠️ `name_as_observed` 不可空：一个没有名字的成员行在界面上无法与代码区分，
    -- 而**空字符串**比 NULL 更坏（它渲染成「有名字，只是空的」）。
    CONSTRAINT index_constituents_name_check
        CHECK (length(trim(name_as_observed)) > 0),
    -- ⭐⭐ **两个条件，不是一个。** 理由与 `0011:59-74` 逐字相同：GLOB 只看**形状**
    -- 不看**日历**，而 `2026-13-45` 是十个字符里的九个数字加两个横线，它稳稳通过。
    -- 补的那半个是 `date(...) IS NOT NULL` —— SQLite 的 `date()` 对非法日期返 NULL。
    -- ⚠️ 而 **CHECK 对 NULL 判为通过**，所以必须显式断言「不是 NULL」；
    -- 少了 `IS NOT NULL`，`date(first_observed_on)` 是一条**永远为真**的约束。
    CONSTRAINT index_constituents_first_observed_on_check
        CHECK (first_observed_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
               AND date(first_observed_on) IS NOT NULL),
    CONSTRAINT index_constituents_last_observed_on_check
        CHECK (last_observed_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
               AND date(last_observed_on) IS NOT NULL),
    -- ⚠️ 「最后看见它的那天」在「第一次看见它的那天」**之前**不是一次观察，
    -- 而是一段我们自己都说不通的记录。
    CONSTRAINT index_constituents_window_check
        CHECK (last_observed_on >= first_observed_on),
    -- ⚠️ **可空，所以要 `IS NULL OR`。** 「源没提供 updateDate」不能写成某个日期，
    -- 而 `CHECK (vendor_update_date GLOB ...)` 遇 NULL 判为通过 —— **那正好是我们要的**
    -- 语义（可空），所以这里只需保证**非空时形状与日历都对**。
    -- ⭐ 这一条与上面两条的区别值得记下：那里必须显式 `IS NOT NULL`（否则约束永远为真），
    -- 这里必须**不要**显式（否则不可空）。
    CONSTRAINT index_constituents_vendor_update_date_check
        CHECK (vendor_update_date IS NULL
               OR (vendor_update_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                   AND date(vendor_update_date) IS NOT NULL)),
    -- ⭐ `fetched_at` 一句 `strftime` 同时管住形状与日历（`0011:95-99` 已论证）：
    -- `2026-02-30` 会被归一化成 `2026-03-02` 从而对不上。所以只需要它一个条件。
    CONSTRAINT index_constituents_fetched_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', fetched_at) = fetched_at),
    -- ⚠️⭐ 「我们观察到某天的成员资格」不可能发生在**抓到它之后**。
    -- 这一条与 `0011:100-106` 的 `fetched_after_announced_check` 是同一个道理：
    -- **在那一刻之前抓到它，意味着我们看到的是未来。**
    -- ⭐ 这里必须用 `date(fetched_at)` 而不是原字符串：抓取带时刻、观察日不带，
    -- 字符串比较会因为 `T` 把**同一天**判成「抓到得比观察晚」。
    CONSTRAINT index_constituents_observed_before_fetched_check
        CHECK (date(last_observed_on) <= date(fetched_at))
) STRICT;

-- ⭐ 「当前成分」的主查询：`WHERE index_code = ? AND last_observed_on = ?`
-- 驱动条件是 `index_code` 等值，而 `last_observed_on` 是第二列而不是末位 ——
-- 0011:124-127 已把这条理由写死（把排序键放第一位会让每只票的查询扫全表）。
--
-- ⭐ **单标的的历史不在这里查**：`(index_code, market, code, first_observed_on)`
-- 是主键前缀，已经有序，所以「这只票的每一段成员资格」走主键索引即可。
CREATE INDEX idx_index_constituents_grid
    ON index_constituents(index_code, last_observed_on);

-- 「曾经是成分、现在不是」—— 池子页面按入池时间倒序翻它。
-- ⭐ 这是本板块**唯一**的查询形状之一，而它必须**便宜**：
-- 一只票可能有过三段成员资格，而正确答案是把三段都列出来而不是取最新一段。
CREATE INDEX idx_index_constituents_code
    ON index_constituents(index_code, market, code, first_observed_on DESC);

-- ---------------------------------------------------------------------------------------
-- index_universe_sweeps：「这份数据有多新」也是一张表
-- ---------------------------------------------------------------------------------------
--
-- 11 · financial_reports 是本仓第一张**承认自己有多旧**的表（spec 043），
-- 而 `.ai/data-sources.md:137` 记着「僵尸报价」的成因是「不报错、不崩溃，只是安静地骗人」。
-- ⚠️ **一个不说自己多旧的成分表，是它的同族** —— 读者会以为那 300 只是今天的，
-- 而它可能是上周一的。所以「我们知道的最后一天」必须可查，而不是从代码里推。
--
-- 粒度：**一次扫描、一个网格点、一个源**。
--
-- ⭐⭐ **`members > 0` 是一条 CHECK，而这是本迁移最要紧的一行。**
-- 实测（2026-10-03）`query_hs300_stocks('2007-07-23')` 返回
-- **`error_code='0'`（成功）且零行** —— 四周后那个周一没有入库批次。
-- ⚠️ 若把零行读成「那天没有成分」，写进去的就是「沪深300 有 0 只成分股」：
-- 一个荒谬值，而**它不会让任何地方报错**。
-- ⇒ 所以「一次成功的观察不可能有零个成员」被写成**约束而不是约定** ——
-- 这个仓库里，让违规的形状**跑不出来**比记得别写它可靠（F-225）。
-- ⭐ 而沪深300 / 上证50 / 中证500 在任何时刻都有成员，所以这条 CHECK 是真的，
-- 而不是「为了挡住某个坏数据」编的。
CREATE TABLE index_universe_sweeps (
    index_code TEXT NOT NULL,
    -- ⭐ **一周一个，所以两次扫描之间没有第四种粒度。**
    -- 「当前成分」的定义就是 `last_observed_on = (SELECT max(grid_point) ...)`，
    -- 而任何这样的查询**必须同时把这个日期显示给读者**（文件头引的那条已知骗人方式）。
    grid_point TEXT NOT NULL,
    source   TEXT NOT NULL,
    -- ⚠️ 这次观察到的成员数。⭐ **必须为正** —— 见上面那段。
    members  INTEGER NOT NULL,
    -- ⚠️ 本次扫描**失败**的网格点数。⭐ 落库而不只是打日志：
    -- 一个不完整的扫描如果看起来完整，读者无法分辨（F-218 的形状，第五次）。
    failures INTEGER NOT NULL,
    -- ⭐ 带时刻：我们什么时候抓的。与 grid_point 分开，因为它回答两个不同的问题
    -- （「数据有多旧」与「我们多久没更新了」），而它们不相等。
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (index_code, grid_point, source),
    -- ⭐ 同一个白名单，理由见上面那条注释 —— **「我们没有这个指数的源」不可表达。**
    CONSTRAINT index_universe_sweeps_index_check
        CHECK (index_code IN ('000300', '000905', '000016')),
    CONSTRAINT index_universe_sweeps_grid_point_check
        CHECK (grid_point GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
               AND date(grid_point) IS NOT NULL),
    -- ⭐⭐⭐ **这一行是本迁移存在的理由。**
    -- 实测 `query_hs300_stocks('2007-07-23')` 返回 **`error_code='0'` 且零行**。
    -- ⚠️ 把零行当「那天没有成分」会写进一个荒谬值，而它不会让任何地方报错。
    -- ⇒ 「一次成功的观察不可能有零个成员」写成约束，于是那个形状**跑不出来**。
    -- ⚠️ 而这不是「为了挡一个坏数据」编的规则：沪深300 / 上证50 / 中证500 在任何
    -- 时刻都有成员，所以 `members > 0` 是真的。
    CONSTRAINT index_universe_sweeps_members_positive_check
        CHECK (members > 0),
    -- ⚠️ 失败数不为负。⭐ **「失败了一次也没有记下来」也要被挡** ——
    -- 否则 `failures = 0` 在两种含义（没失败 / 没记）之间不可分辨，
    -- 而后者正是 `F-218` 那个家族的形状。
    CONSTRAINT index_universe_sweeps_failures_check
        CHECK (failures >= 0),
    -- ⚠️ 「网格点在抓到它之后」不可能，与成分表那条同理由。
    -- ⭐ 而这里**不**加「网格点不能是未来」的约束：⚠️ 它看起来该加，
    -- 但我们**故意**允许网格点取最近一个周一 —— 周分辨率下「今天」的答案是
    -- 「本周一的那份」（§6），而把它夹到今天会让那份数据永远无法记录。
    -- ⭐ 真正的诚实做法是让 `grid_point` 自己说明它有多旧，而不是禁止它。
    CONSTRAINT index_universe_sweeps_grid_before_fetched_check
        CHECK (date(grid_point) <= date(fetched_at)),
    CONSTRAINT index_universe_sweeps_fetched_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', fetched_at) = fetched_at)
) STRICT;

-- 「这个指数我们知道的最后一天」——定义「当前成分」的那一个查询。
--
-- ⭐⚠️ **末位 `grid_point DESC` 是承重的，而 `source` 原本卡在中间，那是一个真实的缺陷。**
-- 第一版写成 `(index_code, source, grid_point DESC)`，理由是「一个扫描点由 (index_code,
-- grid_point, source) 标识，所以三者都在索引里」。⚠️ **而主查询不按 `source` 过滤**：
-- 它问「我们知道的最后一天是几号」，那是一个 `max(grid_point)` ⭐ **B-tree 的前缀在
-- `source` 处断掉，末位的 DESC 根本用不上。**
-- ⇒ **一个索引把三列都收进来，而查询只用前两列，第三列就成了装饰。**
--
-- ⭐ 而这与 `0011:129-136` 那条警告是同一族：**「取最新」的确定性可以来自索引也可以
-- 来自查询，两者都在时无法互相区分，删掉其中一个另一个会补上。**
-- ⇒ 所以这里只把**驱动条件**放前面（`index_code`），把**排序键**放末位，
-- 并且**不把 `source` 放在中间**：查询若要按源过滤，那是一次显式的多源比对，
-- 它该走 `idx_index_universe_sweeps_latest` 之外的路，或者干脆全表扫 ——
-- ⭐ **而不是让一个索引假装自己三列都能用。**
CREATE INDEX idx_index_universe_sweeps_latest
    ON index_universe_sweeps(index_code, grid_point DESC);

-- ---------------------------------------------------------------------------------------
-- append-only：与 0011:144-154 同理由，不是「日志表要加触发器」是因为这样
-- ---------------------------------------------------------------------------------------
--
-- 一句写在文档里的要求拦不住一句 `UPDATE`。⭐ 更要紧的是：**一次 UPDATE 就是一次
-- 静默的重写历史** —— 本表全部的价值在「后来的人看到的是后来那份名单」，
-- 而一次 UPDATE 不会让任何查询报错，它只会把一段成员史改成一段看起来仍然合理的假史。
-- ⚠️ 而这个表的 UPDATE 诱惑比 financial_reports 更大：有人会想「上次扫错了，改一下」。
-- 那正是应该**再扫一次**的理由 —— 新的一次是**新的观察**，有自己的 fetched_at 主键位置。
CREATE TRIGGER index_constituents_no_update BEFORE UPDATE ON index_constituents
BEGIN SELECT RAISE(ABORT, 'index_constituents is append-only: 上次扫错了就再扫一次，扫出新的一行；改写旧行就是伪造成分史'); END;

CREATE TRIGGER index_constituents_no_delete BEFORE DELETE ON index_constituents
BEGIN SELECT RAISE(ABORT, 'index_constituents is append-only: 「曾经是成分」不可删除 ——— 读者过去决策里那些票的名字靠它'); END;

-- ⚠️ **这张表的 UPDATE 诱惑更大**：它的每一行是「我们什么时候知道的」，
-- 改它就是让一句「我们当时就知道」在事后变成一句「我们当时还不知道」。
CREATE TRIGGER index_universe_sweeps_no_update BEFORE UPDATE ON index_universe_sweeps
BEGIN SELECT RAISE(ABORT, 'index_universe_sweeps is append-only: 失败数只能在下一次扫描里更正，不能就地改'); END;

CREATE TRIGGER index_universe_sweeps_no_delete BEFORE DELETE ON index_universe_sweeps
BEGIN SELECT RAISE(ABORT, 'index_universe_sweeps is append-only: 「我们知道的最后一天」不可删除 — 删掉它，一份旧数据会看起来是新的'); END;
