-- 0001_initial · AlphaCouncil 初始 schema
--
-- 覆盖范围（S1 收口）：
--   instruments        标的表，主键 (market, code)
--   watchlist_events   D1 关注池（append-only 事件日志）
--   decisions          J1 决策登记（append-only，红线 4 的数据库表达）
--   audit_log          审计轨迹（append-only，宪法 6.3）
--
-- 三条设计约定，全库统一：
--
--   1. **时间戳一律是 `YYYY-MM-DDTHH:MM:SS.sssZ`（UTC，毫秒）**，由服务端生成。
--      校验写法 `strftime('%Y-%m-%dT%H:%M:%fZ', ts) = ts` —— 它做的是**往返相等**，
--      只接受规范形式：缺 Z、用空格分隔、秒以下位数不对、日期越界，全部拒绝。
--      比手写 GLOB 模式短，且不会因为数错字符而静默放过。
--   2. **空串不是"未知"，是错误** —— 未知一律 NULL（宪法 5.2 #13）。
--      所以每个可空文本列都带 `IS NULL OR length(trim(x)) > 0`。
--   3. **表都是 STRICT** —— 类型错误变成运行时错误，而不是被 SQLite 的
--      动态类型悄悄存下来（宪法 0.2：能移到编译期/运行时就必须移）。
--
-- 约束命名统一 `<table>_<aspect>_check`（宪法 5.4.2），条件必填用 `A OR B IS NOT NULL`
-- 写法而不是 `CASE WHEN`（避免方言差异）。外置清单见**上级目录**的 `storage/constraints.json`
-- （不是本目录 —— 这里只放 `.sql` 与 `manifest.json`）。

-- ===========================================================================
-- instruments · 标的
-- ===========================================================================

-- 主键是 (market, code) 而不是 code：`000001` 在沪市是上证指数、深市是平安银行，
-- 代码→市场是一对多（宪法 5.2 #15 / ADR-0017）。用 code 当主键会让两个不同的
-- 东西共用一行，而且**不会报错**，只会安静地给出另一个标的的数据。
CREATE TABLE instruments (
    market          TEXT NOT NULL,
    code            TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    name            TEXT,
    name_source     TEXT,
    name_fetched_at TEXT,
    created_at      TEXT NOT NULL,

    PRIMARY KEY (market, code),

    CONSTRAINT instruments_market_check
        CHECK (market IN ('sh', 'sz', 'bj')),
    -- 恰好 6 位数字。不用 trim 容忍空白：STRICT 表里空格是明确的错误输入。
    CONSTRAINT instruments_code_check
        CHECK (length(code) = 6 AND code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'),
    CONSTRAINT instruments_asset_type_check
        CHECK (asset_type IN ('stock', 'index', 'etf')),
    CONSTRAINT instruments_name_check
        CHECK (name IS NULL OR length(trim(name)) > 0),
    -- provenance rule：有名字就必须有来源与采集时刻，否则那个名字无法追溯
    CONSTRAINT instruments_name_provenance_check
        CHECK (name IS NULL OR (name_source IS NOT NULL AND name_fetched_at IS NOT NULL)),
    CONSTRAINT instruments_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at)
) STRICT;

-- ===========================================================================
-- watchlist_events · D1 关注池
-- ===========================================================================

-- 为什么是事件日志而不是 `watchlist(market, code, reason, removed_at)` 一行：
--
--   * 关注理由**是用户写下的文字**。红线 15 第 ④ 档明令 agent 永久不得"改关注池
--     理由"，但如果 reason 是一个可 UPDATE 的列，数据库拦不住任何改写。
--   * 产品亮点 ② 是"决策层的间隔重复"（"这句话你说过 3 次"）。要答出"你三个月前
--     写的关注理由和现在写的是不是同一个"，理由必须有历史 —— 覆盖式的列永远答不出。
--   * 这不是新机制，是把 ADR-0011（日志表只追加）与 ADR-0016（触发器强制）应用到
--     关注池。宪法 §2.2 的门槛问的是"既有机制能不能处理"，答案是能。
--
-- 于是"移出关注池"也是一条记录，当前成员由视图 `watchlist_current` 派生。
-- 派生在这里是安全的：行删不掉（触发器），所以派生值不会因为删除而悄悄变化。
CREATE TABLE watchlist_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at   TEXT NOT NULL,
    market        TEXT NOT NULL,
    code          TEXT NOT NULL,
    kind          TEXT NOT NULL,
    reason        TEXT,
    supersedes_id INTEGER,

    CONSTRAINT watchlist_events_kind_check
        CHECK (kind IN ('added', 'removed', 'reason_revised')),
    -- 条件必填：移出不需要理由，加入与改理由必须有
    CONSTRAINT watchlist_events_reason_required_check
        CHECK (kind = 'removed' OR reason IS NOT NULL),
    CONSTRAINT watchlist_events_reason_not_blank_check
        CHECK (reason IS NULL OR length(trim(reason)) > 0),
    CONSTRAINT watchlist_events_reason_length_check
        CHECK (reason IS NULL OR length(reason) <= 2000),
    -- 改理由必须指向被修订的那一条；其余 kind 不许带 supersedes_id
    CONSTRAINT watchlist_events_supersedes_check
        CHECK ((kind = 'reason_revised') = (supersedes_id IS NOT NULL)),
    CONSTRAINT watchlist_events_occurred_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', occurred_at) = occurred_at),

    FOREIGN KEY (market, code) REFERENCES instruments (market, code),
    FOREIGN KEY (supersedes_id) REFERENCES watchlist_events (id)
) STRICT;

-- 当前关注池。`kind = 'removed'` 的最新一条意味着已移出。
-- 用 `id` 排序而不是 `occurred_at`：id 是自增的写入顺序，同一毫秒也不会打平。
CREATE VIEW watchlist_current AS
SELECT
    events.market,
    events.code,
    events.reason,
    events.occurred_at,
    events.id AS last_event_id
FROM watchlist_events AS events
WHERE events.id = (
    SELECT latest.id
    FROM watchlist_events AS latest
    WHERE latest.market = events.market AND latest.code = events.code
    ORDER BY latest.id DESC
    LIMIT 1
)
AND events.kind != 'removed';

-- ===========================================================================
-- decisions · J1 决策登记
-- ===========================================================================

-- 主键 = 记录时刻的毫秒时间戳，服务端生成（ADR-0011 / 红线 4）。
-- 客户端不能传 id —— 否则用户可以把一条决策写成"三个月前"，
-- 而"在结果之前写下的文字"这个不可再生的证据就没了。
CREATE TABLE decisions (
    id               TEXT PRIMARY KEY,
    market           TEXT NOT NULL,
    code             TEXT NOT NULL,
    action           TEXT NOT NULL,
    rationale        TEXT NOT NULL,
    counter_evidence TEXT NOT NULL,
    kill_criteria    TEXT NOT NULL,
    thesis_id        TEXT,

    -- 主键即时间戳：格式本身由数据库校验
    CONSTRAINT decisions_id_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', id) = id),
    CONSTRAINT decisions_action_check
        CHECK (action IN ('buy', 'add', 'hold', 'trim', 'exit')),
    -- 红线 4 的数据库表达（宪法 5.4.3）：理由与反面证据双必填。
    -- 反面证据是**唯一能对抗确认偏差的字段** —— 它不能为空，也不能是空白。
    CONSTRAINT decisions_rationale_required_check
        CHECK (length(trim(rationale)) > 0),
    CONSTRAINT decisions_counter_evidence_required_check
        CHECK (length(trim(counter_evidence)) > 0),
    CONSTRAINT decisions_rationale_length_check
        CHECK (length(rationale) <= 2000),
    CONSTRAINT decisions_counter_evidence_length_check
        CHECK (length(counter_evidence) <= 2000),
    -- 失效条件必须是**结构化谓词数组**（ADR-0017 #5）。
    -- 自由文本只能作补充说明：判定走谓词，才有"数据驱动对质"。
    CONSTRAINT decisions_kill_criteria_json_check
        CHECK (json_valid(kill_criteria) AND json_type(kill_criteria) = 'array'),

    FOREIGN KEY (market, code) REFERENCES instruments (market, code)
) STRICT;

-- ===========================================================================
-- audit_log · 审计轨迹
-- ===========================================================================

-- 宪法 6.3：审计**记"做了什么"，不记"内容是什么"**。
-- `detail` 只放结构化摘要（如 `{"field": "reason"}`），不放用户写下的正文 ——
-- 长度上限 500 是这条规则的机械保证：塞不进一篇文章。
CREATE TABLE audit_log (
    id          TEXT PRIMARY KEY,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_kind TEXT,
    target_id   TEXT,
    detail      TEXT,

    CONSTRAINT audit_log_id_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', id) = id),
    CONSTRAINT audit_log_actor_check
        CHECK (actor IN ('user', 'agent', 'system')),
    CONSTRAINT audit_log_action_not_blank_check
        CHECK (length(trim(action)) > 0),
    CONSTRAINT audit_log_target_check
        CHECK ((target_kind IS NULL) = (target_id IS NULL)),
    CONSTRAINT audit_log_detail_length_check
        CHECK (detail IS NULL OR length(detail) <= 500)
) STRICT;

-- ===========================================================================
-- 索引
-- ===========================================================================

CREATE INDEX watchlist_events_symbol_idx ON watchlist_events (market, code, id);
CREATE INDEX decisions_symbol_idx ON decisions (market, code, id);
CREATE INDEX audit_log_target_idx ON audit_log (target_kind, target_id, id);

-- ===========================================================================
-- append-only 触发器（宪法 5.4.1 / ADR-0016）
-- ===========================================================================

-- 这四对触发器是红线 4 从「文档」搬到「数据库」（宪法第零条 0.2 的第 ④ 层）：
-- 违反时是数据库报错，不是代码评审时的提醒。
-- 静态侧由 S-04 拦「迁移里漏写触发器」，运行时侧由 .ai/checks/data/ 的 D-21 拦
-- 「触发器被绕过」—— 两层都不依赖人记得。

CREATE TRIGGER watchlist_events_no_update BEFORE UPDATE ON watchlist_events
BEGIN SELECT RAISE(ABORT, 'watchlist_events is append-only: 改变想法请追加新记录'); END;

CREATE TRIGGER watchlist_events_no_delete BEFORE DELETE ON watchlist_events
BEGIN SELECT RAISE(ABORT, 'watchlist_events is append-only: 记录不可删除'); END;

CREATE TRIGGER decisions_no_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions is append-only: 改变想法请追加新记录'); END;

CREATE TRIGGER decisions_no_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions is append-only: 记录不可删除'); END;

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only: 审计轨迹不可修改'); END;

CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only: 审计轨迹不可删除'); END;
