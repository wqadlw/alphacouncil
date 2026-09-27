import { expect, test } from '@playwright/test'
import { instrumentDetail, quoteResult, routeApi } from './fixtures'

test.beforeEach(async ({ page }) => {
  await routeApi(page, {
    'GET /api/v1/instruments/sh/600519': instrumentDetail(),
    'GET /api/v1/instruments/sh/600519/quote': quoteResult(1237.0, -0.0114),
    'POST /api/v1/decisions': { detail: 'e2e does not record decisions' },
    'GET /api/v1/decisions': [],
  })
})

test.describe('标的页（I1）与红线 12/13', () => {
  test('the page shows what the reader wrote, in write order', async ({ page }) => {
    await page.goto('/#/i/sh/600519')

    await expect(page.getByText('600519.SH').first()).toBeVisible()
    await expect(page.getByRole('heading', { name: '我对它做过什么' })).toBeVisible()
    // The reader's own words — the reason the follow exists — on the page.
    await expect(page.getByText('毛利率连续三年高于 90%，品牌定价权强').first()).toBeVisible()
  })

  test('the stop-loss panel must state the years needed to recover（红线 12）', async ({
    page,
  }) => {
    await page.goto('/#/i/sh/600519')

    // The panel only opens on demand — prices never animate themselves into
    // a nudge (red line 11).
    await page.getByRole('button', { name: /我正在亏着/ }).click()
    await page.getByPlaceholder('32').fill('32')
    await page.getByPlaceholder('15').fill('15')

    // The sentence the constitution names verbatim, with a number beside it.
    await expect(page.getByText(/恢复所需年数：约/)).toBeVisible()
    await expect(page.getByText(/才能回到成本 —— 亏损是不对称的/)).toBeVisible()

    // And its one-line contract: no advice lives here.
    await expect(page.getByText(/这里没有「要不要卖」/)).toBeVisible()
  })

  test('the decision form refuses to submit until its required fields exist（红线 13）', async ({
    page,
  }) => {
    await page.goto('/#/i/sh/600519')

    const submit = page.locator('button[type="submit"]', { hasText: '记下来' })
    await expect(submit).toBeDisabled()
    await expect(page.getByText(/还差：/)).toBeVisible()
  })

  test('the knowledge layer renders on the page (K1)', async ({ page }) => {
    await page.goto('/#/i/sh/600519')

    // The fifth question the page answers, mounted between price and decisions.
    await expect(page.getByRole('heading', { name: '我对它说过什么' })).toBeVisible()
    // With no cards recorded the empty state says so plainly — no fake loading.
    await expect(page.getByText(/还没有为它写过卡片/)).toBeVisible()
  })

  test('a card converges with a reason and retires from the current claims (K2)', async ({
    page,
  }) => {
    // Override the shared fixture: one active card, and a converge response
    // that returns it converged with its appended event. Routes registered last
    // match first, so these win over the beforeEach mock.
    const activeCard = {
      id: 'card_1700000000000',
      content: '渠道库存是白酒先行指标',
      claim_type: 'supporting',
      source_url: 'https://example.com/report',
      source_title: '渠道调研报告',
      captured_at: '2026-09-20T01:00:00.000Z',
      as_of: null,
      origin: 'user_written',
      priority: 4,
      status: 'active',
      created_at: '2026-09-20T01:00:00.000Z',
      symbols: [{ market: 'sh', code: '600519', display: '600519.SH' }],
      events: [],
    }
    const detail = instrumentDetail()
    let currentCards: Array<Record<string, unknown>> = [activeCard]
    await page.route('**/api/v1/instruments/sh/600519', (route) =>
      route.fulfill({ json: { ...detail, cards: currentCards } }),
    )

    const convergedCard = {
      ...activeCard,
      status: 'converged',
      events: [
        {
          id: 'event_1700000086400',
          card_id: activeCard.id,
          event_type: 'converged',
          reason: '公司改直营，渠道先行关系失效',
          created_at: '2026-09-21T01:00:00.000Z',
        },
      ],
    }
    await page.route('**/api/v1/cards/*/converge', (route) => {
      currentCards = [convergedCard]
      route.fulfill({ json: convergedCard })
    })

    await page.goto('/#/i/sh/600519')
    await expect(page.getByText('渠道库存是白酒先行指标')).toBeVisible()

    await page.getByRole('button', { name: '收敛这张卡' }).click()
    await page
      .getByLabel(/为什么它不再代表你当前的主张/)
      .fill('公司改直营，渠道先行关系失效')
    await page.getByRole('button', { name: '确认收敛' }).click()

    // The card retires to the dimmed converged section, reason intact.
    await expect(
      page.getByRole('heading', { name: '已收敛的主张' }),
    ).toBeVisible()
    await expect(
      page.getByText('已收敛：公司改直营，渠道先行关系失效'),
    ).toBeVisible()
  })
})
