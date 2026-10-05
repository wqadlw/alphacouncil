/**
 * ⭐⭐ **The demo banner, on every screen — including the one that bypasses the shell.**
 * (spec 057)
 *
 * ## What is being protected
 *
 * Measured 2026-10-05 on the reader's own database:
 *
 * ```
 *   instruments 2 · watchlist_events 8 · decisions 5
 *   cards 0 · notes 0 · reviews 0 · lessons 0
 * ```
 *
 * The knowledge layer is empty, ⭐ so the three queues that make this product different
 * from a P&L log opened empty every day — **not because they were broken, but because there
 * had never been anything to review.** `dev.py demo` fills that with a separate library.
 *
 * ⭐ **And a demo that looks exactly like the reader's own data is worse than no demo**,
 * because someone eventually reads its decisions as their own. The banner is one of three
 * layers against that (the subdirectory, the banner, and the server's refusal to seed the
 * real path); only the third fails loudly, ⭐ and this spec covers the second.
 *
 * ## ⭐ Why this file asserts on *every* route rather than one
 *
 * `App.tsx` renders `<StartupPage>` **instead of** `<AppShellFrame>` — see the comment at
 * that `if`. So a banner mounted inside the frame would be ⭐ **invisible on the very first
 * screen a new reader sees**, ⭐ which is the one moment it most has to be there. That is
 * why the banner sits above both branches, and it is why 「it shows on the today page」
 * would be a useless assertion: the today page is the one place the placement bug could
 * not have shown up.
 */

import { expect, test } from '@playwright/test'

import {
  acknowledgeLaunch,
  capabilities,
  clearLaunchAcknowledgement,
  instrumentDetail,
  poolQuotes,
  poolRows,
  quoteResult,
  routeApi,
  todayClosed,
} from './fixtures'

const banner = '这是演示库。你的记录不在这里。'

/** Every shell route, with the fixtures each one needs to render at all. */
const SHELL_ROUTES: { hash: string; name: string; handlers: Record<string, unknown> }[] = [
  { hash: '#/', name: 'today', handlers: { '/api/v1/today': todayClosed() } },
  {
    hash: '#/pool',
    name: 'pool',
    handlers: {
      '/api/v1/watchlist': poolRows(),
      '/api/v1/quotes': poolQuotes(),
    },
  },
  { hash: '#/vault', name: 'vault', handlers: {} },
  { hash: '#/review', name: 'review', handlers: {} },
  { hash: '#/retrospective', name: 'retrospective', handlers: {} },
  {
    hash: '#/instruments/sh/600519',
    name: 'instrument',
    handlers: {
      [`/api/v1/instruments/sh/600519`]: instrumentDetail(),
      '/api/v1/quote': quoteResult(1237.0, -0.0114),
    },
  },
]

test.describe('demo banner', () => {
  test('is absent on a real library', async ({ page }) => {
    await routeApi(page, {
      '/api/v1/capabilities': capabilities({ is_demo: false }),
      '/api/v1/today': todayClosed(),
    })
    await page.goto('/#/')

    await expect(page.getByTestId('demo-banner')).toHaveCount(0)
    // ⭐ Asserted positively too, so a spec that fails to boot cannot pass this by rendering
    // an empty page. `is_demo: false` must mean 「the shell, without the banner」 and not
    // 「nothing at all」 — those are indistinguishable if the only assertion is an absence.
    await expect(page.getByTestId('nav')).toBeVisible()
  })

  for (const route of SHELL_ROUTES) {
    test(`is on the ${route.name} page`, async ({ page }) => {
      await routeApi(page, {
        '/api/v1/capabilities': capabilities({ is_demo: true }),
        ...route.handlers,
      })
      await page.goto(`/${route.hash}`)

      await expect(page.getByTestId('demo-banner')).toBeVisible()
      await expect(page.getByTestId('demo-banner')).toHaveText(banner)
    })
  }

  test('⭐ is on the launch screen, which renders instead of the shell', async ({ page }) => {
    // ⭐ **The one that would have caught the placement bug.** `StartupPage` is not inside
    // `AppShellFrame`, so a banner mounted in the frame is on six of seven screens.
    await routeApi(page, {
      '/api/v1/capabilities': capabilities({ is_demo: true }),
      '/api/v1/today': todayClosed(),
    })
    await clearLaunchAcknowledgement(page)
    await page.goto('/#/')

    // ⭐ Both at once. Asserting the banner alone would pass on the shell too, ⭐ and
    // asserting the launch screen alone would pass if the banner had simply not rendered —
    // the pair is what says 「the banner is on *this* screen」.
    // ⭐ Located by testid rather than by the Chinese sentence: the headline's wording is
    // derived from the due counts (`todayClosed()` yields none, so it renders a fixed
    // string), ⭐ and a copy assertion would break the first time that sentence is edited.
    await expect(page.getByTestId('launch-headline')).toBeVisible()
    await expect(page.getByTestId('demo-banner')).toHaveText(banner)
  })

  test('⭐ carries no digits, no welcome, and no way in', async ({ page }) => {
    await routeApi(page, {
      '/api/v1/capabilities': capabilities({ is_demo: true }),
      '/api/v1/today': todayClosed(),
    })
    await page.goto('/#/')

    const text = (await page.getByTestId('demo-banner').innerText()).trim()

    // ⭐ Red line 11: 「不鼓励频繁操作」. A banner is the first thing on screen and the worst
    // possible place to introduce a number *about the reader* — 「5 张卡片」 is a score.
    expect(text).not.toMatch(/[0-9]/)
    // ⭐ Red line 13: the product does not reassure. 「欢迎」 is reassurance.
    expect(text).not.toMatch(/欢迎|试用|体验/)
    // ⭐ **No road from the demo into the reader's own library.** Red lines 3/13/15 and
    // `agent-guide.md`'s 「不替用户写决策记录」 exist to close exactly that road, ⭐ and a
    // demo that offered 「import into my library」 would reopen it with invented judgments.
    expect(text).not.toMatch(/导入|import/i)
  })

  test('a failed capability check renders nothing rather than a wrong answer', async ({
    page,
  }) => {
    // ⭐ The honest rendering of 「did not find out」. It is deliberately **not** an error
    // message: 「我无法确认这是不是演示库」 is not a sentence a reader should have to read,
    // ⭐ and the guarantee is the server refusing to seed the real path anyway.
    await routeApi(page, {
      '/api/v1/capabilities': 500,
      '/api/v1/today': todayClosed(),
    })
    await page.goto('/#/')

    await expect(page.getByTestId('demo-banner')).toHaveCount(0)
    // ⭐ And the app still works. A banner that cannot be checked must not take the shell
    // down with it — the reader's records do not depend on this request succeeding.
    await expect(page.getByTestId('app-shell')).toBeVisible()
    await expect(page.getByTestId('attention-row').first()).toBeVisible()
  })

  test('survives a reload without flickering into a second copy', async ({ page }) => {
    await routeApi(page, {
      '/api/v1/capabilities': capabilities({ is_demo: true }),
      '/api/v1/today': todayClosed(),
    })
    await acknowledgeLaunch(page)
    await page.goto('/#/')
    await expect(page.getByTestId('demo-banner')).toHaveCount(1)

    await page.reload()
    // ⭐ **Exactly one.** `DemoBanner` fetches in a `useEffect` and renders `null` until it
    // answers, ⭐ so a second banner would mean the effect ran twice per mount — the
    // infinite-render trap `useResource` already fell into once this session.
    await expect(page.getByTestId('demo-banner')).toHaveCount(1)
  })
})
