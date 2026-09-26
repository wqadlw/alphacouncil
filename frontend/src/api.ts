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
}

/** The four states a fetch can be in (constitution 4.6). Never collapsed. */
export type DataStatus = 'ok' | 'no_data' | 'error' | 'unavailable'

export interface Quote {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
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
 * The three writes. Each takes an optional `market`.
 *
 * It is optional rather than required because a code like `600519` can only be
 * Shanghai, and demanding a market for it would be noise. It is accepted
 * because a code like `000001` is *both* the Shanghai Composite and Ping An
 * Bank — and the instrument page knows which one it is showing, so it can say
 * so. Without this the page's own buttons would fail on exactly the codes the
 * pool had to disambiguate when they were added.
 */
export function addToWatchlist(
  ticker: string,
  reason: string,
  market?: string,
): Promise<RecordedEvent> {
  return request<RecordedEvent>('/api/v1/watchlist', {
    method: 'POST',
    body: JSON.stringify({ ticker, reason, market }),
  })
}

export function removeFromWatchlist(ticker: string, market?: string): Promise<RecordedEvent> {
  return request<RecordedEvent>('/api/v1/watchlist/remove', {
    method: 'POST',
    body: JSON.stringify({ ticker, market }),
  })
}

export function reviseReason(
  ticker: string,
  reason: string,
  market?: string,
): Promise<RecordedEvent> {
  return request<RecordedEvent>('/api/v1/watchlist/reason', {
    method: 'POST',
    body: JSON.stringify({ ticker, reason, market }),
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
