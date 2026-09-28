/**
 * The today page's `due` line — the product coming to find the reader (spec 023).
 *
 * Red line 10 sat at `partial` for exactly one reason: `项目总纲` §2.1 says the
 * product must go and find the reader at the moments they will *not* come, and
 * nothing did. This line is that, so most of these tests are about what it must
 * **not** become.
 *
 * The line it must not cross: **a statement about something the reader already
 * committed to**, never **a suggestion about something they might want**. The
 * first is a fact and the only interruption red line 8 permits; the second is a
 * recommendation, which is what red line 8 exists to forbid. So:
 *
 * - ✅ "到期要看的：2 条决策 · 3 张卡片" — the reader is the subject
 * - ❌ "今天有 3 个机会" — the product is the subject
 *
 * Which is why these assert on **absence** so heavily. A hub that renders nothing
 * would pass a "is it tasteful?" check and fail every one of them.
 */

import { expect, test } from '@playwright/test'
import { due, routeApi, todayEmpty } from './fixtures'

/** Just enough for the page to render without other blocks failing first. */
function stub(page: Parameters<typeof routeApi>[0], body: Record<string, unknown>): Promise<void> {
  return routeApi(page, {
    'GET /api/v1/today': body,
    'GET /api/v1/watchlist': [],
    'GET /api/v1/watchlist/quotes': [],
  })
}

test.describe('今日页枢纽', () => {
  test('到期的东西被说成一句话，两个入口点得进去', async ({ page }) => {
    await stub(page, { ...todayEmpty(), due: due(3, 2) })
    await page.goto('/#/')

    const line = page.getByTestId('today-due')
    await expect(line).toBeVisible()
    await expect(line).toContainText('2 条决策')
    await expect(line).toContainText('3 张卡片')

    // Both are links, and both land on the right queue. The mapping comes from the
    // route table (`queueHref`), so this is also a check that the table is the
    // thing being used rather than a hard-coded path.
    await page.getByTestId('today-due-reviews').click()
    await expect(page).toHaveURL(/#\/retrospective/)
    await page.goBack()
    await page.getByTestId('today-due-cards').click()
    await expect(page).toHaveURL(/#\/review/)
  })

  test('⭐ 计数为零时整行不出现', async ({ page }) => {
    /**
     * The rule that is easiest to get wrong in the other direction.
     *
     * "0 条决策到期" is still a sentence *about the reader*, and being told you
     * owe yourself nothing is not worth a line of the default page. It also
     * teaches the reader to scan past this line, which is the opposite of what a
     * line that sometimes matters should do.
     */
    await stub(page, { ...todayEmpty(), due: due(0, 0) })
    await page.goto('/#/')
    await expect(page.getByTestId('today-due')).toHaveCount(0)
  })

  test('只有一类到期时只说那一类', async ({ page }) => {
    await stub(page, { ...todayEmpty(), due: due(0, 2) })
    await page.goto('/#/')
    await expect(page.getByTestId('today-due')).toContainText('2 条决策')
    await expect(page.getByTestId('today-due-cards')).toHaveCount(0)
  })

  test('⭐ 那一行的**字面**被钉死', async ({ page }) => {
    /**
     * ⭐ The strongest of these tests, and it exists because a mutation found the
     * weakness in the one below it: adding 「等你」 to the sentence — turning a
     * statement into a nudge — left the banned-word test **green**, because a list
     * of forbidden Chinese words can never be exhaustive. Nobody thinks of
     * "等你" when writing the list.
     *
     * So the sentence is compared **exactly**. It is product policy, in the same
     * way the dangerous quadrant's warning is (spec 020/021), so a change to it
     * should be a deliberate diff against a test that fails — not a wording tweak
     * that slips past a word list nobody can complete.
     */
    await stub(page, { ...todayEmpty(), due: due(3, 2) })
    await page.goto('/#/')
    // Whitespace-stripped, because the JSX builds the sentence from several text
    // nodes and `innerText` joins them without the spacing one would type by hand.
    // So the comparison is against the stripped form — the *wording* is still
    // pinned exactly, which is the part that matters.
    const text = (await page.getByTestId('today-due').innerText()).replace(/\s+/g, '')
    expect(text).toBe('到期要看的：2条决策·3张卡片')
  })

  test('⭐ 这一行不含任何红线 8 / 11 禁止的东西', async ({ page }) => {
    /**
     * Red line 8 bans anything that reads as a push or a pick; red line 11 bans
     * anything that counts the reader's activity. Both are easy to violate by
     * accident — "3 张卡片等你" adds a nudge, "已复习 2/7" adds a fraction — and
     * neither shows up as an error anywhere.
     *
     * A belt to the exact-match test's braces, and worth keeping for a different
     * reason: it names *why* each word is forbidden, so a reader can extend it
     * with judgement. The exact-match test is what actually holds.
     */
    await stub(page, { ...todayEmpty(), due: due(11, 7) })
    await page.goto('/#/')

    const text = (await page.getByTestId('today-due').innerText()).replace(/\s+/g, '')
    for (const word of [
      '机会', '精选', '异动', '值得关注', '推荐', '快看', '别错过',
      '连续', '打卡', '完成率', '进度', '待办', '逾期', '堆积', '很多',
      '！', '!', '★', '🔥',
    ]) {
      expect(text.includes(word), `枢纽那一行含「${word}」`).toBe(false)
    }
    // No fraction, no percentage — a count invites "out of how many?" and
    // answering that is red line 11's progress bar by another route.
    expect(text).not.toMatch(/[/／]/)
    expect(text).not.toMatch(/[%]/)
  })

  test('⭐ 十一件到期也只是十一，不是「很多」', async ({ page }) => {
    /**
     * The escalation trap.
     *
     * A counter's obvious next feature is a threshold — 10+, 50+, "a lot". That is
     * a nudge wearing a number's clothes, and `项目总纲` §2.1⑤ rules it out: the
     * whole sanctioned shape is 一句陈述, no 催促词. Eleven and one render through
     * exactly the same sentence.
     */
    await stub(page, { ...todayEmpty(), due: due(1, 1) })
    await page.goto('/#/')
    const one = await page.getByTestId('today-due').innerText()

    await stub(page, { ...todayEmpty(), due: due(400, 300) })
    await page.reload()
    const many = await page.getByTestId('today-due').innerText()

    // Same words, same punctuation — only the digits differ.
    const shape = (s: string) => s.replace(/[0-9]+/g, 'N')
    expect(shape(many)).toBe(shape(one))
  })

  test('这一行只有一个链接来源，没有徽章也没有红点', async ({ page }) => {
    await stub(page, { ...todayEmpty(), due: due(3, 2) })
    await page.goto('/#/')

    const line = page.getByTestId('today-due')
    // Exactly the two queue links, and nothing else clickable — no badge
    // sitting beside a count, which is red line 11's打卡计数 in its most common
    // disguise (and the thing the nav is already pinned for not doing).
    await expect(line.locator('a')).toHaveCount(2)
    expect(await line.innerHTML()).not.toMatch(/badge|dot|alert|red-|bg-navy/)
  })

  test('后端没给 due 就不渲染这一行，也不报错', async ({ page }) => {
    /**
     * The block is required server-side, but a client that renders a page from a
     * cached or older response must not crash on it. Missing is a state to render,
     * not an exception.
     */
    const body = todayEmpty() as Record<string, unknown>
    delete body.due
    await stub(page, body)
    await page.goto('/#/')
    await expect(page.getByTestId('today-due')).toHaveCount(0)
    // The rest of the page is unaffected.
    await expect(page.getByText('今天 ·')).toBeVisible()
  })

  test('今天页原有的失效条件块没有回归', async ({ page }) => {
    /** The block that was already here, and the reason this endpoint exists. */
    await routeApi(page, {
      'GET /api/v1/today': {
        ...todayEmpty(),
        attention: [
          {
            kind: 'kill_criterion_due',
            item: {
              decision_id: '2026-09-20T01:00:00.000Z',
              market: 'sh',
              code: '600519',
              display: '600519.SH',
              action: 'buy',
              criterion: {
                metric: 'revenue_yoy',
                operator: '<',
                threshold: 0.55,
                as_of: '2026-09-20',
              },
            },
          },
        ],
        due: due(1, 0),
      },
      'GET /api/v1/watchlist': [],
      'GET /api/v1/watchlist/quotes': [],
    })
    await page.goto('/#/')
    await expect(page.getByTestId('today-due')).toContainText('1 张卡片')
    await expect(page.getByText('revenue_yoy')).toBeVisible()
  })
})
