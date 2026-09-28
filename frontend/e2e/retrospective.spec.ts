/**
 * The retrospective queue (J3) — red line 10, on a screen.
 *
 * Red line 10 is "必须让用户面对不舒服的数据：不美化、不打折；「坏决策+好结果」时
 * **不显示盈利数字**". The mechanism is not the interesting part and is proved
 * elsewhere: `outcome` is a category, so no magnitude was ever stored (spec 020),
 * and the API response enumerates no figure field (`test_decision_reviews_api.py`).
 *
 * What only a browser can show is the part nobody can prove by inspecting a
 * response: **what the user is actually looking at when the verdict comes back.**
 * A page could satisfy every contract and still add "+18%" next to the warning,
 * because the number would have to come from somewhere — and "we don't have it in
 * the API" is a much weaker guarantee than "we checked the pixels".
 *
 * So the two tests that matter here are negative, and they are negative on
 * purpose:
 *
 * 1. **Before it is due, the outcome choice does not exist.** Not disabled, not
 *    greyed out — absent. A disabled control is still on screen and still
 *    clickable, and clicking it means scoring the outcome early, which *is*
 *    hindsight. (The database refuses it too; this is the second line.)
 *
 * 2. **In the dangerous quadrant the whole page contains no number.** Not "no
 *    profit number" — no digits at all, and none of the words that would smuggle
 *    one back in. That is deliberately stricter than the red line, because a
 *    percentage and a currency amount are the same violation wearing different
 *    clothes.
 */

import { expect, test } from '@playwright/test'
import { routeApi } from './fixtures'

const DECISION_ID = '2026-03-12T09:30:00.000Z'

const DECISION = {
  id: DECISION_ID,
  market: 'sh',
  code: '600519',
  display: '600519.SH',
  action: 'buy',
  rationale: '渠道库存处于低位，提价能力可持续',
  counter_evidence: '批价可能因春节压货而短期回落',
  kill_criteria: [
    { metric: 'revenue_yoy', operator: '<', threshold: 0, as_of: '2026-12-31' },
  ],
  thesis_id: null,
}

function state(overrides: Record<string, unknown> = {}) {
  return {
    decision_id: DECISION_ID,
    due_at: '2026-03-12T09:30:00+00:00',
    reviewed_at: null,
    is_due: true,
    reviews: 0,
    ...overrides,
  }
}

function review(overrides: Record<string, unknown> = {}) {
  return {
    decision_id: DECISION_ID,
    review_id: 'review_1790560000000',
    process_score: 2,
    outcome: 'good',
    process: 'bad',
    quadrant: 'dangerous',
    guidance:
      '这次结果好，但你当时写下的理由撑不住它。按当时的方式做，下一次同样的运气不一定在。',
    reviewed_at: '2026-06-12T09:30:00+00:00',
    ...overrides,
  }
}

test.describe('复盘队列', () => {
  test('到期前不渲染结果分选项（不是禁用，是不存在）', async ({ page }) => {
    await routeApi(page, {
      '/api/v1/decision-reviews/due': [state({ is_due: false })],
      [`GET /api/v1/decision-reviews/${DECISION_ID}`]: {
        state: state({ is_due: false }),
        decision: DECISION,
        latest: null,
      },
    })
    await page.goto('/#/retrospective')

    await expect(page.getByTestId('retro-decision')).toBeVisible()
    // The gate: no outcome control exists at all.
    await expect(page.getByTestId('retro-outcome')).toHaveCount(0)
    await expect(page.getByTestId('retro-outcome-good')).toHaveCount(0)
    await expect(page.getByTestId('retro-outcome-bad')).toHaveCount(0)
    await expect(page.getByTestId('retro-outcome-failed')).toHaveCount(0)
    await expect(page.getByTestId('retro-not-due')).toBeVisible()
  })

  test('坏决策+好结果：整页没有任何数字', async ({ page }) => {
    await routeApi(page, {
      '/api/v1/decision-reviews/due': [state()],
      [`GET /api/v1/decision-reviews/${DECISION_ID}`]: {
        state: state(),
        decision: DECISION,
        latest: null,
      },
      'POST /api/v1/decision-reviews': review(),
    })
    await page.goto('/#/retrospective')

    await page.getByTestId('retro-score-2').click()
    await page.getByTestId('retro-outcome-good').click()

    const verdict = page.getByTestId('retro-verdict')
    await expect(verdict).toBeVisible()
    // The cell we are actually in, asserted rather than assumed: if the
    // fixture stopped producing `dangerous`, the rest of this test would pass
    // for the wrong reason.
    await expect(verdict).toHaveAttribute('data-quadrant', 'dangerous')

    // ⭐ The whole body of the page, in the dangerous quadrant.
    const text = (await page.locator('body').innerText()).replace(/\s+/g, '')
    expect(text).not.toMatch(/[0-9]/)
    expect(text).not.toMatch(/%|％|元|收益率|盈利|赚|涨幅|收益/)
    // …and the warning itself is there, so the page is not simply empty.
    await expect(page.getByTestId('retro-guidance')).toContainText('运气')
  })

  test('到期后可以打结果分，且句子来自后端', async ({ page }) => {
    await routeApi(page, {
      '/api/v1/decision-reviews/due': [state()],
      [`GET /api/v1/decision-reviews/${DECISION_ID}`]: {
        state: state(),
        decision: DECISION,
        latest: null,
      },
      'POST /api/v1/decision-reviews': review({
        process_score: 5,
        process: 'good',
        quadrant: 'repeat',
        outcome: 'good',
        guidance: '这个过程值得重复：下次遇到同类情况，按同样的方式做。',
      }),
    })
    await page.goto('/#/retrospective')

    // A process score is always available; the outcome only after a score is
    // picked, so no half-review is left sitting in the UI looking unfinished.
    await expect(page.getByTestId('retro-pick-first')).toBeVisible()
    await page.getByTestId('retro-score-5').click()
    await expect(page.getByTestId('retro-outcome')).toBeVisible()
    await page.getByTestId('retro-outcome-good').click()

    await expect(page.getByTestId('retro-verdict')).toHaveAttribute(
      'data-quadrant',
      'repeat',
    )
    await expect(page.getByTestId('retro-guidance')).toContainText('值得重复')
  })

  test('显示的是当初写下的原话，不是复述', async ({ page }) => {
    await routeApi(page, {
      '/api/v1/decision-reviews/due': [state({ is_due: false })],
      [`GET /api/v1/decision-reviews/${DECISION_ID}`]: {
        state: state({ is_due: false }),
        decision: DECISION,
        latest: null,
      },
    })
    await page.goto('/#/retrospective')

    // The anti-hindsight anchor: the graded text is on the page, and it is the
    // append-only original. If this ever renders a paraphrase, the mechanism is
    // gone and the review is being taken from memory.
    await expect(page.getByTestId('retro-rationale')).toHaveText(DECISION.rationale)
    await expect(page.getByTestId('retro-counter')).toContainText(DECISION.counter_evidence)
    await expect(page.getByTestId('retro-kill')).toContainText('revenue_yoy')
  })

  test('没有承诺复盘的决策不会出现在队列里', async ({ page }) => {
    await routeApi(page, { '/api/v1/decision-reviews/due': [] })
    await page.goto('/#/retrospective')

    // `empty-state` rather than a page-specific id: the empty state is now a
    // shared component (`ui.tsx`), and the point of a shared component is that
    // every page's reads the same way — so the test names the shared one.
    await expect(page.getByTestId('empty-state')).toBeVisible()
    // And the empty state must not be a progress nag — red line 11.
    const text = await page.locator('body').innerText()
    expect(text).not.toMatch(/连续|打卡|完成率|%/)
  })
})
