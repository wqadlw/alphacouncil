/**
 * API fixtures for the browser tests (spec 010).
 *
 * The app under test is the real build; its `/api/v1/**` traffic is answered
 * here from fixtures that mirror the documented response shapes — the same
 * shapes the pytest API tests pin on the other side of the wire. Market data
 * is deliberately mocked: the four data states (no_data / error / stale /
 * unavailable) exist precisely where live sources cannot be summoned on
 * demand, and an E2E suite that flaked with the weather would train everyone
 * to ignore red.
 *
 * Any unmatched `/api/v1` path fails loudly with a 404 that names the missing
 * fixture — a new endpoint must be wired *on purpose*, never silently
 * answered by a catch-all.
 */

import type { Page } from '@playwright/test'

const STAMP = '2026-09-24T07:00:00Z'

export const STAMP_ISO = STAMP

type Body = Record<string, unknown>

/**
 * Intercept every `/api/v1/**` call and answer from `handlers`, keyed by
 * request path (query strings ignored) — a bare path matches any method, or
 * key it as `GET /api/v1/today` to pin the verb. Unmatched paths 404 loudly.
 */
export async function routeApi(
  page: Page,
  handlers: Record<string, Body | number>,
): Promise<void> {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()
    const handler = handlers[`${method} ${path}`] ?? handlers[path]
    if (handler === undefined) {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: `e2e fixture missing for ${path}` }),
      })
      return
    }
    if (typeof handler === 'number') {
      await route.fulfill({ status: handler })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(handler) })
  })
}

export function quoteResult(price: number, changePct: number): Body {
  return {
    status: 'ok',
    value: {
      price,
      prev_close: price * 1.01,
      change_pct: changePct,
      open: price,
      high: price * 1.01,
      low: price * 0.99,
      volume: 2_400_000,
      amount: 297_000_000,
      quoted_at: STAMP,
      source: 'tencent',
      fetched_at: STAMP,
    },
    reason: null,
    detail: null,
    error_code: null,
    source: 'tencent',
    fetched_at: STAMP,
    stale: false,
  }
}

function errorResult(): Body {
  return {
    status: 'error',
    value: null,
    reason: null,
    detail: 'all sources refused',
    error_code: 'DATA_SOURCE_UNAVAILABLE',
    source: null,
    fetched_at: null,
    stale: false,
  }
}

/** The today page's server block: one due criterion, market closed (weekend). */
/**
 * The `due` block, and nothing but a count per queue.
 *
 * Deliberately mirrors the server contract exactly: `queue` is a logical name,
 * not a path, because the route table is the frontend's single source of truth
 * (spec 022) and a URL here would be a second copy of it.
 */
export function due(cards = 0, reviews = 0): Body {
  return {
    cards: { queue: 'cards', count: cards },
    reviews: { queue: 'reviews', count: reviews },
  }
}

export function todayClosed(): Body {
  return {
    generated_at: STAMP,
    attention: [
      {
        kind: 'kill_criterion_due',
        item: {
          decision_id: '2026-09-20T01:00:00.000Z',
          market: 'sh',
          code: '600519',
          display: '600519.SH',
          action: 'buy',
          criterion: { metric: 'revenue_yoy', operator: '<', threshold: 0.55, as_of: '2026-09-20' },
        },
        // ⭐ `revenue_yoy` is a financial metric, and D4 is not built — so the honest
        // answer is `undetermined`, and the page has to say so rather than let a
        // criterion nobody evaluated look like one that held.
        metric: {
          state: 'undetermined',
          label: 'revenue_yoy',
          value: null,
          as_of: null,
          period: null,
          bars_available: null,
        },
      },
    ],
    due: due(),
    market_status: {
      verdict: 'non_trading_day',
      basis: 'weekend',
      last_trading_date: '2026-09-24',
      checked_at: STAMP,
    },
  }
}

/**
 * ⭐ One due criterion per evaluable state (spec 040).
 *
 * Four rows on purpose: the three 「we cannot tell you」 states must be **distinguishable
 * on screen**, and a fixture carrying only one of them cannot prove that. A single
 * "no data" sentence for all of them is the defect §4.6 names.
 */
export function todayEveryState(): Body {
  const row = (
    id: string,
    metric: string,
    state: string,
    value: number | null,
    as_of: string | null,
    period: number | null = null,
    bars: number | null = null,
  ) => ({
    kind: 'kill_criterion_due',
    item: {
      decision_id: id,
      market: 'sh',
      code: '600519',
      display: '600519.SH',
      action: 'buy' as const,
      criterion: { metric, operator: '<' as const, threshold: 1200, as_of: '2026-09-20' },
    },
    metric: { state, label: metric, value, as_of, period, bars_available: bars },
  })
  return {
    generated_at: STAMP,
    attention: [
      row('2026-09-20T01:00:00.000Z', 'ma20', 'crossed', 1185.3, '2026-09-29'),
      row('2026-09-20T02:00:00.000Z', 'ma60', 'warming', null, '2026-09-29', 60, 12),
      row('2026-09-20T03:00:00.000Z', 'revenue_yoy', 'undetermined', null, null),
      {
        kind: 'kill_criterion_due',
        item: {
          decision_id: '2026-09-20T04:00:00.000Z',
          market: 'sh',
          code: '600519',
          display: '600519.SH',
          action: 'buy' as const,
          criterion: { metric: 'close', operator: '<' as const, threshold: 1200, as_of: '2026-09-20' },
        },
        // ⭐ `null` — the server could not read any bars at all. A different fault from
        // `warming`, on a different side, and the page must not merge them.
        metric: null,
      },
    ],
    due: due(),
    market_status: {
      verdict: 'trading_day',
      basis: 'probe',
      last_trading_date: '2026-09-29',
      checked_at: STAMP,
    },
  }
}

/** Today with no due criteria, nothing due in either queue, undecidable market. */
export function todayEmpty(): Body {
  return {
    generated_at: STAMP,
    attention: [],
    due: due(),
    market_status: {
      verdict: 'unknown',
      basis: 'none',
      last_trading_date: null,
      checked_at: STAMP,
    },
  }
}

/** Two pool entries: one priced (stale), one the sources refuse. */
export function poolRows(): Body {
  return [
    {
      market: 'sh',
      code: '600519',
      asset_type: 'stock',
      name: '贵州茅台',
      reason: '毛利率连续三年高于 90%，品牌定价权强',
      since: '2026-09-20T01:00:00.000Z',
      last_event_id: 6,
    },
    {
      market: 'sz',
      code: '000002',
      asset_type: 'stock',
      name: null,
      reason: '物流网络的成本曲线，想验证护城河',
      since: '2026-09-21T01:00:00.000Z',
      last_event_id: 7,
    },
  ]
}

export function poolQuotes(): Body {
  return [
    { market: 'sh', code: '600519', display: '600519.SH', quote: { ...quoteResult(1237.0, -0.0114), stale: true } },
    { market: 'sz', code: '000002', display: '000002.SZ', quote: errorResult() },
  ]
}

export function instrumentDetail(): Body {
  return {
    market: 'sh',
    code: '600519',
    display: '600519.SH',
    asset_type: 'stock',
    name: '贵州茅台',
    follow: {
      status: 'followed',
      reason: '毛利率连续三年高于 90%，品牌定价权强',
      since: '2026-09-20T01:00:00.000Z',
      last_event_id: 6,
      event_count: 1,
    },
    history: [
      {
        event_id: 6,
        occurred_at: '2026-09-20T01:00:00.000Z',
        kind: 'added',
        reason: '毛利率连续三年高于 90%，品牌定价权强',
        supersedes_id: null,
      },
    ],
    decisions: [
      {
        id: '2026-09-20T01:00:00.000Z',
        market: 'sh',
        code: '600519',
        display: '600519.SH',
        action: 'buy',
        rationale: '毛利率连续三年高于 90%，品牌定价权强',
        counter_evidence: '白酒需求与宏观强相关，若高端消费收缩，定价权无法对冲量的下滑',
        kill_criteria: [{ metric: 'revenue_yoy', operator: '<', threshold: 0.55, as_of: '2026-12-31' }],
        thesis_id: null,
      },
    ],
    cards: [],
  }
}

export function recordedEvent(): Body {
  return {
    event_id: 99,
    occurred_at: STAMP,
    kind: 'added',
    market: 'sh',
    code: '600036',
    reason: '测试写入的理由',
    supersedes_id: null,
  }
}
