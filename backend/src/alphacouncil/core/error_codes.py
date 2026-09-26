"""The managed error-code namespace — the single source of truth.

`.ai/error-codes.md` is the human-readable view; this module is what the code
imports. `S-05` checks the two against each other, so a code cannot exist in one
place and be missing from the other.

**Why an enum rather than strings:** the rule "unregistered codes must not
appear in code" used to live in a document (layer ① — a sentence, enforced by
nobody). Here it becomes a *type* (layer ③): a typo or an invented code fails to
import, rather than reaching a user as an unexplained string. See constitution
§0.2 — *if a rule can be moved from ① to ③, it must be*.

**Publishing rule:** once a code has shipped, it is never renamed. Changing the
meaning means adding a new code and marking the old one deprecated.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Every code the product may emit."""

    # -- DATA_SOURCE_* : external sources ----------------------------------
    DATA_SOURCE_RATE_LIMITED = "DATA_SOURCE_RATE_LIMITED"
    DATA_SOURCE_IP_BLOCKED = "DATA_SOURCE_IP_BLOCKED"
    DATA_SOURCE_FORBIDDEN = "DATA_SOURCE_FORBIDDEN"
    DATA_SOURCE_CIRCUIT_OPEN = "DATA_SOURCE_CIRCUIT_OPEN"
    DATA_SOURCE_UNAVAILABLE = "DATA_SOURCE_UNAVAILABLE"
    DATA_SOURCE_UNREACHABLE = "DATA_SOURCE_UNREACHABLE"
    DATA_SOURCE_NOT_SUPPORTED = "DATA_SOURCE_NOT_SUPPORTED"
    DATA_SOURCE_TICKER_AMBIGUOUS = "DATA_SOURCE_TICKER_AMBIGUOUS"
    DATA_SOURCE_TICKER_INVALID = "DATA_SOURCE_TICKER_INVALID"

    # -- DATA_* : the four data states (constitution 4.6) ------------------
    DATA_NO_DATA = "DATA_NO_DATA"
    DATA_FETCH_ERROR = "DATA_FETCH_ERROR"
    DATA_UNVERIFIABLE = "DATA_UNVERIFIABLE"

    # -- CONTRACT_* : unit and period discipline (constitution 4.2) --------
    CONTRACT_ADJUST_MISMATCH = "CONTRACT_ADJUST_MISMATCH"
    CONTRACT_UNIT_AMBIGUOUS = "CONTRACT_UNIT_AMBIGUOUS"
    CONTRACT_CURRENCY_MISSING = "CONTRACT_CURRENCY_MISSING"
    CONTRACT_PERIOD_MISSING = "CONTRACT_PERIOD_MISSING"

    # -- DECISION_* : the decision journal ---------------------------------
    DECISION_RATIONALE_REQUIRED = "DECISION_RATIONALE_REQUIRED"
    DECISION_COUNTER_EVIDENCE_REQUIRED = "DECISION_COUNTER_EVIDENCE_REQUIRED"
    DECISION_APPEND_ONLY = "DECISION_APPEND_ONLY"
    DECISION_CLIENT_SUPPLIED_ID = "DECISION_CLIENT_SUPPLIED_ID"

    # -- WATCHLIST_* : the instrument pool (D1) ----------------------------
    # A separate namespace from DECISION_* because the two rules look alike and
    # are not: one guards a trade, the other guards the reason for watching an
    # instrument before any trade exists. Merging them would make "how often do
    # users leave the reason blank" unanswerable.
    WATCHLIST_REASON_REQUIRED = "WATCHLIST_REASON_REQUIRED"
    WATCHLIST_REASON_TOO_LONG = "WATCHLIST_REASON_TOO_LONG"
    WATCHLIST_NOT_FOLLOWED = "WATCHLIST_NOT_FOLLOWED"
    WATCHLIST_ALREADY_REMOVED = "WATCHLIST_ALREADY_REMOVED"

    # -- INSTRUMENT_* : the instrument itself, not the user's relation to it --
    INSTRUMENT_ASSET_TYPE_CONFLICT = "INSTRUMENT_ASSET_TYPE_CONFLICT"

    # -- AGENT_* : agent permission boundary (ADR-0010) --------------------
    AGENT_TOOL_NOT_FOUND = "AGENT_TOOL_NOT_FOUND"
    AGENT_DRAFT_NOT_COMMITTED = "AGENT_DRAFT_NOT_COMMITTED"
    AGENT_WRITE_DENIED = "AGENT_WRITE_DENIED"

    # -- MIGRATION_* / STORAGE_* ------------------------------------------
    MIGRATION_SNAPSHOT_FAILED = "MIGRATION_SNAPSHOT_FAILED"
    MIGRATION_FAILED = "MIGRATION_FAILED"
    STORAGE_DB_NEWER_THAN_APP = "STORAGE_DB_NEWER_THAN_APP"
    STORAGE_DB_NO_UPGRADE_PATH = "STORAGE_DB_NO_UPGRADE_PATH"

    # -- CHECK_* : emitted by the static/data check subsystem --------------
    # One per static rule, so a finding can be referenced by a stable id.
    # The first twelve mirror `.ai/checks/static/README.md` §3 one for one;
    # `S-12` fails the build if the two lists ever disagree.
    CHECK_RAW_HTTP = "CHECK_RAW_HTTP"
    CHECK_BOOLEAN_STATE = "CHECK_BOOLEAN_STATE"
    CHECK_PREDICTION_FIELD = "CHECK_PREDICTION_FIELD"
    CHECK_MISSING_TRIGGER = "CHECK_MISSING_TRIGGER"
    CHECK_UNREGISTERED_CODE = "CHECK_UNREGISTERED_CODE"
    CHECK_CLIENT_SUPPLIED_ID = "CHECK_CLIENT_SUPPLIED_ID"
    CHECK_RETURN_RATE_LEAK = "CHECK_RETURN_RATE_LEAK"
    CHECK_IMMATURE_OUTCOME = "CHECK_IMMATURE_OUTCOME"
    CHECK_TIME_COST_MISSING = "CHECK_TIME_COST_MISSING"
    CHECK_PRINT_STATEMENT = "CHECK_PRINT_STATEMENT"
    CHECK_BARE_EXCEPT = "CHECK_BARE_EXCEPT"
    CHECK_DOC_DRIFT = "CHECK_DOC_DRIFT"

    # -- CHECK_* : emitted by the check runner itself -----------------------
    # Not tied to any single rule, so they cannot be attributed to one row.
    CHECK_EXEMPTION_UNREASONED = "CHECK_EXEMPTION_UNREASONED"
    CHECK_RUNNER_ERROR = "CHECK_RUNNER_ERROR"
