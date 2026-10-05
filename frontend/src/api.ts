/**
 * The API client. Deliberately thin — it does not re-validate anything the
 * server already enforces.
 *
 * The one thing it *does* care about is the error envelope. The backend answers
 * a domain failure with `{severity, code, message, target, fix}`, and `message`
 * is written for the user ("a watchlist reason cannot be blank — it is the
 * sentence the user is held to when the position goes wrong"). Re-wording it in
 * the client would throw away the only sentence written by whoever understood
 * the rule.
 */

export interface WatchlistEntry {
  market: string
  code: string
  asset_type: string
  name: string | null
  reason: string | null
  since: string
  last_event_id: number
}

export interface RecordedEvent {
  event_id: number
  occurred_at: string
  kind: 'added' | 'removed' | 'reason_revised'
  market: string
  code: string
  reason: string | null
  supersedes_id: number | null
}

export interface ApiFailure {
  severity?: string
  code: string
  message: string
  target?: string | null
  fix?: string | null
}

/**
 * One line of the watchlist log, as the instrument endpoint reports it.
 *
 * Not the same shape as `RecordedEvent`: that one is the receipt for a write and
 * carries the instrument inline, because the caller has just named it. Here the
 * instrument is already known — it is the page you are on — so repeating it on
 * every row would be noise. The two are kept apart rather than merged into one
 * loose type so a field added to either cannot silently satisfy the other.
 */
export interface WatchlistEvent {
  event_id: number
  occurred_at: string
  kind: 'added' | 'removed' | 'reason_revised'
  reason: string | null
  supersedes_id: number | null
}

export type FollowStatus = 'followed' | 'removed' | 'never'

export interface FollowState {
  status: FollowStatus
  reason: string | null
  since: string | null
  last_event_id: number | null
  event_count: number
}

export interface InstrumentDetail {
  market: string
  code: string
  display: string
  asset_type: string
  name: string | null
  follow: FollowState
  history: WatchlistEvent[]
  /**
   * Every decision recorded about this instrument, oldest first.
   *
   * Untruncated, and in write order — the same reason the watchlist log is.
   * "What have I believed about this company, and in what order did I change my
   * mind" only reads as an answer if nothing is missing from it.
   */
  decisions: Decision[]
  /**
   * Every knowledge card tied to this instrument, newest first (K1).
   *
   * Unlike the decisions and the log, this is a filtered view: the card store
   * is the knowledge layer, and an instrument page shows only the cards that
   * concern it. "What have I claimed about this company, and where did I say
   * it came from" reads newest-first, because an older card is not yet
   * superseded — it still exists, it just answers an older question.
   */
  cards: Card[]
}

/** How a card entered the record. Mirrors `CardOrigin` in `domain/card.py`. */
export type CardOrigin = 'ai_generated' | 'extracted' | 'user_written'

/** Lifecycle state. Mirrors `CardStatus` in `domain/card.py` (K2). */
export type CardStatus = 'active' | 'converged'

/** A lifecycle event kind, mirrored from `CardEventType` (K2). */
export type CardEventType = 'verified' | 'converged'

/** Whether the claim is for, against, or neither. Mirrors `ClaimType`. */
export type ClaimType = 'supporting' | 'challenging' | 'neutral'

/**
 * One recorded claim with its provenance.
 *
 * `id` is the write moment — server-generated, and the request schema refuses
 * any body that names it (S-06). `captured_at` is the moment the source was
 * seen, `created_at` the moment the row landed; they differ when a card is
 * recorded later than the material it quotes. `as_of` is the point-in-time
 * cutoff of the claim's figures, not a deadline and not a due date.
 */
export interface Card {
  id: string
  content: string
  claim_type: ClaimType
  source_url: string
  source_title: string
  captured_at: string
  as_of: string | null
  origin: CardOrigin
  priority: number
  status: CardStatus
  created_at: string
  symbols: CardSymbol[]
  events: CardEvent[]
}

/** One append-only lifecycle event for a card (K2). */
export interface CardEvent {
  id: string
  event_type: CardEventType
  reason: string | null
  created_at: string
}

/** One instrument a card is attached to, in the conventional form. */
export interface CardSymbol {
  market: string
  code: string
  display: string
}

export interface CardInput {
  content: string
  claim_type: ClaimType
  source_url: string
  source_title: string
  as_of?: string | null
  origin?: CardOrigin
  priority?: number
  symbols: string[]
}

/** What was decided. Mirrors the `decisions_action_check` constraint. */
export type DecisionAction = 'buy' | 'add' | 'hold' | 'trim' | 'exit'

/** Mirrors `ComparisonOperator` in `domain/decision.py`. Symbols, not words. */
export type ComparisonOperator = '<' | '<=' | '>' | '>=' | '==' | '!='

/**
 * One falsifiable condition — a predicate, never a sentence.
 *
 * ADR-0017 #5: "营收同比转负就重评" as prose cannot be evaluated, so nothing
 * can watch it and it can never come and find you. Structured, it can be
 * evaluated the moment the figure lands, which is what makes product highlight
 * ③ (data-driven confrontation) possible at all.
 */
export interface KillCriterion {
  metric: string
  operator: ComparisonOperator
  threshold: number
  /** Point-in-time cutoff (YYYY-MM-DD), not a deadline. */
  as_of: string
}

export interface Decision {
  /** The moment it was written, UTC with milliseconds. Server-generated. */
  id: string
  market: string
  code: string
  display: string
  action: DecisionAction
  rationale: string
  counter_evidence: string
  kill_criteria: KillCriterion[]
  thesis_id: string | null
}

export interface DecisionInput {
  ticker: string
  market?: string
  action: DecisionAction
  rationale: string
  counter_evidence: string
  kill_criteria: KillCriterion[]
  thesis_id?: string | null
  /**
   * When the user wants to come back and review this decision. Omitted means
   * "not yet", which is a real answer — the system will not invent an interval,
   * because "review after 90 days" is a suggestion with no stated criterion.
   * What it buys: a commitment made *before* the outcome exists (red line 4).
   */
  review_due_at?: string | null
}

/** The four states a fetch can be in (constitution 4.6). Never collapsed. */
export type DataStatus = 'ok' | 'no_data' | 'error' | 'unavailable'

export interface Quote {
  /**
   * ⚠️ Declared and never read.
   *
   * ⭐ Every current caller already knows which instrument it asked for — the
   * watchlist row, the pool row ⭐ — so nothing on a page needs this. ⭐ It is
   * declared anyway because 「no caller needs it」 and 「the server does not send
   * it」 are different facts, ⭐ and this interface is the only place that claim
   * can be written down. `S-18` (spec 053) exists because that claim had been
   * made the other way round silently, ⭐ on a type where it mattered.
   */
  symbol: { market: string; code: string }
  price: number
  prev_close: number
  /** A decimal fraction: -0.0114 is -1.14%. Computed server-side. */
  change_pct: number
  open: number
  high: number
  low: number
  volume: number
  amount: number
  quoted_at: string
  source: string
  fetched_at: string
}

export interface QuoteResult {
  status: DataStatus
  value: Quote | null
  reason: string | null
  detail: string | null
  error_code: string | null
  source: string | null
  fetched_at: string | null
  /** True when every live source failed and this is the last known good value. */
  stale: boolean
}

// ---------------------------------------------------------------------------
// K3 · the review queue
// ---------------------------------------------------------------------------

/**
 * Where a claim sits in the schedule.
 *
 * `deferred` is ours, not fsrs's: "not right now" is a queue state, not a
 * memory state, and postponing does **not** damage the card (SuperMemo S-05:
 * "暂不处理是特性不是拖延").
 */
export type ScheduleState = 'learning' | 'review' | 'relearning' | 'deferred'

/** Four grades, because fsrs v6 has four — not the five the literature still quotes. */
export type ReviewRating = 'again' | 'hard' | 'good' | 'easy'

export type ReviewOutcome = 'reviewed' | 'deferred'

/**
 * A card's scheduling state.
 *
 * ⚠️ **The absence of fields is the point.** No `retrievability`, no
 * `stability`, no `due_in_days`, no `mastery` — each is a number *about the
 * user*, and red line 9 forbids showing a 成绩. A field that does not exist
 * cannot be rendered by accident, which is why the backend refuses to send one
 * (`tests/unit/test_reviews_api.py::TestTheResponseCarriesNoScore`).
 */
export interface Schedule {
  card_id: string
  state: ScheduleState
  due_at: string
}

/** What one interaction did. A fact, not a verdict — see `ReviewReceipt`. */
export interface ReviewReceipt {
  card_id: string
  outcome: ReviewOutcome
  next_due_at: string
  state: ScheduleState
}

/**
 * One row of `card_reviews` — an interaction, never edited.
 *
 * ⭐ **Field-for-field identical to `NoteReview` (`notes.ts:257`) except for `card_id`.**
 * Both server models were written to the same shape and `scheduling.ReviewRow` /
 * `note_recall.ReviewRow` are the same dataclass — ⭐ so a reader who has seen a note's
 * history reads a card's without a translation table. `S-18` (`no_response_drift`) is
 * what holds the two sides together: it caught this type being absent the moment the
 * endpoint landed, which is why it exists.
 *
 * ⚠️ **`outcome` has two values here and three for a note.** A note is editable, so a
 * rewrite restarts its schedule and is recorded as `reset` (spec 028); ⭐ a card is
 * immutable, so migration 0005 constrains `outcome IN ('reviewed','deferred')` and there
 * is no third state to name. ⭐ **The narrower union is the structural fact, not an
 * omission** — and it is why the card history has no row equivalent to 「这条被我改过，排程从头开始」.
 *
 * ⚠️ **`duration_ms` is here and is not rendered.** Red line 11 rejects *showing*
 * 「你复习了 3 秒」 — an invitation to optimise one's own recall instead of reading
 * (`timelineAdapters.tsx` argues it at length for notes). It does not reject *storing*
 * it, and no client may submit one (`422`). Keeping the field means removing it later is
 * a decision rather than an accident.
 */
export interface CardReview {
  id: string
  card_id: string
  outcome: ReviewOutcome
  rating: ReviewRating | null
  reviewed_at: string
  duration_ms: number | null
  from_due_at: string
  to_due_at: string
  from_state: ScheduleState
  to_state: ScheduleState
}

/**
 * The whole history, oldest first.
 *
 * ⭐ **This is what answers 「我复习过好几次，为什么今天又来?」** for a card. The sentence is
 * `listNoteReviews`'s, copied deliberately rather than reworded: the question is the same
 * one, and it was spec 028's reason for making a note's rewrite a `reset` row.
 * ⭐ A card has no `reset`, so its history cannot answer a rewrite — but it can answer the
 * rest, which before spec 055 it could not answer at all.
 *
 * ⚠️ **Rejects rather than resolving empty for a missing card.** The server answers 404
 * (`CARD_NOT_FOUND`) on purpose, unlike the note route which returns `[]`
 * (`backend/tests/unit/test_reviews_api.py` holds both behaviours, so the divergence
 * cannot be tidied away silently).
 */
export function listCardReviews(cardId: string): Promise<CardReview[]> {
  return request<CardReview[]>(`/api/v1/cards/${cardId}/reviews`)
}

export function scheduleCard(cardId: string): Promise<Schedule> {
  return request<Schedule>(`/api/v1/cards/${cardId}/schedule`, { method: 'POST' })
}

/**
 * The queue at a stated instant.
 *
 * `asOf` is optional because the server can read the clock, but the tests always
 * pass it: a queue is a question about a moment, and a question you cannot
 * re-ask is a question you cannot check.
 */
export function getDueCards(asOf?: string, limit = 50): Promise<Schedule[]> {
  const params = new URLSearchParams()
  if (asOf) params.set('as_of', asOf)
  if (limit !== 50) params.set('limit', String(limit))
  const query = params.toString()
  return request<Schedule[]>(`/api/v1/review/due${query ? `?${query}` : ''}`)
}

/**
 * The body `POST /api/v1/review/{card_id}` accepts.
 *
 * ⭐ **This is the wire shape, and the union below is derived from it** ⭐ — not the other
 * way round. ⭐ Two declarations of one shape is what `spec 049` removed from this file, ⭐
 * and re-introducing it here would have been the tidiest-looking way to satisfy a gate.
 */
export interface CardReviewBody {
  outcome: ReviewOutcome
  rating?: ReviewRating | null
  days?: number | null
}

/**
 * ⭐ **The discrimination is kept** ⭐ — a recall carries a rating and a postponement
 * carries a day, ⭐ and an interface alone would let a page send `outcome: 'deferred'`
 * with a rating and find out from the server. ⭐ Derived rather than written out, ⭐ so
 * the field list exists exactly once.
 */
export type CardReviewInput =
  | (CardReviewBody & { outcome: 'reviewed'; rating: ReviewRating })
  | (CardReviewBody & { outcome: 'deferred' })

export function recordReview(
  cardId: string,
  body: CardReviewInput,
): Promise<ReviewReceipt> {
  return request<ReviewReceipt>(`/api/v1/review/${cardId}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * Decision reviews (J3) — the retrospective queue.
 *
 * **Named `decision-reviews`, not `reviews`.** `/api/v1/review` is the *card*
 * queue; one letter apart is not a distinction, and a client that mistypes it
 * would get a 200 full of the wrong shape.
 */
export type ProcessBand = 'good' | 'bad'

export type Quadrant = 'repeat' | 'acceptable' | 'dangerous' | 'fix' | 'unknown'

/**
 * A decision's review outcome — a **category**, never a number.
 *
 * There is no `figure` here and that is the point (red line 10): a bad decision
 * that happened to pay must not display its profit, so nothing stores one. A
 * future field named `*_pct` or `profit` in this shape is a regression, and the
 * E2E spec asserts the rendered page contains no digits in the dangerous case.
 */
export type DecisionOutcome = 'good' | 'bad' | 'failed'

export interface ReviewState {
  decision_id: string
  due_at: string
  /** Non-null only once an outcome is recorded: a process score alone is a half-review. */
  reviewed_at: string | null
  is_due: boolean
  reviews: number
}

export interface DecisionReview {
  decision_id: string
  review_id: string
  process_score: number
  outcome: DecisionOutcome | null
  process: ProcessBand
  quadrant: Quadrant
  /**
   * The one sentence this quadrant is permitted to print, **served by the server**.
   *
   * The frontend renders it and does not retype it: a UI-authored version of the
   * dangerous-quadrant warning is one careless PR away from congratulating
   * someone for a decision that lost them money the next time.
   */
  guidance: string
  reviewed_at: string
  /**
   * ⭐ **The reader's own words, or `null`.** Added 2026-10-05 (spec 056) ⭐ — the column
   * existed and the API was **not sending it**, so a sentence someone had written about
   * their own reasoning could not come back. That is the same shape as the missing history
   * endpoint one level in: a stored fact with no path to the reader.
   *
   * ⚠️ `null` and `""` are different answers — 「他当时写了什么」 and 「他当时什么都没写」
   * — and the response is able to tell them apart. ⭐ Do not collapse them.
   *
   * ⭐ **`outcome` above is nullable and that is red line 5 made visible**: measured,
   * `reviews.record()` gates only the outcome, so a process score may be written repeatedly
   * while the outcome stays blank. A history showing only completed rows would teach the
   * reader that the two halves are one thing.
   */
  note: string | null
}

/**
 * The capability matrix, and ⭐ **whether this is the demo library** (spec 057).
 *
 * ⚠️ **`is_demo` is read at boot, once, for `DemoBanner`.** The server field's description
 * used to claim this endpoint was already loaded by the shell, so the banner would be
 * free. ⭐ Measured: **no frontend file calls `/capabilities` at all** ⭐ — the matrix has
 * no consumer in the interface (`status.md` records it as an undecided orphan) ⇒ **one
 * extra request at boot**, which is what the server docstring now says.
 *
 * Only `is_demo` is typed here. ⭐ **The cells are not**: this file deliberately does not
 * restate a `Dataset` x `Market` matrix nobody renders, because a type for a field nothing
 * reads is a second copy that will drift (`F-248`: a table's existence is not evidence
 * that anything uses it).
 */
export interface CapabilitiesRead {
  /** ⭐ True when the database in use is `dev.py demo`'s seeded library. */
  is_demo: boolean
}

export function getCapabilities(): Promise<CapabilitiesRead> {
  return request<CapabilitiesRead>('/api/v1/capabilities')
}

/**
 * Every time a decision was reviewed, oldest first — `spec 056`.
 *
 * ⭐ **`DecisionReview[]`, deliberately not a second type.** The first version of this
 * declared its own interface, and **two ways of writing that were both wrong**:
 *
 * 1. `extends Omit<DecisionReview, never>` ⭐ — and `S-18 no-response-drift` walks only
 *    **literal** members, so the type was invisible to it. Measured: a bogus field added to
 *    it left the rule clean. (`F-257`)
 * 2. ⭐ **Writing the eight fields out** fixed the blindness and **broke something worse**:
 *    `S-18` matches a schema to a client type by **field set**, so a type holding all of
 *    `DecisionReviewRead`'s fields makes the correspondence **ambiguous** — ⭐ and the
 *    rule's response to ambiguity is silence, so it stopped reporting on the **single
 *    review** endpoint. Measured: deleting a *required* field from that type stayed green.
 *
 * ⇒ **One client type for one concept.** And the collapse fixed a real gap rather than
 * only tidying: `reviews.note` is a column the API was **dropping**, so a sentence the
 * reader wrote about their own reasoning could not come back even for the latest review.
 *
 * ⭐ **This is not what the retrospective page calls.** Measured 2026-10-05: in the
 * dangerous quadrant that page asserts **the whole page contains no digit**
 * (`e2e/retrospective.spec.ts:120` — 「deliberately stricter than the red line」), and a
 * review history is made of digits. ⇒ The instrument page reads this, beside the
 * decisions — the same page the card review history went on, for the same reason.
 *
 * ⚠️ **404 for a missing decision, `[]` for an unreviewed one.** Two different facts, and
 * this matches the card side rather than the note side.
 */
export function listDecisionReviewHistory(decisionId: string): Promise<DecisionReview[]> {
  return request<DecisionReview[]>(
    `/api/v1/decision-reviews/${encodeURIComponent(decisionId)}/reviews`,
  )
}

/**
 * Decisions already reviewed, most recent first.
 *
 * ⭐ Added 2026-09-28 (spec 030 follow-up) because the retrospective page's only
 * other list is the **due** one, and a decision leaves it the moment its review is
 * written — so a review you had already done was invisible on the page whose entire
 * subject is reviews, and the lesson composer was unreachable.
 *
 * Found by opening the app. ⭐ The E2E suite had passed throughout, because its
 * fixture returned an already-reviewed decision *inside the due queue* — a state
 * the server cannot produce. **A fixture describing a state the product cannot be in
 * makes the test agree with the fixture rather than with the product.**
 */
export function getRecentDecisionReviews(limit = 20): Promise<ReviewState[]> {
  return request<ReviewState[]>(`/api/v1/decision-reviews/recent?limit=${limit}`)
}

export function getDueDecisionReviews(asOf?: string, limit = 50): Promise<ReviewState[]> {
  const params = new URLSearchParams()
  if (asOf) params.set('as_of', asOf)
  if (limit !== 50) params.set('limit', String(limit))
  const query = params.toString()
  return request<ReviewState[]>(`/api/v1/decision-reviews/due${query ? `?${query}` : ''}`)
}

export function getDecisionReview(decisionId: string): Promise<{
  state: ReviewState
  /**
   * The words being graded, returned with the review so the page cannot show a
   * verdict without them. `decisions` is append-only, so this text cannot have
   * been edited to look better than it was.
   */
  decision: Decision
  latest: DecisionReview | null
}> {
  return request(`/api/v1/decision-reviews/${decisionId}`)
}

/**
 * Record a review. `outcome` is omitted before the review is due — not sent as
 * null, because "I have not scored it yet" and "I scored it as nothing" are
 * different statements and only one of them is a thing this product records.
 */
/**
 * The body `POST /api/v1/decision-reviews` accepts.
 *
 * ⭐ `outcome` and `note` are optional **because the review may not be due yet** ⭐ — ⭐ and
 * 「I have not scored it yet」 and 「I scored it as nothing」 are different statements, ⭐ so
 * the client omits the field rather than sending null.
 */
export interface DecisionReviewBody {
  decision_id: string
  process_score: number
  outcome?: DecisionOutcome | null
  note?: string | null
}

export function recordDecisionReview(body: DecisionReviewBody): Promise<DecisionReview> {
  return request<DecisionReview>('/api/v1/decision-reviews', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly fix: string | null

  constructor(failure: ApiFailure, status: number) {
    super(failure.message)
    this.name = 'ApiError'
    this.code = failure.code
    this.status = status
    this.fix = failure.fix ?? null
  }
}

/**
 * FastAPI's own validation body: `{detail: [{loc, msg, type}, ...]}`.
 *
 * Worth decoding rather than replacing with "输入不完整", because the predicate
 * editor produces these: a threshold sent as text, a date typed as `2026-13-01`.
 * The server already knows which field is wrong and says so; throwing that away
 * and telling the reader to check everything is how a form becomes a guessing
 * game.
 */
function describeValidation(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null
  const first = detail[0] as { loc?: unknown; msg?: unknown }
  const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null
  const message = typeof first.msg === 'string' ? first.msg : null
  if (!field && !message) return null
  const where = field === null ? '请求' : `字段「${String(field)}」`
  return `${where}被服务器拒绝：${message ?? '格式不符合要求'}`
}

/**
 * One HTTP helper for the whole client.
 *
 * ⭐ **Exported for `notes.ts` rather than duplicated there** (spec 026). The notes
 * client is its own file because `api.ts` is already 678 lines and covers five
 * concerns, but the *error* shape is a contract every page handles: one
 * `ApiError`, one normalisation of FastAPI's 422 envelope. A second `fetch`
 * wrapper would mean a second place where an error can be shaped differently —
 * and the note page's whole argument is that notes and cards differ in their
 * *rules*, not in how failures are reported.
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!response.ok) {
    // FastAPI's own validation errors (422) use `{detail: [...]}` rather than
    // our envelope; normalise so callers only ever handle one shape.
    const body = (await response.json().catch(() => null)) as
      | ApiFailure
      | { detail?: unknown }
      | null

    if (body && typeof body === 'object' && 'code' in body) {
      throw new ApiError(body as ApiFailure, response.status)
    }
    throw new ApiError(
      {
        code: 'REQUEST_REJECTED',
        message:
          (body && typeof body === 'object' ? describeValidation(body.detail) : null) ??
          `请求被拒绝（HTTP ${response.status}）`,
      },
      response.status,
    )
  }

  return (await response.json()) as T
}

export function listWatchlist(): Promise<WatchlistEntry[]> {
  return request<WatchlistEntry[]>('/api/v1/watchlist')
}

/**
 * One pool row paired with its own fetch outcome.
 *
 * The batch has no status of its own — the server prices each followed
 * instrument independently and reports each truth separately, so "three
 * priced, one refused, one not quoted" survives the trip. Keyed by
 * `(market, code)` because the code alone is not an instrument (000001 is
 * both an index and a bank).
 */
export interface PoolQuote {
  market: string
  code: string
  display: string
  quote: QuoteResult
}

/**
 * Price every instrument currently followed.
 *
 * The second of the pool page's two requests, for the same reason the
 * instrument page splits record from price: the list is local and cannot
 * fail, this one crosses the network and will. Merging them would let a
 * source outage blank the page where the user's own reasons live.
 */
export function getWatchlistQuotes(): Promise<PoolQuote[]> {
  return request<PoolQuote[]>('/api/v1/watchlist/quotes')
}

/** One predicate the server found due, with the decision it came from. */
/**
 * ⭐ Why the page says what it says about a due criterion.
 *
 * `crossed` / `not_crossed` are facts about the **comparison**.
 * `warming` / `undetermined` / `no_bars` are facts about **us** — the metric is too
 * young, or the catalogue has never heard of it, or the source has no bars.
 *
 * ⭐ The last three are kept apart because they call for different reader actions
 * (「等一周」/「这里不会有」/「换个代码」), and collapsing them into 「条件没成立」 would
 * have the program vouching for a comparison nobody performed.
 */
export type MetricState =
  | 'crossed'
  | 'not_crossed'
  | 'warming'
  | 'undetermined'
  | 'no_bars'
  | 'not_announced'
  // ⭐⭐ `not_reported` — the report came out and does not carry this figure.
  // ⚠️ **It is not `not_announced`**: that one resolves when the next report lands.
  // This one has no remedy — `--` is how a company says the number is undefined — so
  // the screen must not imply a date. (`S-02`: a `has_*` field here would be red.)
  | 'not_reported'

export interface MetricReading {
  state: MetricState
  /** The metric's name, e.g. `MA20`. Falls back to the raw token when unknown. */
  label: string
  /** `null` whenever `state` is not a comparison. ⭐ Never `0` (红线 6). */
  value: number | null
  /**
   * Which bar the value came from. ⭐ `null` for `undetermined` and `no_bars`, and set
   * for `warming` — a second, independent signal that separates 「too young to say」 from
   * 「never going to say」 even if a caller only looks at this.
   */
  as_of: string | null
  /**
   * How many bars this metric needs before it has a value. ⭐ `null` for a price fact,
   * which needs one bar and never warms up.
   */
  period: number | null
  /**
   * ⭐ How many bars were actually read, counted **server-side**. ⭐ Sent rather than
   * derived here: trading days are not calendar days, and a client-side count is wrong by
   * the number of public holidays — which would make 「还差 N 根」 a promise the page
   * does not keep.
   */
  bars_available: number | null
  /** ⭐ The latest report period that *had* been announced when this period had
   *  not. Meaningful only for `not_announced`, and it is a fact rather than a flag
   *  (`S-02` would be red on a `has_*` name here). */
  latest_announced_period_end: string | null
  /** ⭐ The report period this value summarises. `period` above is a
   *  different question that happens to share the word: how many *bars* it needs. */
  period_end: string | null
}

export interface AttentionItem {
  kind: 'kill_criterion_due'
  item: {
    decision_id: string
    market: string
    code: string
    display: string
    action: DecisionAction
    criterion: KillCriterion
  }
  /**
   * ⭐ Absent means the server could not read any bars for this instrument, which is
   * **not** the same as a metric that evaluated cleanly to `warming`. ⭐ The distinction
   * is "we have no data at all" against "we have the data and the metric is too young" —
   * a different fault, on a different side, with a different fix.
   */
  metric: MetricReading | null
  /**
   * ⭐ The sentence, already rendered by `domain/criterion_sentence.py` (spec 044).
   *
   * ⭐ It lives on the **attention item** rather than on the metric, because `metric` is
   * `null` when the server could not read any bars — ⭐ and the reader needs a sentence
   * exactly then. Putting it on the metric would have left one case unwritten and pushed a
   * fallback back into this file, which is the second home the move existed to remove.
   *
   * ⭐ Render verbatim. Do not re-derive it here: a notification sends the same string,
   * and two wordings is one drift away.
   */
  verdict: string
  /**
   * ⭐ Whether the reader is being told something they could act on today. `false` for
   * the three 「we don't know」 states. ⭐ A flag rather than something derived from the
   * text, because the styling says the same thing as the sentence.
   */
  adjudicable: boolean
}

/** Whether the market opens today — or that the probe could not tell. */
export type TradingDayVerdict = 'trading_day' | 'non_trading_day' | 'unknown'

/** What the verdict rests on. `none` accompanies `unknown` only. */
export type TradingDayBasis = 'probe' | 'weekend' | 'none'

export interface MarketStatus {
  verdict: TradingDayVerdict
  basis: TradingDayBasis
  /** The newest date with a daily bar — the fact behind 「休市」. */
  last_trading_date: string | null
  checked_at: string
}

/**
 * Which queue a count belongs to — a **logical name**, not a path.
 *
 * The server deliberately does not send a URL. The route table (`routing.ts`) is
 * the single source of truth for where a view lives (spec 022), and a path in an
 * API response would be a second copy of that fact — the kind that works in dev
 * and 404s in prod, with nothing to grep.
 */
export type QueueName = 'cards' | 'reviews'

/** A count and nothing else. No due date, no title, no ordering, no link. */
export interface DueCount {
  queue: QueueName
  /**
   * How many have come round now.
   *
   * Not a score: nothing here is summed, compared against a target, or turned
   * into a completion fraction. See spec 023 §二 for why a count of the reader's
   * *own commitments* is a statement of fact, and why that is the only kind of
   * thing red line 8 lets the product interrupt with.
   */
  count: number
}

export interface Today {
  generated_at: string
  attention: AttentionItem[]
  /**
   * The second thing the today page is allowed to bring: how many of the reader's
   * own review commitments have come round. The first is `attention` above.
   */
  due: {
    cards: DueCount
    reviews: DueCount
  }
  market_status: MarketStatus
}

/**
 * What deserves attention today (the today page's block ①).
 *
 * "Due" means the cutoff date you wrote has arrived — the question can now be
 * asked. It does **not** mean triggered: the metric has no data source yet, so
 * the client must say "go verify", never announce an outcome.
 */
export function getToday(): Promise<Today> {
  return request<Today>('/api/v1/today')
}

/**
 * ⭐ **What the ticker means, before anything is written (spec 047).**
 *
 * ⭐ **This function had no caller at all**, which is the whole of the defect: the
 * server has answered 「which instrument is this?」 correctly since D1 landed, and
 * `POST /watchlist` has rejected an ambiguous code with `DATA_SOURCE_TICKER_AMBIGUOUS`
 * and the sentence 「choose one」 — **while the page had nothing to choose with.**
 *
 * Measured against the running server, before this existed:
 *
 * ```
 *   GET  /api/v1/instruments/resolve?ticker=000001
 *     -> 200 {"status":"ambiguous","candidates":["sh","sz"],"display":null}
 *   POST /api/v1/watchlist {"ticker":"000001","reason":"…"}
 *     -> 400 {"code":"DATA_SOURCE_TICKER_AMBIGUOUS",
 *             "message":"000001 exists on sh / sz — choose one"}
 * ```
 *
 * ⭐ **`status` is a three-state enum and not a boolean**, for the reason
 * `constitution` 7.7 gives elsewhere: 「not a code at all」 and 「a code, but two of
 * them」 need different sentences, and a boolean would make the caller recover the
 * difference by inspecting which fields happened to be null.
 *
 * ⚠️ **`display` is null exactly when `candidates` is non-empty**, by the server's
 * own contract (「Absent while ambiguous」). So a client that renders `display` and
 * falls back to `code` when it is null is correct, and one that assumes `display` is
 * always there is not.
 */
export type ResolveStatus = 'resolved' | 'ambiguous'

export interface TickerResolution {
  status: ResolveStatus
  code: string
  /** Absent while `ambiguous` — a bare code is not an instrument. */
  market: string | null
  asset_type: string | null
  /** Conventional form, e.g. `600519.SH`. Absent while ambiguous. */
  display: string | null
  /** Markets the code could mean. Empty unless `status` is `ambiguous`. */
  candidates: string[]
}

/**
 * ⭐ **A refusal is a normal answer, not an exception.**
 *
 * `ticker=zzz` comes back **400** with the standard envelope, and `data.resolve()`
 * turns a non-2xx into a thrown `ApiError`. So this function catches it and returns
 * a third state rather than letting every caller re-implement the same catch:
 *
 * ```
 *   'unusable'  ->  { status: 'unusable', message, code, detail }
 * ```
 *
 * ⚠️ **`message` is the server's sentence, verbatim and untranslated.** It is data
 * layer wording about 「this is not a code」, and translating it here would mean a
 * frontend table of error codes that can drift from `api/errors.py` — which `S-05`
 * exists to prevent for the other two of the three sources (docs ↔ enum ↔ code).
 * The frontend has no such guarantee, so this spec does not add one.
 */
export interface UnusableTicker {
  status: 'unusable'
  /** The server's own sentence. Never invented here. */
  message: string
  code: string
  detail: string | null
}

export type TickerAnswer = TickerResolution | UnusableTicker

export function resolveTicker(ticker: string): Promise<TickerAnswer> {
  return request<TickerResolution>(
    `/api/v1/instruments/resolve?ticker=${encodeURIComponent(ticker.trim())}`,
  ).catch((cause: unknown) => {
    if (cause instanceof ApiError) {
      return {
        status: 'unusable',
        message: cause.message,
        code: cause.code,
        detail: cause.fix,
      }
    }
    throw cause
  })
}

/**
 * ⭐⭐ **Is this card on the review queue, and when is it next due? (spec 048)**
 *
 * ⭐ **This function and `POST /cards/{id}/schedule` existed together for months with
 * the `POST` having zero callers, because without a read the interface cannot tell
 * 「already enrolled」 from 「never enrolled」 — and it cannot infer it from
 * `GET /review/due`, which returns only what is *due* right now.** Measured on
 * 2026-10-02 against an empty database:
 *
 * ```
 *   POST /api/v1/cards                 -> 201 card_1790916668533
 *   GET  /api/v1/review/due            -> 0 items    (the server volunteers nothing)
 *   POST /api/v1/cards/{id}/schedule   -> 201 {"state":"learning", …}
 *   GET  /api/v1/review/due            -> 1 item
 * ```
 *
 * ⇒ **The review queue could only be filled by writing code.** That is the same shape
 * this repository has now met three times: J3's 「机制齐了却够不着」, a
 * `listNoteReviews` with no callers, and two implementations of `RecordTimeline`.
 *
 * ⚠️ **The rejection here is a normal answer and it is a `409`, not a `404`** —
 * `GET /notes/{id}/schedule` answers 404 for the same state, and copying that was
 * this spec's first move, but `api/errors.py` had already decided the card's case:
 *
 * > K3. Both are 409 rather than 404 on purpose: the *card* exists, and what
 * > conflicts is the request with the card's scheduling state. Answering 404 would
 * > tell the user their card is gone when it is sitting right there.
 *
 * ⇒ So callers get **three** states, and that is the contract:
 *
 * | outcome            | meaning                          | what the interface owes the reader |
 * |--------------------|----------------------------------|------------------------------------|
 * | `Schedule`         | enrolled, here is when it is due  | 「下次 …」                          |
 * | `null` + 409       | not enrolled — an ordinary empty  | offer the button                    |
 * | `null` + anything else | **do not know**                | say so; **never offer the button** |
 *
 * ⭐ **That last row is the one that matters.** `VaultPage`'s note enrolment reads
 * `.catch(() => false)` — *any* failure becomes 「not enrolled」 — so a backend outage
 * shows a 「加入复习」 button that is guaranteed to fail. This function keeps the
 * three apart by returning `null` and letting the caller ask **which** failure it was.
 */
export async function getCardSchedule(cardId: string): Promise<Schedule | null> {
  try {
    return await request<Schedule>(`/api/v1/cards/${encodeURIComponent(cardId)}/schedule`)
  } catch (cause) {
    // ⭐ Only this one code means 「not on the queue」. Anything else — the server is
    // down, the card id is stale, a future 500 — is **not knowing**, and collapsing it
    // into "not enrolled" is how a broken link gets a working-looking button.
    if (cause instanceof ApiError && cause.code === 'CARD_NOT_SCHEDULED') return null
    throw cause
  }
}

/**
 * The three writes. Each takes an optional `market`.
 *
 * It is optional rather than required because a code like `600519` can only be
 * Shanghai, and demanding a market for it would be noise. It is accepted
 * because a code like `000001` is *both* the Shanghai Composite and Ping An
 * Bank — and the instrument page knows which one it is showing, so it can say
 * so. Without this the page's own buttons would fail on exactly the codes the
 * pool had to disambiguate when they were added.
 *
 * ⭐ **As of spec 047 the pool page always passes it**, because it has just resolved
 * the ticker and therefore knows. The parameter stays optional for the other callers
 * that have a `(market, code)` pair already in hand.
 */
/** The body `POST /api/v1/watchlist` accepts. `reason` is the point of the endpoint. */
export interface WatchlistAddBody {
  ticker: string
  reason: string
  market?: string | null
  /** ⭐ Declared and never sent ⭐ — the server defaults it, ⭐ and a client that cannot
   *  send it is not a client that is missing a field. ⭐ This line is what `S-18`'s
   *  optional-versus-required split exists to be able to say. */
  asset_type?: string
}

/** The body `POST /api/v1/watchlist/reason` accepts. Instrument, not event id. */
export interface WatchlistReasonBody {
  ticker: string
  reason: string
  market?: string | null
}

/**
 * The body `POST /api/v1/watchlist/remove` accepts.
 *
 * ⭐ **`reason` is declared and never sent**, ⭐ and that is correct: ⭐ `watchlist.py:72`
 * says 「A reason is optional — leaving needs no justification」. ⭐ `S-18` reports an
 * undeclared optional field as a note rather than an error ⭐ precisely so this line can
 * exist ⭐ — **a client that does not exercise an optional path is not drift.**
 */
export interface WatchlistRemovalBody {
  ticker: string
  market?: string | null
  reason?: string | null
}

export function addToWatchlist(
  ticker: string,
  reason: string,
  market?: string,
): Promise<RecordedEvent> {
  return request<RecordedEvent>('/api/v1/watchlist', {
    method: 'POST',
    body: JSON.stringify({ ticker, reason, market } satisfies WatchlistAddBody),
  })
}

export function removeFromWatchlist(ticker: string, market?: string): Promise<RecordedEvent> {
  return request<RecordedEvent>('/api/v1/watchlist/remove', {
    method: 'POST',
    body: JSON.stringify({ ticker, market } satisfies WatchlistRemovalBody),
  })
}

export function reviseReason(
  ticker: string,
  reason: string,
  market?: string,
): Promise<RecordedEvent> {
  return request<RecordedEvent>('/api/v1/watchlist/reason', {
    method: 'POST',
    body: JSON.stringify({ ticker, reason, market } satisfies WatchlistReasonBody),
  })
}

/**
 * Read one instrument: identity, follow state, and the whole log.
 *
 * Succeeds for an instrument nobody has followed — the endpoint answers 200 with
 * `follow.status === 'never'`, because the page it feeds is where you decide
 * whether to follow it. A 404 here would mean "you cannot look at this", which
 * is the opposite of what the page is for.
 */
export function getInstrument(market: string, code: string): Promise<InstrumentDetail> {
  return request<InstrumentDetail>(
    `/api/v1/instruments/${encodeURIComponent(market)}/${encodeURIComponent(code)}`,
  )
}

/**
 * Price one instrument.
 *
 * Deliberately a separate request from `getInstrument`. This one crosses the
 * network and will fail sometimes; the record does not. Merging them would let a
 * source outage blank a page whose content — the reason you wrote, and every
 * change you have made since — is still perfectly true.
 */
export function getQuote(market: string, code: string): Promise<QuoteResult> {
  return request<QuoteResult>(
    `/api/v1/instruments/${encodeURIComponent(market)}/${encodeURIComponent(code)}/quote`,
  )
}

/**
 * ⭐⭐ **What this build can compute, for one market** (spec 058).
 *
 * ⭐ **This exists because the product was lying by example.** Measured before the route
 * did: `DecisionForm`'s kill-criterion input had `placeholder="gross_margin"`, ⭐ and that
 * token is in **neither** `metrics.CATALOGUE` (24) nor `metrics.FINANCIAL_CATALOGUE` (8).
 * ⭐ The domain validates shape only (`[a-z][a-z0-9_]*`), so `POST /api/v1/decisions`
 * answered **201** and stored it verbatim; ⭐ `/today` showed nothing until the criterion
 * came due, and by then the sentence blamed the data. ⭐ Gross margin *is* computable —
 * the token is `gp_margin`, label 「销售毛利率」. ⭐ `metrics.read_metric` has answered this
 * with `UNKNOWN_METRIC` the whole time; ⭐ nobody asked until months later.
 *
 * ⭐ **`market` is required, and `catalogue.metrics` is already filtered by it.** Measured:
 * `financial` is `pending` for `bj`, ⭐ so a Beijing instrument can compute **none** of the
 * 32 and gets an empty list with all 32 in `unavailable`. ⭐ That is a real answer, not an
 * error — ⭐ and it is the sentence a `.BJ` reader most needs.
 */
export interface MetricCatalogue {
  generated_at: string
  market: string
  metrics: MetricCell[]
  /**
   * ⭐ Tokens this market cannot compute. **Sent, not hidden** — the domain accepts an
   * uncomputable metric on purpose, so omitting these would make the interface argue with
   * a decision the reader is allowed to make.
   */
  unavailable: string[]
}

/** One computable metric. ⭐ `label` is what the reader sees; `token` is what they write. */
export interface MetricCell {
  token: string
  label: string
  /** ⭐ `daily` comes from 行情 bars, `financial` from reported figures. */
  dataset: string
}

export function getMetrics(market: string): Promise<MetricCatalogue> {
  return request<MetricCatalogue>(`/api/v1/metrics?market=${encodeURIComponent(market)}`)
}

/**
 * Record a decision. There is no update and no delete, on purpose.
 *
 * The three required fields are required because of what the row is *for*:
 * `rationale` is the sentence you will be held to, `counter_evidence` is the
 * only field that can resist confirmation bias, and `kill_criteria` is what
 * lets the data come and find you. The server enforces all three — this
 * function does not re-check them, because a second copy of a rule is a second
 * chance to disagree with it.
 *
 * `id` is deliberately absent from the request. It is the write moment, it is
 * generated server-side, and the schema rejects any body that names it
 * (ADR-0011, and check S-06).
 */
export function recordDecision(input: DecisionInput): Promise<Decision> {
  return request<Decision>('/api/v1/decisions', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

/**
 * The most recent decisions across every instrument, newest first.
 *
 * Not used by the instrument page — that page gets its own decisions with the
 * instrument itself, untruncated. This is for the "what have I been doing
 * lately" view (T1), which does not exist yet; it is here because the endpoint
 * is, and leaving a working endpoint unwrapped invites the next person to write
 * a second `fetch`.
 */
export function listRecentDecisions(limit = 50): Promise<Decision[]> {
  return request<Decision[]>(`/api/v1/decisions?limit=${limit}`)
}

/**
 * List cards, newest first, optionally filtered to one instrument.
 *
 * The instrument page passes its own market and code; a future knowledge view
 * will call this without them. An empty result is `[]`, not an error.
 */
export function listCards(options?: {
  market?: string
  code?: string
  claim_type?: ClaimType
  origin?: CardOrigin
  status?: CardStatus
  limit?: number
}): Promise<Card[]> {
  const params = new URLSearchParams()
  if (options?.market) params.set('market', options.market)
  if (options?.code) params.set('code', options.code)
  if (options?.claim_type) params.set('claim_type', options.claim_type)
  if (options?.origin) params.set('origin', options.origin)
  if (options?.status) params.set('status', options.status)
  if (options?.limit) params.set('limit', String(options.limit))
  const query = params.toString()
  return request<Card[]>(`/api/v1/cards${query ? `?${query}` : ''}`)
}

/**
 * Record a card. There is no update and no delete, on purpose.
 *
 * A card is a signed statement: `content` is the claim, `source_url` and
 * `source_title` are where it came from, and the write is one-way because
 * editing a claim would quietly rewrite the record of what you once believed.
 * Changing your mind is a new card, never an edit of the old one. `id` is
 * deliberately absent from the input — it is the write moment, generated
 * server-side, and the schema rejects any body that names it (S-06).
 */
export function createCard(input: CardInput): Promise<Card> {
  return request<Card>('/api/v1/cards', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

/**
 * Upgrade an `ai_generated` card to `user_written`.
 *
 * The isolation red line: an AI candidate stays flagged until a person has
 * actually looked at the source. The server refuses this for any card that is
 * not `ai_generated` (409).
 */
export function verifyCard(cardId: string): Promise<Card> {
  return request<Card>(`/api/v1/cards/${encodeURIComponent(cardId)}/verify`, {
    method: 'PATCH',
  })
}

/**
 * Read one card.
 *
 * The review page needs the claim and its source, and it shows both rather than
 * only the claim: what is being reviewed has to be checkable against where it
 * came from, or "review" is just recitation (the provenance rule, in the UI).
 */
export function getCard(cardId: string): Promise<Card> {
  return request<Card>(`/api/v1/cards/${encodeURIComponent(cardId)}`)
}

/**
 * Retire an active card to `converged` with a user-written reason (K2).
 *
 * The lifecycle exit: the card is not deleted and stays visible, but it
 * leaves the current body of claims. The reason is mandatory and is written
 * by the user, never generated by an agent (red line 15).
 */
export function convergeCard(cardId: string, reason: string): Promise<Card> {
  return request<Card>(`/api/v1/cards/${encodeURIComponent(cardId)}/converge`, {
    method: 'PATCH',
    body: JSON.stringify({ reason }),
  })
}

export interface DailyBar {
  symbol: { market: string; code: string }
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  /**
   * Turnover in CNY, or `null` when the source does not publish it.
   *
   * ⭐ Never `0`. Verified live against Tencent on 2026-09-29: 214 bars, every one
   * `null`. `close * volume` would be an estimate wearing the costume of a
   * measurement, which is why the model leaves the field nullable.
   */
  amount: number | null
  /**
   * The adjustment basis the prices were normalised to. `1.0` is unadjusted.
   *
   * `models/market.py:86-89` is why it travels with the bar instead of being
   * re-derived on arrival: a series can be put back on any basis without
   * refetching, and refetching is where the answer would change.
   */
  adj_factor: number
  /**
   * When this bar was pulled, ISO-8601.
   *
   * ⚠️ Not read by any page today, and that is its honest state rather than an
   * oversight: `S-18` (spec 053) measured that the server has been sending this
   * all along and no check could see that the client had not declared it.
   * ⭐ Declared now so that the day a page *does* read it, the compiler is
   * already asking the question.
   */
  fetched_at: string
  /**
   * Which provider this bar came from.
   *
   * ⚠️ Distinct from the envelope's `source` further down, which names the
   * answer as a whole. ⭐ Two fields with one word in them, and the page caption
   * shows the envelope's ⭐ — see `KlineChart.tsx:373`.
   */
  source: string
}

/**
 * One indicator series, aligned index-for-index with `DailySeries.bars`.
 *
 * ⭐ `null` in `values` is not a gap to be smoothed over — it means 「this bar is inside
 * the warm-up window, the value does not exist yet」. The server sends the same length as
 * `bars` so the client never has to work out which bar a value belongs to.
 */
export interface IndicatorSeries {
  /** Stable id, e.g. `ma20`. Safe to switch on. */
  name: string
  /** Human label, e.g. `MA20`. */
  label: string
  /** One entry per bar, oldest first. Never shorter than `bars`, never longer. */
  values: (number | null)[]
}

/** Bars and their indicators, as one value. */
export interface DailySeries {
  bars: DailyBar[]
  /**
   * ⭐ May be **empty**: a window shorter than every indicator's period yields no series
   * at all. That is a fact about the data, not a failure, and the chart has to say so
   * rather than draw an empty legend entry.
   */
  indicators: IndicatorSeries[]
  /**
   * ⚠️ The `start` **the caller passed**, verbatim ⭐ — not the window the server
   * fetched. Those differ: `MAX_DAILY_WINDOW_DAYS = 1500` narrows the request to
   * about four years, and Tencent then caps it at 320 bars, which is about fifteen
   * months. ⭐ Both clamps used to be invisible, and `?start=2015-01-01` returned
   * `status="ok"` with no error while delivering nine fewer years than asked for.
   *
   * ⚠️ `null` means **the caller passed nothing** ⭐ — which is *not* the same as
   * 「they asked for nothing」. ⭐ It is 「we chose 320 days for them」, and a page
   * needs two different sentences for those.
   */
  requested_start: string | null
  requested_end: string | null
  /** First delivered bar's `trade_date`. `null` when there are no bars at all. */
  delivered_from: string | null
  /** Last delivered bar's `trade_date`. `null` when there are no bars at all. */
  delivered_to: string | null
  /**
   * ⭐ True when `delivered_from` is more than **seven days** after
   * `requested_start` ⭐ — that is, when the gap is wider than a weekend plus this
   * market's holiday clusters.
   *
   * ⚠️⚠️ **It is not the truth. The two dates are.** `requested_start` is a
   * *calendar* day and `delivered_from` is a *trading* day, ⭐ so the comparison
   * needs slack, ⭐ and slack is a judgement rather than a measurement ⭐ — the first
   * version compared them directly and reported `clamped: true` for `2024-01-01`,
   * which was New Year's Day. ⭐ A page that shows both dates is right even when
   * this boolean is wrong; ⭐ a page that shows only this boolean is right only when
   * the judgement was.
   *
   * ⭐ And `pyproject.toml:130-132` says display wording lives in `frontend/`,
   * ⭐ so the sentence itself belongs on the page, not here.
   */
  clamped: boolean
}

/**
 * ⭐ Same envelope as `QuoteResult`, field for field.
 *
 * A second shape for the same four states would let the two disagree about what a fetch
 * can be in, and the disagreement would show up as a branch that is unreachable in one
 * component and reachable in the other.
 */
export interface DailyResult {
  status: DataStatus
  /**
   * `null` for every state but `ok`. ⭐ Not `[]` — an empty array here would be a fifth
   * state the envelope does not have, and it would read as 「this instrument has no
   * history」 when the truth might be 「every source refused」.
   */
  value: DailySeries | null
  reason: string | null
  detail: string | null
  error_code: string | null
  source: string | null
  fetched_at: string | null
  /** True when every live source failed and these are the last known good bars. */
  stale: boolean
}

/**
 * Daily bars for one instrument, oldest first.
 *
 * ⭐ The four states come back as they arrive. Mapping `no_data` onto an empty array here
 * would move the distinction into the component, and the component is where it gets lost.
 */
export function getDaily(
  market: string,
  code: string,
  query: { start?: string; end?: string } = {},
): Promise<DailyResult> {
  const search = new URLSearchParams()
  if (query.start !== undefined) search.set('start', query.start)
  if (query.end !== undefined) search.set('end', query.end)
  const suffix = search.size > 0 ? `?${search.toString()}` : ''
  return request<DailyResult>(`/api/v1/instruments/${market}/${code}/daily${suffix}`)
}

// ---------------------------------------------------------------------------
// 沪深300 成分（spec 052）
// ---------------------------------------------------------------------------

/**
 * 一段被观察到的成员资格。
 *
 * ⚠️ first_observed_on / last_observed_on 是**我们观察到的窗口**，不是生效日。
 * 源给的 updateDate 是每周一批的入库戳（实测：五个值全是周一，而它在两次定期调整上
 * 精确等于编制方案的生效日，只因为那两天的生效日恰好落在周一）。
 */
export interface UniverseMembership {
  market: string
  code: string
  name: string
  first_observed_on: string
  last_observed_on: string
  is_latest: boolean
}

/**
 * 「我们知道的最后一天」—— 它跟着每一个答案走。
 *
 * ⭐ resolution 是一个**事实**，程序可以据此分支；
 * ⚠️ 而那句「至多落后七天，这不是故障」是**产品文案**，写在这一页而不是后端 ——
 * pyproject.toml 记着 display wording 历来住在 frontend/。
 */
export interface UniverseFreshness {
  index_code: string
  latest_grid_point: string | null
  members: number | null
  source: string | null
  resolution: string
  /** ⭐ False = 「我们从来没取过」，那**不是**「名单是空的」。 */
  ever_swept: boolean
}

export interface Universe {
  freshness: UniverseFreshness
  members: UniverseMembership[]
}

/**
 * 名单，加上它自己有多旧。
 *
 * ⚠️ 与名单分开，是因为**它们的新鲜度不同**：名单可以被缓存，
 * 而 useResource 在失败时不清 data（useResource.ts:88），
 * 所以一个不自带新鲜度的列表会在源挂掉时看起来仍然新鲜。
 */
export function getUniverse(q?: string): Promise<Universe> {
  const search = new URLSearchParams()
  if (q !== undefined && q.trim() !== '') search.set('q', q.trim())
  const suffix = search.size > 0 ? `?${search.toString()}` : ''
  return request<Universe>(`/api/v1/universe${suffix}`)
}

/**
 * ⭐ 一只票的全部区间 —— **不是只有当前那一段**。
 *
 * ⚠️ 一只 2013 年被摘出去的票在最新名单里**没有行**，而读者翻自己 2013 年的决策
 * 需要那一行来显示名字。⇒ 这是「出现过的」真正需要的端点，名单本身补不回来。
 */
export function getUniverseHistory(
  market: string,
  code: string,
): Promise<UniverseMembership[]> {
  return request<UniverseMembership[]>(`/api/v1/universe/history/${market}/${code}`)
}