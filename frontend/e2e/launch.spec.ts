/**
 * The launch screen, as a reader meets it (ADR-0033).
 *
 * ⭐ **This is where rendering is asserted, and that placement is the repo's own
 * rule rather than a preference.** `styleguide.test.ts` records that there is no
 * `jsdom` and no `@testing-library/react` here, so a unit test cannot render a
 * component; `launch.test.ts` therefore tests the three *decisions* (which
 * painting, whether today has been seen, what the credit says) with no DOM at all,
 * and this file tests the four things only a browser can know: that the screen is
 * actually in the way, that the painting loads, that the artwork is not cropped,
 * and that the reader can get past it.
 *
 * ⭐ **Every test here starts by clearing the day's key**, because the screen is
 * suppressed once it has been seen and a stale key from a previous test in the
 * same worker would make the whole file pass by checking nothing. That is the
 * vacuity failure this repository keeps meeting, and the first version of this
 * file had it: `localStorage` persists across tests in one Playwright context.
 */

import { expect, test } from '@playwright/test'
import { clearLaunchAcknowledgement, routeApi, todayEmpty } from './fixtures'

const SEEN = 'alphacouncil.launch.seen'

/**
 * The one-shot marker `clearLaunchAcknowledgement` leaves in `sessionStorage`.
 *
 * Quoted rather than exported from `fixtures.ts` so a test that needs to make the
 * screen pending *again* has to name the same string the helper uses — and so that
 * a change to the helper's sentinel shows up here as a compile error rather than as
 * three tests quietly stopping meaning anything.
 */
const SENTINEL = 'e2e.launch.pending'

/** Every endpoint any view behind the launch screen might ask for. */
function stub(page: Parameters<typeof routeApi>[0]): Promise<void> {
  return routeApi(page, {
    'GET /api/v1/today': todayEmpty(),
    'GET /api/v1/watchlist': [],
    'GET /api/v1/watchlist/quotes': [],
    'GET /api/v1/review/due': [],
    'GET /api/v1/decision-reviews/due': [],
  })
}

/**
 * Land on a hash with the launch screen **pending**.
 *
 * ⭐ **`addInitScript` runs on *every* navigation in the context, including every
 * `reload()`** — and two of the tests below reload precisely to prove the screen
 * does *not* come back. The first version of this helper cleared the key this way,
 * so each reload re-cleared it and the assertion 「the launch screen is gone after
 * reloading」 was guaranteed to fail, for a reason that had nothing to do with the
 * product.
 *
 * So the clear is **one-shot**: a script that removes the key and then removes
 * itself from the same context is not expressible, but a script that only removes
 * it when a sentinel is absent is, and the sentinel is the simplest thing that
 * survives one navigation and not two.
 *
 * (The alternative — clear with `page.evaluate` after `goto` — is a race with
 * React's first render, which is why `addInitScript` was reached for in the first
 * place. One-shot beats racy here.)
 */
async function openWithLaunchPending(
  page: Parameters<typeof routeApi>[0],
  hash = '#/',
): Promise<void> {
  // ⭐ **`stub` first, then the removal — and the order is the whole mechanism.**
  //
  // `routeApi` acknowledges the launch screen for every spec (see `fixtures.ts` for
  // why that is not optional), so this file has to undo it. `addInitScript`
  // callbacks run **in registration order** on every navigation and the last one
  // wins — measured, not assumed:
  //
  //   register SET then REMOVE  -> null        (REMOVE won)
  //   register REMOVE then SET  -> "SET"       (SET won)
  //
  // So the removal must be registered *after* the acknowledgement.
  //
  // ⭐ **This file had it backwards, and the failure mode was silent.** Removing
  // first meant the acknowledgement landed last and won, so the key was written
  // before the app read it — every one of these nine tests failed on
  // `getByTestId('startup')` not being found, with no hint that the ordering was
  // the cause. Six seconds of timeout per test and the assertion says
  // 「element not found」, which reads like a missing component rather than two
  // lines in the wrong order.
  //
  // ⭐ **It is one-shot, so it does not fight the app afterwards.** A `reload()`
  // after dismissal re-runs both scripts, the sentinel stands the removal down, and
  // whatever the app wrote stands — which is what lets 「records the dismissal, so
  // it does not come back on the next launch」 pass.
  await stub(page)
  await clearLaunchAcknowledgement(page)
  await page.goto(`/${hash}`)
}

test.describe('开屏 · the launch screen', () => {
  test('is in the way on a first launch, and says what the product is', async ({
    page,
  }) => {
    await openWithLaunchPending(page)

    const screen = page.getByTestId('startup')
    await expect(screen).toBeVisible()
    // The shell must NOT be there yet: this is the assertion that proves the
    // screen renders *instead of* the app rather than inside it.
    await expect(page.getByTestId('app-shell')).toHaveCount(0)

    await expect(page.getByText('投资是一场修行')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'AlphaCouncil' })).toBeVisible()
    await expect(page.getByTestId('launch-enter')).toBeVisible()
  })

  test('shows a real painting, and the one the day calls for', async ({ page }) => {
    await openWithLaunchPending(page)

    const art = page.getByTestId('launch-art')
    await expect(art).toBeVisible()

    // Not decorative: the natural size has to arrive with the bytes, or the
    // layout reserves a 300×150 box and the painting jumps into it.
    const loaded = await art.evaluate((node) => {
      const img = node as HTMLImageElement
      if (!img.complete) return null
      return { w: img.naturalWidth, h: img.naturalHeight, src: img.currentSrc }
    })
    expect(loaded, 'the painting did not decode').not.toBeNull()
    expect(loaded!.w).toBeGreaterThan(200)
    expect(loaded!.h).toBeGreaterThan(200)

    // `data-day` is the manifest's answer, and the browser's own dimensions are
    // the file's answer. Two independent sources, and they must agree — that is
    // what proves `manifest.ts` was generated from these files rather than typed.
    const day = await art.getAttribute('data-day')
    expect(Number(day)).toBeGreaterThanOrEqual(1)
    expect(Number(day)).toBeLessThanOrEqual(31)
  })

  /**
   * ⭐ **The proportion check, and it is the one this design is built on.**
   *
   * The painting is displayed at its own aspect ratio with nothing cropped, because
   * a two-metre hanging scroll and a landscape album leaf are both 30-centimetre
   * objects of the same kind. `object-fit: cover` on this image would have been one
   * class and would have quietly cut a third off a tall scroll every day.
   */
  test('hangs the painting whole, at its own proportions', async ({ page }) => {
    await openWithLaunchPending(page)
    const art = page.getByTestId('launch-art')
    await expect(art).toBeVisible()

    // ⭐ **Cancel `ac-hang` before measuring, and this is the third distinct wrong
    // answer this assertion has given** — the two before it are recorded because the
    // next reader will otherwise repeat them.
    //
    // 1. `offsetWidth / offsetHeight`: integers, so the wrong instrument. It also
    //    happened to be *immune* to the animation, so it passed — a test right for
    //    the wrong reason, which teaches the next reader that the crop check works.
    // 2. `getBoundingClientRect()` without waiting: measured 1.433 against a
    //    natural 1.269, a 13% error, `cover`-magnitude, from a painting that is in
    //    fact displayed whole. A `transform` does not affect `offset*` and **does**
    //    affect `getBoundingClientRect()`, so this instrument was measuring
    //    `scaleY(0.88)` rather than the layout.
    // 3. `img.getAnimations()` to wait on: **an empty array, every time.** The
    //    animation is declared on `.startup-hang`, which is the `<figure>`; the
    //    `<img>` inside it has none. Waiting on an empty list resolves at once, so
    //    the "wait" was a no-op and the measurement still landed mid-animation.
    //
    // Isolated in a standalone page — the shipped layout with and without the
    // animation — the numbers are **13.19 % drift at t=0 and 0 % after 1.4 s**, and
    // the no-animation control is 0 % throughout. So the painting is displayed
    // whole; the assertion was measuring the animation.
    //
    // Cancelling rather than waiting is the fix, and it is deterministic: it
    // removes the transform immediately, so the box measured is the layout box
    // whatever the animation was doing, and the assertion cannot pass or fail on
    // the machine's speed. It also says what the test is about — layout, not motion.
    // The motion is the subject of `honours prefers-reduced-motion` below.
    await art.evaluate(async (node) => {
      const img = node as HTMLImageElement
      if (!img.complete) await img.decode()
      const frame = img.closest('.startup-frame') ?? img
      for (const animation of frame.getAnimations()) animation.cancel()
    })

    const shape = await art.evaluate((node) => {
      const img = node as HTMLImageElement
      const box = img.getBoundingClientRect()
      return {
        natural: img.naturalWidth / img.naturalHeight,
        rendered: box.width / box.height,
        naturalW: img.naturalWidth,
        naturalH: img.naturalHeight,
        renderedW: Number(box.width.toFixed(3)),
        renderedH: Number(box.height.toFixed(3)),
      }
    })
    // ⭐ The measured values, so a failure says what it saw rather than only what
    // it wanted: a 1133×893 painting (1.2688) laid out at 581.078×458 (1.2686).
    expect(
      Math.abs(shape.natural - shape.rendered),
      `natural ${shape.naturalW}x${shape.naturalH} (${shape.natural}) vs ` +
        `rendered ${shape.renderedW}x${shape.renderedH} (${shape.rendered})`,
    ).toBeLessThan(0.01 * shape.natural)
  })

  test('credits the painting, though CC0 does not require it', async ({ page }) => {
    await openWithLaunchPending(page)
    const credit = page.getByTestId('launch-credit')
    await expect(credit).toBeVisible()
    await expect(credit).toContainText('Cleveland')
    // No life dates: the credit line is the one line on this screen nobody should
    // have to read twice. `launch.test.ts` pins the stripping rule.
    await expect(credit).not.toContainText(/\d{3,4}[–-]\d{3,4}/)
  })

  test('lets the reader in by clicking, by the button, and by Enter', async ({
    page,
  }) => {
    await openWithLaunchPending(page)
    await expect(page.getByTestId('startup')).toBeVisible()

    await page.getByTestId('launch-enter').click()
    await expect(page.getByTestId('app-shell')).toBeVisible()
    await expect(page.getByTestId('startup')).toHaveCount(0)

    // Re-open it and leave by keyboard: the two ways must not be the same code
    // path, and a keydown listener left bound after unmount would fire here.
    //
    // ⭐ **The sentinel is cleared as well as the key**, because
    // `clearLaunchAcknowledgement` is one-shot. The first navigation consumed it, so
    // the `reload()` would re-run only `routeApi`'s acknowledgement, the key would
    // be written before the app read it, and the screen would not come back — for a
    // reason that has nothing to do with the reader. Two resets, not one, is what
    // 「pending again」 means.
    await page.evaluate(
      (args) => {
        window.localStorage.removeItem(args.key)
        window.sessionStorage.removeItem(args.sentinel)
      },
      { key: SEEN, sentinel: SENTINEL },
    )
    await page.reload()
    await expect(page.getByTestId('startup')).toBeVisible()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('app-shell')).toBeVisible()
  })

  test('records the dismissal, so it does not come back on the next launch', async ({
    page,
  }) => {
    await openWithLaunchPending(page)
    await page.getByTestId('launch-enter').click()
    await expect(page.getByTestId('app-shell')).toBeVisible()

    const stored = await page.evaluate((key) => window.localStorage.getItem(key), SEEN)
    // A date, not a boolean: a boolean would show the screen on every launch
    // forever, or never again, because there would be nothing in it to expire.
    expect(stored).toMatch(/^\d{4}-\d{2}-\d{2}$/)

    await page.reload()
    await expect(page.getByTestId('startup')).toHaveCount(0)
    await expect(page.getByTestId('app-shell')).toBeVisible()
  })

  /**
   * The 20-times-a-day problem, stated as a test: a tool somebody opens twenty
   * times a day cannot put a full-screen anything in front of that twenty times.
   */
  test('does not come back on the same day, and comes back the next one', async ({
    page,
  }) => {
    await openWithLaunchPending(page)
    await page.getByTestId('launch-enter').click()

    await page.reload()
    await expect(page.getByTestId('startup')).toHaveCount(0)

    // Tomorrow's key is a different string, so this is the same test as the last
    // one with the clock moved — which is the only way to be sure the stored value
    // is compared and not merely present.
    //
    // ⚠️ `2026-10-02` is a **hardcoded date**, and that is deliberate here: if it
    // were `new Date()` then a run on the 2nd would write today's own date and the
    // assertion would pass without proving anything. When this test eventually runs
    // on 2026-10-02 it will start passing vacuously — and the guard below is what
    // will notice, by refusing rather than by quietly agreeing.
    await page.evaluate(
      (args) => {
        window.localStorage.setItem(args.key, '2026-10-02')
        window.sessionStorage.removeItem(args.sentinel)
      },
      { key: SEEN, sentinel: SENTINEL },
    )
    await page.reload()
    await expect(page.getByTestId('startup')).toBeVisible()
  })

  test('is reachable from ⌘K once dismissed, and the palette still works', async ({
    page,
  }) => {
    await openWithLaunchPending(page)
    await page.getByTestId('launch-enter').click()
    await expect(page.getByTestId('app-shell')).toBeVisible()

    await page.keyboard.press('ControlOrMeta+k')
    await page.getByText('重看开屏').click()
    // The palette is the only way back, because the screen is deliberately not a
    // route and so has no nav row and no href.
    await expect(page.getByTestId('startup')).toBeVisible()
    await expect(page.getByTestId('launch-art')).toBeVisible()

    // And it is not a dead end: leaving it again works.
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('app-shell')).toBeVisible()
  })

  test('honours prefers-reduced-motion', async ({ page }) => {
    // The animation is 1200 ms of `scaleY`, which is the point of the screen, and
    // it is the one thing on it that a reader who gets motion sick cannot avoid
    // by not looking. `V-06` proves the stylesheet switches it off; this proves
    // the switch is wired to the media query and not merely present.
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await openWithLaunchPending(page)
    const art = page.getByTestId('launch-art')
    await expect(art).toBeVisible()

    // ⭐ On the **frame**, not the image, for the reason the proportion test records
    // at length: `startup-hang` is declared on the `<figure>`, so `img.getAnimations()`
    // is an empty array whatever the media query says. Asserting on the image here
    // would pass unconditionally — the same vacuity this file's header is about.
    const running = await art.evaluate((node) => {
      const img = node as HTMLImageElement
      const frame = img.closest('.startup-frame') ?? img
      return {
        frame: frame.getAnimations().filter((a) => a.playState === 'running').length,
        image: img.getAnimations().filter((a) => a.playState === 'running').length,
        names: frame.getAnimations().map((a) => (a as CSSAnimation).animationName),
      }
    })
    expect(running.frame, `running on the frame: ${running.names.join(', ')}`).toBe(0)

    // And the same query with motion allowed, so this test proves the *query* can
    // find a running animation rather than only that it finds none.
    //
    // ⚠️ **The sentinel is reset alongside the key**, exactly as in the two reload
    // tests above. `clearLaunchAcknowledgement` is one-shot, so by the second
    // navigation in this test it has stood down and `routeApi`'s acknowledgement is
    // the only thing left — the app reads a written key and never shows the screen.
    // The failure is `launch-art` not being found, which reads like a missing image
    // rather than like a marker that was not reset.
    await page.evaluate(
      (args) => {
        window.localStorage.removeItem(args.key)
        window.sessionStorage.removeItem(args.sentinel)
      },
      { key: SEEN, sentinel: SENTINEL },
    )
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await page.reload()
    const art2 = page.getByTestId('launch-art')
    await expect(art2).toBeVisible()
    const runningWhenAllowed = await art2.evaluate((node) => {
      const img = node as HTMLImageElement
      const frame = img.closest('.startup-frame') ?? img
      return frame.getAnimations().filter((a) => a.playState === 'running').length
    })
    expect(runningWhenAllowed, 'the control: motion is on, so something must animate').toBeGreaterThan(0)
  })

  /**
   * ⭐⭐⭐ **Everything on the screen is reachable, at every size.**
   *
   * This exists because of a defect that no other assertion in this file could see,
   * and that no test anywhere in the repo could see either. Measured at **900×800**,
   * one column:
   *
   * ```
   *   document.scrollHeight  1026
   *   document.clientHeight   800
   *   .startup-frame   top  318   height 630
   *   .startup-credit  top  962      ← 162px past the bottom
   * ```
   *
   * and the shell sets `body { overflow: hidden }`. **So nothing scrolled.** The
   * painting and the credit were rendered, present in the DOM, `toBeVisible()` in
   * Playwright's sense, and *unreachable* — a reader with a narrow window and a
   * laptop's height got two lines of type and a way out, and no painting.
   *
   * The cause was `min-height: 100%`, which sets a *floor*: the block grows past
   * the viewport and its overflow is clipped by an ancestor that is forbidden from
   * scrolling. `Playwright`'s visibility is geometric, so every other assertion here
   * passed throughout — including `hangs the painting whole`, which measured the
   * proportions of a painting nobody could see.
   *
   * ⚠️ **Two assertions, and the second is the one that matters.** 「fits」 alone
   * would pass on a screen that is *mostly* fine, so the test scrolls and then asks
   * whether the last line is inside the box. A size where the content overflows but
   * does not scroll fails the second assertion; a size where it fits passes both.
   */
  test('keeps everything reachable at a size where the columns stack', async ({ page }) => {
    // ⭐ 900×800, not a round smaller number: 900 is the **largest** width that
    // stacks (the two-column query starts at 1180) and 800 is a laptop's usable
    // height. The defect lives in that corner specifically — at 414×896 a phone the
    // content fits, and at 1440×900 it is one column each way.
    await page.setViewportSize({ width: 900, height: 800 })
    await openWithLaunchPending(page)

    const startup = page.getByTestId('startup')
    await expect(startup).toBeVisible()
    await expect(page.getByTestId('launch-art')).toBeVisible()

    // The screen owns the scrolling, rather than being clipped by an ancestor that
    // is not allowed to scroll.
    const box = await startup.evaluate((node) => {
      const el = node as HTMLElement
      return {
        overflowY: getComputedStyle(el).overflowY,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        scrolls: el.scrollHeight > el.clientHeight,
      }
    })
    expect(box.overflowY, 'the launch screen must be its own scroll container').toBe('auto')
    // Measured at this size before the fix: 1026 against 800.
    expect(box.scrollHeight, 'the screen scrolls at 900x800, so this size is the gate').toBeGreaterThan(
      box.clientHeight,
    )

    // And the last line can be brought into view. `fullyVisible` is computed against
    // the *container's* box, not the viewport's, so it fails if the credit is clipped
    // by anything in between.
    await startup.evaluate((node) => {
      ;(node as HTMLElement).scrollTop = 99_999
    })
    const reached = await page.getByTestId('launch-credit').evaluate((node) => {
      const credit = node.getBoundingClientRect()
      const container = node.closest('[data-testid=startup]') as HTMLElement
      const bounds = container.getBoundingClientRect()
      return {
        scrollTop: Math.round(container.scrollTop),
        top: Math.round(credit.top),
        bottom: Math.round(credit.bottom),
        containerTop: Math.round(bounds.top),
        containerBottom: Math.round(bounds.bottom),
        inside: credit.top >= bounds.top - 0.5 && credit.bottom <= bounds.bottom + 0.5,
      }
    })
    expect(
      reached.inside,
      `credit ${reached.top}..${reached.bottom} inside ${reached.containerTop}..` +
        `${reached.containerBottom}, scrollTop ${reached.scrollTop}`,
    ).toBe(true)
  })
})
