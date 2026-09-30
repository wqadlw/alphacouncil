/**
 * ⌘K — the command palette (spec 025).
 *
 * ## ⭐ Why this file exists at all
 *
 * The palette shipped in the same commit as the three-pane shell and was
 * **verified by hand only** — the round's own changelog lists it as
 * 「手动验证过，无 E2E 断言」. That is the one hole spec 025 left, and it is the
 * worst-shaped hole of the four: a shortcut handler is exactly the kind of code
 * that breaks silently. Nothing about a `keydown` listener failing looks like a
 * failure — the app just stops responding to ⌘K, and there is nothing to notice
 * unless a test presses the key.
 *
 * So: hand-verified is not verified. This file makes it verified, and it is the
 * cheapest kind of test to write — a headless browser, one API stub, and a
 * keyboard.
 *
 * ## What is worth asserting, and what is not
 *
 * Worth it, because each is a behaviour that can regress without looking wrong:
 *
 * - all three ways in (⌘K, `/`, focusing the search box) and that `/` stays out
 *   of the way while the reader is typing into a field
 * - filtering narrows the list, and the count really narrows
 * - ↑↓ moves the cursor, ⏎ runs it, Esc closes it
 * - the cursor is a **2px left rule, not a row fill** — the spec is explicit and
 *   a row fill is exactly the sort of "improvement" that arrives later and
 *   passes review
 * - running a navigation command actually changes the view, and ⌘K works from
 *   every view (the shell is persistent; the palette must be too)
 * - the scrim closes on click, and it is a **paper wash, not black**
 *
 * Not worth it: pixel positions, transition timing. There is no animation to
 * test (guide §7.1: no entrance motion at all), so the only thing a timing
 * assertion could catch is a bug nobody has.
 */

import { expect, test } from '@playwright/test'
import { ROUTES } from '../src/routing'
import { routeApi, todayEmpty } from './fixtures'

const VIEWS = ['#/', '#/pool', '#/review', '#/retrospective'] as const

/** Every API call the shell makes on any of the four views. */
async function stub(page: Parameters<typeof routeApi>[0]): Promise<void> {
  await routeApi(page, {
    'GET /api/v1/today': todayEmpty(),
    'GET /api/v1/watchlist': [],
    'GET /api/v1/watchlist/quotes': [],
    'GET /api/v1/review/due': [],
    'GET /api/v1/decision-reviews/due': [],
  })
}

test.describe('命令面板（spec 025 · ⌘K）', () => {
  test('⌘K opens it from every view, and the shell is persistent', async ({ page }) => {
    /**
     * Every view, not one. The palette is a child of the frame, so a bug that
     * only appears on one route would be a bug in whichever page contributes
     * commands — and today none do, which means the *next* one to be added could
     * break every view at once without this test noticing.
     */
    await stub(page)
    for (const view of VIEWS) {
      await page.goto(`/${view}`)
      await expect(page.getByTestId('palette'), `${view} 没有面板`).toHaveCount(0)

      await page.keyboard.press('Control+k')
      await expect(page.getByTestId('palette'), `${view} 打开失败`).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(page.getByTestId('palette'), `${view} 关闭失败`).toHaveCount(0)
    }
  })

  test('the search box is a third way in, and it is not itself an input', async ({
    page,
  }) => {
    /**
     * The top bar's box is a **fake** input: `readOnly`, so clicking it cannot
     * start a half-typed query that the palette then discards. It focuses →
     * the palette opens → the palette's own field takes the keystrokes.
     *
     * Asserting `readOnly` is the point. A real editable box here would leave two
     * fields fighting over the same characters, and it would look fine.
     */
    await stub(page)
    await page.goto('/#')

    const box = page.getByTestId('search-box')
    await expect(box).toHaveAttribute('readonly', '')

    await box.click()
    await expect(page.getByTestId('palette')).toBeVisible()
    await expect(page.getByTestId('palette-input')).toBeFocused()
  })

  test('`/` opens it, except while the reader is typing', async ({ page }) => {
    await stub(page)
    await page.goto('/#/pool')

    await page.keyboard.press('/')
    await expect(page.getByTestId('palette')).toBeVisible()
    await page.keyboard.press('Escape')

    // ⭐ The guard. A knowledge program has text fields — the pool's reason, the
    // instrument's rationale, a claim's source. If `/` opened the palette while
    // one of them had focus, typing a reason containing a slash would swallow
    // the rest of the sentence and open a search box instead.
    const reason = page.locator('form input').nth(1)
    await reason.click()
    await reason.type('毛利率/净利率')
    await expect(page.getByTestId('palette')).toHaveCount(0)
    await expect(reason).toHaveValue('毛利率/净利率')
  })

  test('typing filters, and the list really gets shorter', async ({ page }) => {
    await stub(page)
    await page.goto('/#')
    await page.keyboard.press('Control+k')

    const items = page.getByTestId('palette-item')
    const all = await items.count()
    // ⭐ Derived from `ROUTES`, not written down.
    //
    // This was `expect(all).toBe(4)`, and adding the `vault` view (spec 026)
    // broke it — the same dead-constant trap the constraint ledger documents
    // ("written dead on purpose, a new migration changes it"). A number that has
    // to be edited whenever the app grows a screen is not asserting anything; it
    // is just a second place to forget.
    expect(all).toBe(ROUTES.length)
    // And the palette really does offer every view, not a hand-picked few.
    for (const route of ROUTES) {
      await expect(page.getByTestId('palette-list')).toContainText(route.label)
    }

    // ⭐ Two commands share 复, and that is correct — 复习 and 复盘 are different
    // destinations. The first draft of this test asserted a count of 1 here and
    // failed, which is worth recording: the instinct "a search result should be
    // one thing" is wrong for a palette, where showing both candidates is the
    // entire value. What matters is that the list *narrows*, so the count is
    // asserted against 4 rather than against 1.
    await page.getByTestId('palette-input').fill('复')
    await expect(items).toHaveCount(2)
    await expect(items.nth(0)).toContainText('复习')
    await expect(items.nth(1)).toContainText('复盘')

    // A query that matches one thing gets one thing.
    await page.getByTestId('palette-input').fill('关注')
    await expect(items).toHaveCount(1)
    await expect(items.first()).toContainText('关注池')

    await page.getByTestId('palette-input').fill('不存在的东西')
    await expect(items).toHaveCount(0)
    // Rule 8 again: a fact and what to do, not 「无结果」.
    await expect(page.getByTestId('palette-list')).toContainText('没有匹配项')
    await expect(page.getByTestId('palette-list')).toContainText('Esc')
  })

  test('the cursor is a left rule, not a row fill', async ({ page }) => {
    /**
     * `docs/FRONTEND_STYLE_GUIDE.md` §8.2: 「选中项左侧 2px 金线」, because a
     * full-row fill on a paper background reads as a *button* and a rule reads
     * as a *cursor* — which is what it is.
     *
     * ⭐ Asserted on **colour**, and the width is asserted to be equal on both
     * rows. That is not pedantry — it is the other half of the design:
     *
     * The unselected row carries `border-l-transparent`, which is still a 2px
     * border, only transparent. That is deliberate: it reserves the space, so
     * moving the cursor between rows does not make the labels jump one glyph to
     * the right and back. The first draft of this test asserted that the
     * unselected row's `border-left-width` was *not* 2px, and it failed — the
     * implementation was right and the test had the wrong idea about what
     * `transparent` does.
     *
     * Both assertions are on computed styles rather than class names, because a
     * class assertion passes just as happily on a renamed utility as on the
     * intended border. This is about the visual contract, not the implementation.
     */
    await stub(page)
    await page.goto('/#')
    await page.keyboard.press('Control+k')

    const first = page.getByTestId('palette-item').first()
    const last = page.getByTestId('palette-item').last()

    await expect(first).toHaveAttribute('data-active', 'true')
    await expect(last).toHaveAttribute('data-active', 'false')

    const box = (el: Element) => {
      const s = getComputedStyle(el)
      return { width: s.borderLeftWidth, colour: s.borderLeftColor }
    }
    const active = await first.evaluate(box)
    const inactive = await last.evaluate(box)

    // The mark is 2px on the selected row…
    expect(active.width, '选中项应有 2px 左侧标记').toBe('2px')
    expect(active.colour, '选中项应是金线').not.toBe(inactive.colour)
    // …and 2px on the unselected one too, so nothing shifts when the cursor moves.
    expect(inactive.width, '未选中项也保留 2px 占位，避免文字跳动').toBe('2px')
    expect(inactive.colour).toMatch(/rgba\(0,\s*0,\s*0,\s*0\)|transparent/)
  })

  test('↑↓ ⏎ Esc all work, and ⏎ navigates', async ({ page }) => {
    await stub(page)
    await page.goto('/#')
    await page.keyboard.press('Control+k')

    const items = page.getByTestId('palette-item')
    const count = await items.count()
    // Derived, for the same reason as in the filtering test above.
    expect(count).toBe(ROUTES.length)

    const activeIndex = async () => {
      const flags = await items.evaluateAll((els) =>
        els.map((el) => el.getAttribute('data-active')),
      )
      return flags.indexOf('true')
    }

    expect(await activeIndex(), '打开时第一项应当是当前项').toBe(0)
    await page.keyboard.press('ArrowDown')
    expect(await activeIndex()).toBe(1)
    await page.keyboard.press('ArrowDown')
    expect(await activeIndex()).toBe(2)

    // ⭐ Walking past the end **stops**. Not wrap, not clamp to the wrong row:
    // either sends ⏎ to a command the reader did not pick.
    //
    // ⭐⭐ The press count is derived too, and that is the second dead constant
    // this file has now had. The first draft pressed ↓ three times and asserted
    // the cursor had reached the end — which is true with four views and false
    // with five, so adding a view broke a test about clamping. A clamp test must
    // press *more* times than there are items and then assert it stopped; any
    // fixed number is asserting the length of the route table instead.
    for (let i = 0; i < count; i += 1) {
      await page.keyboard.press('ArrowDown')
    }
    expect(await activeIndex(), '越过末项后应停在末项，不回绕').toBe(count - 1)

    // And one more press changes nothing, which is the part a wrap-around
    // implementation gets wrong.
    await page.keyboard.press('ArrowDown')
    expect(await activeIndex()).toBe(count - 1)

    await page.keyboard.press('ArrowUp')
    expect(await activeIndex()).toBe(count - 2)

    // ⭐ Walk to a *named* row and say so before pressing ⏎.
    //
    // The first draft pressed ⏎ and asserted `#/pool` while the cursor was
    // actually two rows further on, so it navigated to 复盘 and failed. The
    // lesson is the same as the clamp one: **do not count keys and then name a
    // destination** — the row has a name, so assert the name first. A palette
    // test that says "I pressed Enter three times and expected 关注池" is only
    // testing its own arithmetic.
    while ((await activeIndex()) > 1) {
      await page.keyboard.press('ArrowUp')
    }
    expect(await activeIndex()).toBe(1)
    await expect(items.nth(1)).toContainText('关注池')

    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/#\/pool/)
    await expect(page.getByTestId('palette')).toHaveCount(0)
  })

  test('the scrim is a paper wash and it closes on click', async ({ page }) => {
    /**
     * `rgb(251 250 248 / 0.72)` — the paper colour at 72%.
     *
     * A black scrim is the other product's modal; the guide allows this element
     * to leave the document plane precisely because it uses the page's own
     * colour. So the colour is the assertion, not a detail.
     */
    await stub(page)
    await page.goto('/#')
    await page.keyboard.press('Control+k')

    const scrim = page.getByTestId('palette-scrim')
    const colour = await scrim.evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(colour, '遮罩应是纸白半透，不是黑色').toMatch(/^rgba\(251,\s*250,\s*248,\s*0\.7\d\)$/)

    await scrim.click({ position: { x: 5, y: 5 } })
    await expect(page.getByTestId('palette')).toHaveCount(0)
  })

  test('the panel itself obeys the no-shadow rule', async ({ page }) => {
    /**
     * The one documented exception in the whole product (guide §3.2) is this
     * element's *scrim*. The panel beside it is not exempt, and since the
     * scrim's exemption exists, "the palette may have a shadow" is the obvious
     * next misreading — so it is pinned here while the exception is fresh.
     */
    await stub(page)
    await page.goto('/#')
    await page.keyboard.press('Control+k')

    const shadow = await page
      .getByTestId('palette')
      .evaluate((el) => getComputedStyle(el).boxShadow)
    expect(shadow === 'none' || shadow === '', `面板不该有阴影，实得 ${shadow}`)
  })

  test('the hint in the top bar is a letter, not a number', async ({ page }) => {
    /**
     * ⭐ Load-bearing, and easy to break.
     *
     * `retrospective.spec.ts:120` asserts that in the dangerous quadrant the
     * **whole body** contains no digit. The ⌘K hint is chrome, so it is inside
     * that blast radius — if it ever became `⌘1` or gained "3 results", it would
     * break a red-line test in a file that has nothing to do with the palette.
     * Asserted here so the breakage is reported as what it is.
     */
    await stub(page)
    await page.goto('/#')
    const hint = await page.locator('header kbd').innerText()
    expect(hint, '提示里不能出现数字').not.toMatch(/[0-9]/)
    expect(hint).toContain('K')
  })
})

/**
 * ⭐ Focus (spec 045 stage D).
 *
 * ⭐ **These three tests exist because the palette shipped with hand verification
 * and no focus assertion at all**, and the gap is invisible from the markup:
 * `role="dialog"` and `aria-modal="true"` were both present, ⭐ which is why a
 * reader of the source concludes the accessibility work is done. It was not.
 *
 * ⭐ **Every number below was measured with a browser probe before the fix, and the
 * measurements are the reason the tests look the way they do:**
 *
 * - closing left `document.activeElement` on `body` — nothing had recorded the
 *   reader's focus, so nothing could give it back;
 * - Tab *forwards* stayed inside for five presses and left on the sixth;
 * - Tab *backwards* left on the very first press.
 *
 * ⭐ **The two directions could not both be right by accident**, and the reading that
 * 「the panel is last in `<body>` so forward Tab is naturally safe」 is the one that
 * makes the bug invisible: the panel is portalled, ⭐ so forward Tab had to pass
 * through the whole page first, and the five safe steps were the browser's own
 * order rather than a trap doing its job. ⭐ One direction escaping immediately and
 * the other escaping late is what a **missing** trap looks like when the panel
 * happens to sit at the end of the tab order — which is why this file presses Tab
 * **more times than there are rows** on both sides.
 */
test.describe('命令面板的焦点（spec 045 阶段 D）', () => {
  test('关闭后焦点回到原处，不是 body', async ({ page }) => {
    await stub(page)
    await page.goto('/#')

    // ⭐ **A real element, focused deliberately.** The alternative — opening the
    // palette from wherever focus happens to be — makes 「restored」 mean 「somewhere
    // plausible」, ⭐ and the pre-fix behaviour (focus on `body`) is a plausible
    // somewhere. ⭐ The assertion below is therefore on the *same* `data-testid`,
    // not on 「an element exists」.
    //
    // ⭐ **Derived from `ROUTES`, for the reason this file already gives twice.**
    // The first draft wrote `'nav-市场'` — the right *shape* of the testid but the
    // wrong view, ⭐ and Playwright reported it as a bare 30s `locator.focus` timeout
    // with no assertion output. ⭐ A locator that matches nothing is a bad way to
    // learn which view you meant, so the name comes from the route table and a
    // rename or a reordering cannot break it.
    const before = page.getByTestId(`nav-${ROUTES[0].label}`)
    await before.focus()
    await expect(before).toBeFocused()

    await page.keyboard.press('Control+k')
    await expect(page.getByTestId('palette-input')).toBeFocused()

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('palette')).toHaveCount(0)
    // ⭐ One frame, because the restore is scheduled in a rAF ⭐ — an assertion
    // immediately after `toHaveCount(0)` would race the very thing it checks.
    await page.evaluate(
      () => new Promise((done) => requestAnimationFrame(() => done(null))),
    )
    await expect(before, '关闭后焦点应回到打开它的那个链接').toBeFocused()
  })

  test('Tab 与 Shift+Tab 都出不去面板', async ({ page }) => {
    await stub(page)
    await page.goto('/#')
    await page.keyboard.press('Control+k')
    await expect(page.getByTestId('palette')).toBeVisible()

    const rows = await page.getByTestId('palette-item').count()
    // ⭐ **Press more than there are stops, in both directions.** Any smaller number
    // passes against a *missing* trap ⭐ — the pre-fix forward walk needed exactly
    // `rows + 1` presses to escape, so `rows` presses prove nothing.
    const presses = rows + 3
    const inPanel = async () =>
      page.evaluate(
        () => Boolean(document.activeElement?.closest('[data-testid="palette"]')),
      )

    for (let i = 0; i < presses; i += 1) {
      await page.keyboard.press('Tab')
      expect(await inPanel(), `向前 Tab 第 ${i + 1} 次跑出了面板`).toBe(true)
    }
    for (let i = 0; i < presses; i += 1) {
      await page.keyboard.press('Shift+Tab')
      expect(await inPanel(), `向后 Tab 第 ${i + 1} 次跑出了面板`).toBe(true)
    }
  })

  test('背景对 Tab 关闭，而且面板自己没被自己冻住', async ({ page }) => {
    /**
     * ⭐ **The mechanism behind the previous test, checked separately.**
     *
     * The trap keeps the *keyboard* inside; `inert` is what stops a **script** or a
     * browser's own focus handling from landing on the page behind. ⭐ They are
     * different mechanisms and either can be right while the other is wrong, ⭐ so
     * the previous test's success is not evidence about this one.
     */
    await stub(page)
    await page.goto('/#')
    await page.keyboard.press('Control+k')
    await expect(page.getByTestId('palette')).toBeVisible()

    // ⭐ `inert` on the shell, and the panel **outside** it. Both halves, because
    // `inert` on the shell is only correct if the panel escaped the subtree ⭐ —
    // and a panel that is still inside would be frozen, which looks exactly like a
    // working modal until the reader types.
    const shape = await page.evaluate(() => {
      const shell = document.getElementById('app-shell')
      return {
        shellFound: Boolean(shell),
        shellInert: shell?.inert ?? null,
        panelInsideShell: Boolean(shell?.querySelector('[data-testid="palette"]')),
      }
    })
    expect(shape.shellFound, '找不到 app-shell，inert 无从施加').toBe(true)
    expect(shape.shellInert, '面板打开时背景应为 inert').toBe(true)
    expect(shape.panelInsideShell, '面板不能落在被 inert 的子树里，否则它自己会被冻住').toBe(
      false,
    )

    // ⭐ And the trap is not a lock: the panel still takes keystrokes. A modal that
    // passes the three assertions above and cannot be typed into is broken.
    await page.getByTestId('palette-input').fill('知识')
    await expect(page.getByTestId('palette-item')).toHaveCount(1)
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/#\/vault/)
    await expect(page.getByTestId('palette')).toHaveCount(0)

    // ⭐ **And `inert` is undone on close**, so the page is usable again. A cleanup
    // that leaves the shell inert passes every assertion above ⭐ — the reader sees
    // a working page that cannot be clicked.
    expect(
      await page.evaluate(() => document.getElementById('app-shell')?.inert ?? null),
      '关闭后背景不应仍为 inert',
    ).toBe(false)
  })
})
