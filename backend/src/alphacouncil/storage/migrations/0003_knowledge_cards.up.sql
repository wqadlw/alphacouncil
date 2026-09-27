-- 0003 · knowledge_cards：知识卡片与关联标的（spec 012 · K1）
--
-- 为什么这张表存在：
-- 知识卡片是 AlphaCouncil 知识层的最小原子单元（K1）。
-- 它不是通用笔记，而是一条附带来源追溯的一句话判断（provenance rule）。
--
-- 核心设计：
-- 1. 强制来源追溯（宪法 5.2 / 红线 4）：
--    source_url 与 captured_at 严格必填，且必须是合规 URL 协议与标准 UTC 毫秒时间戳。
-- 2. 三种录入通道（红线 15 / ADR-0022）：
--    origin 为 user_written / extracted / ai_generated。ai_generated 必须留存来源，
--    后续由用户核对升级。
-- 3. 三分类（ADR-0021）：
--    supporting / challenging / neutral。
-- 4. 优先级与收敛状态：
--    priority 为 1..5，status 为 active / converged。
-- 5. 标的多对多关联：
--    card_symbols 维护卡片与标的 (market, code) 的关联，受外键约束。

CREATE TABLE cards (
    id           TEXT    NOT NULL PRIMARY KEY,
    content      TEXT    NOT NULL,
    claim_type   TEXT    NOT NULL,
    source_url   TEXT    NOT NULL,
    source_title TEXT    NOT NULL,
    captured_at  TEXT    NOT NULL,
    as_of        TEXT,
    origin       TEXT    NOT NULL,
    priority     INTEGER NOT NULL,
    status       TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    CONSTRAINT cards_id_check
        CHECK (GLOB('card_[0-9]*', id)),
    CONSTRAINT cards_content_required_check
        CHECK (length(trim(content)) > 0),
    CONSTRAINT cards_content_length_check
        CHECK (length(content) <= 1000),
    CONSTRAINT cards_claim_type_check
        CHECK (claim_type IN ('supporting', 'challenging', 'neutral')),
    CONSTRAINT cards_source_url_required_check
        CHECK (length(trim(source_url)) > 0),
    CONSTRAINT cards_source_url_format_check
        CHECK (source_url GLOB 'http://*' OR source_url GLOB 'https://*'),
    CONSTRAINT cards_source_title_required_check
        CHECK (length(trim(source_title)) > 0),
    CONSTRAINT cards_source_title_length_check
        CHECK (length(source_title) <= 255),
    CONSTRAINT cards_captured_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', captured_at) = captured_at),
    CONSTRAINT cards_as_of_check
        CHECK (as_of IS NULL OR strftime('%Y-%m-%d', as_of) = as_of),
    CONSTRAINT cards_origin_check
        CHECK (origin IN ('user_written', 'extracted', 'ai_generated')),
    CONSTRAINT cards_priority_check
        CHECK (priority IN (1, 2, 3, 4, 5)),
    CONSTRAINT cards_status_check
        CHECK (status IN ('active', 'converged')),
    CONSTRAINT cards_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at)
) STRICT;

CREATE TABLE card_symbols (
    card_id    TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    market     TEXT NOT NULL,
    code       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (card_id, market, code),
    FOREIGN KEY (market, code) REFERENCES instruments(market, code) ON DELETE RESTRICT,
    CONSTRAINT card_symbols_market_check
        CHECK (market IN ('sh', 'sz', 'bj')),
    CONSTRAINT card_symbols_code_check
        CHECK (GLOB('[0-9][0-9][0-9][0-9][0-9][0-9]', code)),
    CONSTRAINT card_symbols_created_at_check
        CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at)
) STRICT;

CREATE INDEX idx_card_symbols_instrument ON card_symbols(market, code);
CREATE INDEX idx_cards_status ON cards(status);
CREATE INDEX idx_cards_origin ON cards(origin);
