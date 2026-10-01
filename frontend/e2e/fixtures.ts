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

/**
 * ⭐ **Mark today's launch screen as already seen, before the app boots.**
 *
 * This exists because of what the launch screen did to the suite, and both halves
 * of that are worth stating because the fix looks like a test convenience and is
 * not.
 *
 * The screen is shown on `#/` when the reader has not seen it today — and
 * `#/` is what most of these specs navigate to, because it means 「the app, at its
 * home view」. So 27 tests in `nav.spec.ts` and `palette.spec.ts` failed on
 * 「the shell is not on screen」, and the one-line cause was a product feature
 * doing exactly what it was built to do.
 *
 * The alternative was to change the product, and both available changes were
 * wrong:
 *
 * - **Never show it on `#/`.** Then it never shows at all, since `#/` is the only
 *   address that means 「I have no destination in mind」.
 * - **Show it only on an empty hash.** `#`, `#/` and `''` all mean today
 *   (`parseHash` normalises them onto one table entry), so this would have picked
 *   a spelling rather than a meaning, and `vite preview` plus most links spell it
 *   `#/`.
 *
 * So the specs that are about the **shell** say they are past the launch screen,
 * and the specs that are about the **launch screen** (`launch.spec.ts`) remove the
 * key again and are the only place it appears. The key is the same string the app
 * writes (`launchLogic.ts`'s `LAUNCH_SEEN_KEY`), quoted here rather than imported
 * because `e2e/` must not depend on `src/` internals — the app under test is the
 * built bundle, and a test that imports the source is testing two different things
 * at once.
 *
 * ⚠️ `addInitScript`, not `page.evaluate`. The app reads the key while React is
 * mounting, so setting it after `goto` races the first render.
 */
export const LAUNCH_SEEN_KEY = 'alphacouncil.launch.seen'

/**
 * ⭐ **Put the page in a state where today's launch screen is behind the reader.**
 *
 * `init` runs once and leaves the key set, so it is safe to call more than once
 * and safe to call before *or* after `routeApi`. ⭐ **It does not survive a
 * `reload()`**, because `addInitScript` is registered on the page and the key it
 * writes persists — so a spec that reloads keeps the acknowledged state, which is
 * what the launch-screen specs rely on when they assert 「it does not come back」。
 */
export async function acknowledgeLaunch(page: Page): Promise<void> {
  await page.addInitScript((key) => {
    const now = new Date()
    const month = String(now.getMonth() + 1).padStart(2, '0')
    const day = String(now.getDate()).padStart(2, '0')
    window.localStorage.setItem(key, `${now.getFullYear()}-${month}-${day}`)
  }, LAUNCH_SEEN_KEY)
}

/**
 * ⭐ **The opt-out, for the spec that is about the launch screen itself.**
 *
 * Written as a removal rather than as a flag, because the app has no such flag and
 * inventing one in the fixtures to serve a test would be inventing behaviour the
 * product does not have.
 *
 * ⭐ **It is one-shot, and that is the second thing this got wrong.**
 * `addInitScript` runs on *every* navigation, and the first version of
 * `launch.spec.ts` cleared the key unconditionally — so 「records the dismissal, so
 * it does not come back on the next launch」 re-cleared it on its own `reload()` and
 * failed for a reason that had nothing to do with the product.
 *
 * The sentinel lives in `sessionStorage`, which is **per-tab and survives reloads**,
 * and is the reason the clear happens on the first navigation and not the second.
 */
export async function clearLaunchAcknowledgement(page: Page): Promise<void> {
  await page.addInitScript(
    (args: { key: string; sentinel: string }) => {
      if (window.sessionStorage.getItem(args.sentinel) === 'done') return
      window.sessionStorage.setItem(args.sentinel, 'done')
      window.localStorage.removeItem(args.key)
    },
    { key: LAUNCH_SEEN_KEY, sentinel: 'e2e.launch.pending' },
  )
}

type Body = Record<string, unknown>

/**
 * Intercept every `/api/v1/**` call and answer from `handlers`, keyed by
 * request path (query strings ignored) — a bare path matches any method, or
 * key it as `GET /api/v1/today` to pin the verb. Unmatched paths 404 loudly.
 *
 * ⭐ **This also acknowledges the launch screen, and that is the whole point of
 * putting it here rather than in the twelve specs that needed it.**
 *
 * The launch screen (ADR-0033) appears on `#/` for a reader who has not seen it
 * today, and `#/` is what most of these specs navigate to, because it means 「the
 * app, at its home view」. Twenty-seven tests in `nav.spec.ts` and
 * `palette.spec.ts`, plus eleven in `today-hub.spec.ts`, plus `today.spec.ts` and
 * one in `routing.spec.ts`, failed on 「the shell is not on screen」 — and every
 * one of them was failing correctly, because a full-screen painting really was in
 * the way of a test about the shell behind it.
 *
 * Three ways to fix it were available and two of them were wrong:
 *
 * - **Edit twelve spec files** to clear the key. That makes the suite green and
 *   leaves the product as it is, which is fine — but it is twelve edits that must
 *   be repeated by the next person who writes a spec, and the next person will
 *   not know to make them. The failure would return the first time somebody added
 *   a `test.beforeEach`.
 * - **Stop showing the screen on `#/`.** Then it never shows, since `#/` is the
 *   only address meaning 「no destination in mind」 — the other two spellings are
 *   the same route.
 * - **Acknowledge it centrally**, at the one place every spec already goes to
 *   arrange its world. One edit, and a spec that forgets gets a clear failure
 *   rather than a mysterious one.
 *
 * ⭐ **`launch.spec.ts` does not use `routeApi` for this**, and has to opt back
 * out. It calls `routeApi` too, so it calls `clearLaunchAcknowledgement(page)`
 * immediately after — and that is written down rather than left as a convention,
 * because the alternative is a launch-screen spec that silently never sees the
 * launch screen.
 *
 * ⚠️ `addInitScript` and not `page.evaluate`: the app reads the key while React
 * is mounting, so setting it after `goto` races the first render. It is registered
 * **before** any navigation, so it holds for `reload()` too.
 */
export async function routeApi(
  page: Page,
  handlers: Record<string, Body | number>,
): Promise<void> {
  await acknowledgeLaunch(page)
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
        // ⭐ Added in spec 044: the server ships the sentence, byte-for-byte the one
        // `domain/criterion_sentence.py` renders for `undetermined`. ⭐ These three
        // fields live on the **attention item**, not on `metric`, because `metric`
        // is `null` in another fixture and the reader still needs a sentence then.
        verdict:
          '观察期已到 —— 「revenue_yoy」不在我们能算的指标里，这条判据没有被求值过。',
        adjudicable: false,
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
  // ⭐ The sentence is **not** written here. It is written in
  // `backend/src/alphacouncil/domain/criterion_sentence.py` and shipped by `/today`
  // (spec 044), so these fixtures use the exact strings that server produces. ⭐ They are
  // literals rather than a re-implementation on purpose: ⭐ a TypeScript copy here would
  // be the second home the move existed to remove, and it would agree with itself.
  const row = (
    id: string,
    metric: string,
    state: string,
    value: number | null,
    as_of: string | null,
    period: number | null,
    bars: number | null,
    verdict: string,
    adjudicable: boolean,
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
    verdict,
    adjudicable,
  })
  return {
    generated_at: STAMP,
    attention: [
      row(
        '2026-09-20T01:00:00.000Z',
        'ma20',
        'crossed',
        1185.3,
        '2026-09-29',
        null,
        null,
        // ⭐ `1185.30`, not `1,185.30`. ⭐ `formatValue` in `criterion_sentence.py` only
        // adds the thousands separator when the value **is an integer** (「整数就按整数
        // 打印」); ⭐ a fractional reading prints as it is. The first draft of this
        // fixture put the separator in, ⭐ and the E2E then failed on a *rendering*
        // difference that had moved the sentence into the server — ⭐ which is exactly
        // the drift this move was supposed to make impossible.
        '已越过 —— ma20 现在 1185.30（2026-09-29）。',
        true,
      ),
      row(
        '2026-09-20T02:00:00.000Z',
        'ma60',
        'warming',
        null,
        '2026-09-29',
        60,
        12,
        '观察期已到 —— ma60 还差 48 根日线才有值，这条判据暂时没有被求值。',
        false,
      ),
      row(
        '2026-09-20T03:00:00.000Z',
        'revenue_yoy',
        'undetermined',
        null,
        null,
        null,
        null,
        '观察期已到 —— 「revenue_yoy」不在我们能算的指标里，这条判据没有被求值过。',
        false,
      ),
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
        // ⭐ The sentence is still there, and that is the point of putting it on the
        // attention item rather than on the metric (spec 044).
        verdict: '观察期已到 —— 这个代码没有日线，这条判据没有被求值过。',
        adjudicable: false,
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
