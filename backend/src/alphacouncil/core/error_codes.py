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
    # Added 2026-09-26 with J1. The schema enforces that kill_criteria is a JSON
    # array; it cannot enforce that the array is non-empty, because an empty one
    # satisfies `json_valid(...) AND json_type(...) = 'array'`. So "no falsifiable
    # condition" is refused in the domain, and it needs its own code for the same
    # reason the counter-evidence does: "how often does a user record a decision
    # with nothing that could ever falsify it" has to stay answerable.
    DECISION_KILL_CRITERIA_REQUIRED = "DECISION_KILL_CRITERIA_REQUIRED"
    DECISION_TEXT_TOO_LONG = "DECISION_TEXT_TOO_LONG"


    # -- CARD_* : knowledge cards (K1) -------------------------------------
    CARD_CONTENT_REQUIRED = "CARD_CONTENT_REQUIRED"
    CARD_SOURCE_URL_REQUIRED = "CARD_SOURCE_URL_REQUIRED"
    CARD_SOURCE_TITLE_REQUIRED = "CARD_SOURCE_TITLE_REQUIRED"
    CARD_NOT_FOUND = "CARD_NOT_FOUND"
    CARD_ALREADY_VERIFIED = "CARD_ALREADY_VERIFIED"
    CARD_TEXT_TOO_LONG = "CARD_TEXT_TOO_LONG"
    CARD_PRIORITY_INVALID = "CARD_PRIORITY_INVALID"
    # Added 2026-09-27 with K2 (spec 013). Convergence is the lifecycle exit:
    # it only applies to an active card and demands a user-written reason. The
    # two failures stay separate codes — "how often do users try to retire an
    # already retired card" and "how often do they skip the reason" answer
    # different questions.
    CARD_NOT_ACTIVE = "CARD_NOT_ACTIVE"
    CARD_CONVERGE_REASON_REQUIRED = "CARD_CONVERGE_REASON_REQUIRED"

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
    CHECK_TOOL_ENCODING_UNGUARDED = "CHECK_TOOL_ENCODING_UNGUARDED"

    # -- CHECK_* : emitted by the check runner itself -----------------------
    # Not tied to any single rule, so they cannot be attributed to one row.
    CHECK_EXEMPTION_UNREASONED = "CHECK_EXEMPTION_UNREASONED"
    CHECK_RUNNER_ERROR = "CHECK_RUNNER_ERROR"
