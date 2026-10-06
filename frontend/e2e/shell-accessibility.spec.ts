import { expect, test } from '@playwright/test'
import { instrumentDetail, poolQuotes, poolRows, quoteResult, routeApi } from './fixtures'

/**
 * The shell a keyboard and a screen reader actually meet.
 *
 * Three things, added 2026-10-06 and each one measured rather than assumed:
 *
 * 1. `<main>` — the document had `header`, `nav` and two labelled `section`s and
 *    no `main`, so "where am I" had no answer. E2E measures it because a landmark
 *    is exactly the kind of thing a refactor removes silently.
 * 2. A skip link — the shell persists, so without it every page begins with the
 *    brand link, the search box and eight sidebar rows before any content.
 * 3. Focus following the route — a route change replaced the content and left
 *    focus on the sidebar link that was just activated, so the next Tab walked the
 *    sidebar again.
 *
 * And the ErrorBoundary, which is the other half: a page that throws should cost
 * the reader that page and keep the navigation, not blank the window.
 */

test.beforeEach(async ({ page }) => {
  await routeApi(page, {
    'GET /api/v1/instruments/sh/600519': instrumentDetail(),
    'GET /api/v1/instruments/sh/600519/quote': quoteResult(1237.0, -0.0114),
    'GET /api/v1/instruments/sh/600519/daily': { bars: [], indicators: {} },
    'GET /api/v1/today': {
      attention: [],
      due: { cards: { queue: 'cards', count: 0 }, reviews: { queue: 'reviews', count: 0 } },
    },
    // The pool is the route this spec navigates to after the failure, and it is
    // stubbed fully because a half-stubbed destination throws too -- which is the
    // boundary working correctly and the test being wrong about why.
    'GET /api/v1/watchlist': poolRows(),
    'GET /api/v1/watchlist/quotes': poolQuotes(),
  })
})

test.describe('外壳的可访问性（2026-10-06）', () => {
  test('the document has one main, and it holds the content not the navigation', async ({
    page,
  }) => {
    await page.goto('/#/i/sh/600519')

    const main = page.getByRole('main')
    await expect(main).toHaveCount(1)

    // The navigation is chrome that persists across every route, so putting it
    // inside `main` would answer "where am I" wrongly.
    await expect(main.locator('nav')).toHaveCount(0)
    await expect(main.locator('header')).toHaveCount(0)
    // ...and the page's own heading is inside it.
    await expect(main.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('the skip link is the first thing a keyboard reaches, and it moves focus', async ({
    page,
  }) => {
    await page.goto('/#/i/sh/600519')

    // `sr-only` rather than `hidden`: `display: none` takes the element out of the
    // tab order, so a "hidden" skip link is a skip link that cannot be skipped to.
    const skip = page.getByTestId('skip-to-main')
    await expect(skip).toHaveCount(1)

    await page.keyboard.press('Tab')
    await expect(skip).toBeFocused()

    // It points at the landmark, which is why the landmark carries an id.
    await skip.press('Enter')
    await expect(page).toHaveURL(/#main$/)
    await expect(page.getByRole('main')).toBeFocused()
  })

  test('a route change puts focus in the content, not back on the navigation', async ({
    page,
  }) => {
    await page.goto('/#/i/sh/600519')

    // Deliberately **not** asserted on arrival: focus belongs at the top of the
    // document there, so that the next Tab reaches the skip link. The previous
    // version of this test asserted it and was wrong — it encoded the bug the
    // skip-link test caught.
    await page.getByTestId('nav-关注池').click()
    await expect(page.getByRole('main')).toBeFocused()

    // The specific wrongness this fixes: focus left on the sidebar link that was
    // just activated, so the reader's next Tab re-walked the navigation instead of
    // entering the page they asked for.
    const onNavLink = await page.evaluate(() => {
      const active = document.activeElement
      return active?.closest('nav') !== null
    })
    expect(onNavLink).toBe(false)
  })
})

test.describe('渲染失败（ErrorBoundary）', () => {
  test('a page that throws costs the reader that page and keeps the navigation', async ({
    page,
  }) => {
    /**
     * The failure is provoked by a **response that breaks its own shape** — `follow`
     * is null, and the page reads `detail.follow.status`. That is not a contrived
     * crash: it is exactly the shape drift `S-18` exists to catch, and a client
     * meeting one should degrade rather than vanish.
     */
    await routeApi(page, {
      'GET /api/v1/instruments/sh/600519': {
        market: 'sh',
        code: '600519',
        display: '600519.SH',
        asset_type: 'stock',
        name: '形状不对的标的',
        follow: null,
        history: [],
        decisions: [],
        cards: [],
      },
    })

    await page.goto('/#/i/sh/600519')

    const failure = page.getByTestId('render-failure')
    await expect(failure).toBeVisible()

    // The two sentences that carry the meaning: this program's fault, and the
    // record is not involved. A reader who cannot tell those two apart has been
    // told their investment history is at someone else's mercy.
    await expect(failure).toContainText('这个程序自己的问题')
    await expect(failure).toContainText('你的记录没有受影响')

    // 红线 8: a failure in this program names no provider, no upstream, no health.
    const text = (await failure.innerText()) ?? ''
    for (const forbidden of ['行情源', '数据源', '超时', '冷却', 'provider', '上游']) {
      expect(text).not.toContain(forbidden)
    }

    // The shell survives, which is the whole design: the navigation is the only
    // way out of a broken page, so wrapping the shell would have defeated it.
    await expect(page.getByTestId('app-shell')).toBeVisible()
    await expect(page.getByTestId('nav')).toBeVisible()
    await expect(page.getByTestId('render-failure-reload')).toBeVisible()

    // And the way out works from the failure screen: the boundary is keyed on the
    // route, so a page that failed does not follow the reader to the next one.
    await page.getByTestId('nav-关注池').click()
    await expect(failure).toHaveCount(0)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })
})
