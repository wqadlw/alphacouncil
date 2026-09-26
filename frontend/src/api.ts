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
          response.status === 422
            ? '输入不完整 — 标的代码与理由都必须填写。'
            : `请求被拒绝（HTTP ${response.status}）`,
      },
      response.status,
    )
  }

  return (await response.json()) as T
}

export function listWatchlist(): Promise<WatchlistEntry[]> {
  return request<WatchlistEntry[]>('/api/v1/watchlist')
}

export function addToWatchlist(ticker: string, reason: string): Promise<RecordedEvent> {
  return request<RecordedEvent>('/api/v1/watchlist', {
    method: 'POST',
    body: JSON.stringify({ ticker, reason }),
  })
}

export function removeFromWatchlist(ticker: string): Promise<RecordedEvent> {
  return request<RecordedEvent>('/api/v1/watchlist/remove', {
    method: 'POST',
    body: JSON.stringify({ ticker }),
  })
}
