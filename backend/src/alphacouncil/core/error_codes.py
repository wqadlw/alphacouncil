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
    # Added 2026-09-28 (spec 021) for the retrospective page. The only
    # DECISION_* code that is not about the input — hence 404 rather than the
    # 400 the rest of this namespace gets.
    DECISION_NOT_FOUND = "DECISION_NOT_FOUND"


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

    # Added 2026-09-28 with K3 (spec 018). Review scheduling. Three codes because
    # three different questions are being asked: does this card exist on the queue
    # (NOT_SCHEDULED), is enrolling it twice a mistake worth refusing (ALREADY),
    # and is the timestamp UTC (NOT_UTC). The last one exists because `fsrs`
    # rejects a naive datetime with a library error; ours names the field instead.
    CARD_NOT_SCHEDULED = "CARD_NOT_SCHEDULED"
    CARD_ALREADY_SCHEDULED = "CARD_ALREADY_SCHEDULED"
    CARD_TIMESTAMP_NOT_UTC = "CARD_TIMESTAMP_NOT_UTC"

    # -- NOTE_* : knowledge notes (spec 026) --------------------------------
    # A separate namespace from CARD_* on purpose, and the separation is the
    # whole point of the feature.
    #
    # The two look alike — both are knowledge, both carry the reader's words —
    # and they are guarded by **opposite** rules. A card is a claim you are
    # willing to sign, so it must carry a source (`CARD_SOURCE_URL_REQUIRED`).
    # A note is a note: 「流动性收紧时周期股先跌」 has no source, and forcing one
    # would push the reader to attach a link they have not read. Merging the
    # namespaces would make "how often do users attach a citation they did not
    # read" unanswerable, which is the one number that would show the provenance
    # rule decaying.
    #
    # ⭐ `NOTE_TEXT_TOO_LONG` is deliberately much larger than
    # `CARD_TEXT_TOO_LONG` (1000 chars). A card is "超过 3 行不算卡片，算文章";  # noqa: RUF003
    # an article is exactly what a note is allowed to be. 200k is a size guard
    # against a pasted file, not a style rule.
    #
    # The `noqa` sits on the quoted line and is deliberately **not** a per-file
    # exemption: this is a verbatim sentence from the card specification, and
    # `RUF003` cannot tell a quotation from ordinary prose. Suppressing one line
    # leaves the rule active for the rest of the file, where a lookalike
    # character in a comment is still worth knowing about.
    NOTE_TITLE_REQUIRED = "NOTE_TITLE_REQUIRED"
    NOTE_TITLE_TOO_LONG = "NOTE_TITLE_TOO_LONG"
    NOTE_BODY_BLANK = "NOTE_BODY_BLANK"
    NOTE_TEXT_TOO_LONG = "NOTE_TEXT_TOO_LONG"
    NOTE_NOT_FOUND = "NOTE_NOT_FOUND"
    NOTE_TAG_INVALID = "NOTE_TAG_INVALID"
    NOTE_LINK_SELF = "NOTE_LINK_SELF"
    NOTE_LINK_TARGET_UNKNOWN = "NOTE_LINK_TARGET_UNKNOWN"

    # -- NOTE_* scheduling (spec 028) --------------------------------------
    # Separate from the card codes (CARD_NOT_SCHEDULED / CARD_ALREADY_SCHEDULED)
    # for the same reason the whole note namespace is separate: a note review is
    # a **re-read and re-affirm** (「我的思想变了」), while a card review is a
    # check against a source. Merging them would make "how often does a user
    # still hold a view they wrote down" unanswerable — and that is the number
    # the whole 「经验无法从历史中学习」 thesis rests on.
    NOTE_NOT_SCHEDULED = "NOTE_NOT_SCHEDULED"
    NOTE_ALREADY_SCHEDULED = "NOTE_ALREADY_SCHEDULED"

    # -- LESSON_* : J5, spec 030 -------------------------------
    # ⭐ A lesson is not a card and not a note, so it gets its own prefix rather
    # than borrowing CARD_* or NOTE_*. The codes that would have been tempting to
    # reuse are the ones that mattered: a lesson with no content is not
    # NOTE_BODY_BLANK, because the two rules were written for two different
    # questions, and a reader who saw the wrong code would be told the note rules
    # apply to a thing that has never been a note.
    #
    # Corner brackets rather than fullwidth parentheses here, unlike the rest of
    # this project: RUF003 applies to comments too, and this sentence is mine —
    # not a quotation of a rule, so the per-file exemption in pyproject.toml does
    # not reach it and should not be stretched to.
    LESSON_CONTENT_BLANK = "LESSON_CONTENT_BLANK"
    LESSON_TEXT_TOO_LONG = "LESSON_TEXT_TOO_LONG"
    LESSON_NOT_FOUND = "LESSON_NOT_FOUND"
    LESSON_REVIEW_MISSING = "LESSON_REVIEW_MISSING"
    LESSON_ALREADY_PROMOTED = "LESSON_ALREADY_PROMOTED"
    LESSON_PROMOTION_SOURCE_REQUIRED = "LESSON_PROMOTION_SOURCE_REQUIRED"
    LESSON_NOT_SCHEDULED = "LESSON_NOT_SCHEDULED"
    LESSON_TIMESTAMP_NOT_UTC = "LESSON_TIMESTAMP_NOT_UTC"

    # -- REVIEW_* : decision reviews and the four quadrants (J3) ------------
    # Added 2026-09-28 (spec 020). REVIEW_NOT_DUE is the one that matters most:
    # it is the hard gate from `项目总纲` P0-3 — an outcome may not be scored
    # before the review is due, because scoring early is hindsight. The schema
    # enforces it too; this code is what the failure looks like when it arrives
    # through our own door rather than as a raw IntegrityError.
    REVIEW_SCORE_INVALID = "REVIEW_SCORE_INVALID"
    REVIEW_NOT_DUE = "REVIEW_NOT_DUE"
    REVIEW_NOTE_BLANK = "REVIEW_NOTE_BLANK"
    REVIEW_STATE_MISSING = "REVIEW_STATE_MISSING"

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
    # S-14 (spec 032). Two codes, not one: 「未跟踪」 and 「被忽略」 are different
    # defects with different fixes, and merging them into one code would make the
    # fix string lie about which one it is. The ignored case is the one that matters
    # more \u2014 `git status` does not show ignored files.
    CHECK_UNTRACKED_SOURCE = "CHECK_UNTRACKED_SOURCE"
    CHECK_IGNORED_SOURCE = "CHECK_IGNORED_SOURCE"
    # S-15. Two codes, and the split is the whole rule: 「the bytes are not UTF-8」
    # and 「the bytes are UTF-8 and one of the characters in them is U+FFFD」 are
    # different defects with different repairs. Merging them would also merge them
    # with the framework's own `errors="replace"`, which manufactures U+FFFD from
    # undecodable bytes and would make the two indistinguishable in a report.
    CHECK_SOURCE_NOT_UTF8 = "CHECK_SOURCE_NOT_UTF8"
    CHECK_MOJIBAKE_REPLACEMENT_CHAR = "CHECK_MOJIBAKE_REPLACEMENT_CHAR"

    # -- CHECK_* : emitted by the check runner itself -----------------------
    # Not tied to any single rule, so they cannot be attributed to one row.
    CHECK_EXEMPTION_UNREASONED = "CHECK_EXEMPTION_UNREASONED"
    # S-16 (spec 049). A descriptive code: it is not a product error but a disagreement
    # between the enums the backend publishes and the unions the frontend wrote. Its
    # consumer is the check runner, never a request path -- which is why it sits in the
    # CHECK_* block above rather than among the codes `api/errors.py` maps to HTTP.
    CHECK_ENUM_DRIFT = "CHECK_ENUM_DRIFT"
    # S-17 (spec 050). A descriptive code like CHECK_ENUM_DRIFT: the disagreement is
    # between the frontend's call sites and the routes the app serves, and its consumer
    # is the check runner, never a request path.
    CHECK_ROUTE_DRIFT = "CHECK_ROUTE_DRIFT"
    # S-18 (spec 053). Same shape of consumer as the two above: the disagreement is
    # between what FastAPI publishes and what `api.ts` declares, and nobody but the
    # check runner ever reads it. ⭐ Worth its own code rather than a reuse of
    # CHECK_ENUM_DRIFT ⭐ because the two rules have **opposite** fix directions:
    # ⭐ S-16's usual answer is "change the client", ⭐ and S-18's is often
    # "this schema has no client consumer, say so in a waiver".
    CHECK_RESPONSE_DRIFT = "CHECK_RESPONSE_DRIFT"
    CHECK_RUNNER_ERROR = "CHECK_RUNNER_ERROR"
