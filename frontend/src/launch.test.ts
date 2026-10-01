/**
 * The launch screen's three decisions: which painting, whether today has been
 * seen, and what the credit says.
 *
 * ⭐ **There is no `render` in this file, and that is not a shortcut.** This
 * repository has no `jsdom` and no `@testing-library/react` — `styleguide.test.ts`
 * records the choice and says a component cannot be rendered in a unit test here,
 * so rendering assertions live in `e2e/launch.spec.ts` under Playwright.
 *
 * The first version of this test imported `render` and `screen` and failed to
 * parse, because the packages are not installed. `V-07` and 宪法 §3.2.1 exist so
 * that a convenience does not become a dependency, so the answer was to move the
 * decisions into `launchLogic.ts` rather than to install a DOM.
 *
 * Each test below is here because the thing it checks is wrong in a way that does
 * not announce itself.
 */

import { describe, expect, it } from 'vitest'
import { SCROLLS, scrollFor } from './art/scroll/manifest'
import { parseHash } from './routing'
import {
  creditLine,
  isHomeAddress,
  LAUNCH_SEEN_KEY,
  launchSeenToday,
  localDayKey,
  markLaunchSeen,
} from './launchLogic'

/** A `Storage` stand-in, so none of this needs a DOM. */
function memory(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    read: () => map.get(LAUNCH_SEEN_KEY) ?? null,
  }
}

/** A `Storage` that throws, which is what a private window does. */
const hostile = {
  getItem: () => {
    throw new Error('storage disabled')
  },
  setItem: () => {
    throw new Error('storage disabled')
  },
}

describe('which painting a date gets', () => {
  /**
   * The day of the month, not a hash of the date.
   *
   * This is the property that makes the choice checkable rather than arbitrary:
   * the 14th of April and the 14th of May get the same painting, because the day
   * of the month is something a reader can predict. A hash would be stable and
   * inexplicable, which is worse than either.
   */
  it('is the day of the month', () => {
    const april = new Date(2026, 3, 14)
    const may = new Date(2026, 5, 14)
    expect(scrollFor(april).day).toBe(14)
    expect(scrollFor(may).day).toBe(14)
    expect(scrollFor(april).accession).toBe(scrollFor(may).accession)
  })

  it('gives every day of a 31-day month its own painting', () => {
    for (const day of [1, 2, 15, 28, 30, 31]) {
      expect(scrollFor(new Date(2026, 9, day)).day).toBe(day)
    }
  })

  /**
   * February has no 30th or 31st, and neither does April, June, September and
   * November.
   *
   * The first version indexed `SCROLLS[date - 1]` with no clamp, so the last week
   * of every 30-day month had **no picture at all** — five weeks a year with a
   * hole in the launch screen, and a hole that only shows up in February and is
   * therefore never noticed. `scrollFor` clamps into range instead.
   */
  it('clamps a 30-day month onto the last painting rather than showing none', () => {
    expect(scrollFor(new Date(2026, 1, 28)).day).toBe(28)
    expect(scrollFor(new Date(2026, 3, 30)).day).toBe(30)
    // Day 0 cannot happen from `getDate()`, but the clamp is written as a range
    // and a range with one end untested is a range with one end wrong.
    expect(scrollFor(new Date(2026, 9, 1)).day).toBe(1)
  })

  it('has 31 distinct paintings, one per day', () => {
    expect(SCROLLS).toHaveLength(31)
    expect(new Set(SCROLLS.map((s) => s.accession)).size).toBe(31)
  })

  it('numbers them 1..31 with no gap', () => {
    expect(SCROLLS.map((s) => s.day)).toEqual(
      Array.from({ length: 31 }, (_, i) => i + 1),
    )
  })
})

describe('the manifest is honest about its own provenance', () => {
  /**
   * The first generator run wrote 31 paintings with an **empty accession and an
   * empty source URL**, because it read the API's field names
   * (`accession_number`, `creators[]`, `url`) off a cached record that had already
   * been trimmed to `accession` / `artist` / `page`. Nothing about the images was
   * wrong and the build was green; the claim 「public domain」 simply had nothing
   * behind it. These three assertions are that failure, made permanent.
   */
  it('gives every painting an accession number and a source page', () => {
    const bad = SCROLLS.filter(
      (s) => s.accession.trim() === '' || !s.source.startsWith('https://'),
    )
    expect(bad.map((s) => `day ${s.day}`)).toEqual([])
  })

  it('credits the museum on every painting', () => {
    const bad = SCROLLS.filter((s) => !s.museum.includes('Cleveland'))
    expect(bad.map((s) => `day ${s.day}`)).toEqual([])
  })

  /**
   * A hand-typed width is a width that is eventually wrong invisibly: the layout
   * reserves the wrong box, the image lands in it, and nothing says so. The
   * manifest is generated from measured dimensions for exactly this reason.
   */
  it('records a measured size for every painting', () => {
    const bad = SCROLLS.filter((s) => !(s.width > 0 && s.height > 0))
    expect(bad.map((s) => `day ${s.day}`)).toEqual([])
  })

  it('has a title for every painting, because the credit line needs one', () => {
    const bad = SCROLLS.filter((s) => s.title.trim() === '')
    expect(bad.map((s) => `day ${s.day}`)).toEqual([])
  })
})

describe('the day key is local, not UTC', () => {
  /**
   * At 23:30 local on the 1st, UTC has already rolled to the 2nd in UTC+8. A
   * `toISOString().slice(0, 10)` key would therefore store **tomorrow's** date,
   * and tonight's screen would show tomorrow's painting beside today's date.
   *
   * Built from local components on purpose: a `…T23:30:00Z` literal is 07:30 on
   * the 2nd on this machine, so asserting against it would test nothing.
   */
  it('agrees with the local clock across a midnight boundary', () => {
    expect(localDayKey(new Date(2026, 9, 1, 23, 59, 59))).toBe('2026-10-01')
    expect(localDayKey(new Date(2026, 9, 2, 0, 0, 0))).toBe('2026-10-02')
  })

  it('zero-pads the month and the day', () => {
    // Unpadded, `2026-1-5` and `2026-01-05` would be two different keys for the
    // same day depending on which month wrote it.
    expect(localDayKey(new Date(2026, 0, 5))).toBe('2026-01-05')
    expect(localDayKey(new Date(2026, 10, 30))).toBe('2026-11-30')
  })
})

describe('once a day, not once a session', () => {
  it('shows the screen when today has not been acknowledged', () => {
    expect(launchSeenToday(new Date(2026, 9, 1), memory())).toBe(false)
  })

  it('does not show it twice on the same day', () => {
    const store = memory()
    markLaunchSeen(new Date(2026, 9, 1), store)
    expect(launchSeenToday(new Date(2026, 9, 1, 23, 59), store)).toBe(true)
  })

  it('shows it again the next day', () => {
    const store = memory()
    markLaunchSeen(new Date(2026, 9, 1), store)
    expect(launchSeenToday(new Date(2026, 9, 2), store)).toBe(false)
  })

  it('shows it again the next month, even on the same day number', () => {
    const store = memory()
    markLaunchSeen(new Date(2026, 9, 1), store)
    expect(launchSeenToday(new Date(2026, 10, 1), store)).toBe(false)
  })

  /**
   * A boolean would show the screen on every launch forever, or never again,
   * because there would be nothing in it to expire. The key holds the **date**.
   */
  it('stores the date, not a boolean', () => {
    const store = memory()
    markLaunchSeen(new Date(2026, 9, 1), store)
    expect(store.read()).toBe('2026-10-01')
  })

  /**
   * A private window throws on both calls. Throwing would mean the app cannot
   * start at all, which is a far worse outcome than one extra launch screen.
   */
  it('treats unavailable storage as "not seen" rather than throwing', () => {
    expect(launchSeenToday(new Date(2026, 9, 1), hostile)).toBe(false)
    expect(() => markLaunchSeen(new Date(2026, 9, 1), hostile)).not.toThrow()
  })

  it('treats absent storage as "not seen", for the same reason', () => {
    expect(launchSeenToday(new Date(2026, 9, 1), null)).toBe(false)
    expect(() => markLaunchSeen(new Date(2026, 9, 1), null)).not.toThrow()
  })

  it('ignores a value written for another day', () => {
    // A stale key from a version that wrote something else must not suppress
    // today's screen.
    const store = memory({ [LAUNCH_SEEN_KEY]: 'yes' })
    expect(launchSeenToday(new Date(2026, 9, 1), store)).toBe(false)
  })
})

/**
 * ⭐ **Which addresses show the launch screen, and why this is the assertion that
 * matters most in this file.**
 *
 * The launch screen was first put in front of every route on a first launch, and
 * the whole `e2e/` suite broke — 10 passed, 101 failed — because `localStorage` is
 * keyed on the origin and `vite preview` serves every spec from one. Whichever spec
 * looked at the screen first wrote the key for the rest, and every later assertion
 * failed on 「the shell is not on screen」 rather than on anything it was written to
 * check.
 *
 * The suite was pointing at a real defect: a reader who opens `#/i/sh/600519` from
 * a bookmark has asked a specific question, and a full-screen painting in front of
 * it is the app putting its own onboarding above the reader's intent.
 *
 * Three spellings mean today and all three must show the screen, because
 * `parseHash` normalises exactly these three onto the today route — a reader who
 * restarts the app onto `#` should see it, and one who lands on the canonical `#/`
 * should not be treated as having asked for something specific.
 */
describe('which addresses show the launch screen', () => {
  it('shows it for the three spellings of 「start here」', () => {
    expect(isHomeAddress('')).toBe(true)
    expect(isHomeAddress('#')).toBe(true)
    expect(isHomeAddress('#/')).toBe(true)
  })

  it('skips it for every address that names a destination', () => {
    for (const hash of [
      '#/pool',
      '#/review',
      '#/retrospective',
      '#/vault',
      '#/i/sh/600519',
      '#/nonsense',
      '#/pool?x=1',
    ]) {
      expect(isHomeAddress(hash), `${hash} should not show the launch screen`).toBe(false)
    }
  })

  it('agrees with the route table about which hashes are today', () => {
    // Two implementations of "is this home" is the shape this repository keeps
    // meeting, so the two are compared rather than trusted. `parseHash` is the
    // authority on what a hash *means*; this module is the authority on whether to
    // interrupt, and it must not disagree about the first question.
    for (const hash of ['', '#', '#/', '#/pool', '#/vault', '#/i/sh/600519']) {
      const meansToday = parseHash(hash).name === 'today'
      expect(isHomeAddress(hash), `hash ${JSON.stringify(hash)}`).toBe(meansToday)
    }
  })
})

describe('the credit line', () => {
  /**
   * The parenthetical life dates are stripped. `Cleveland Museum of Art` already
   * places the object, and a launch screen's credit is the one line nobody should
   * have to read twice; the artist's dates are the museum's metadata, not the
   * painting's.
   */
  it('drops the artist life dates but keeps the painting date', () => {
    const line = creditLine(
      'Shen Zhou (Chinese, 1427–1509)',
      'after 1490',
      'Distant View of Tiger Hill',
      'The Cleveland Museum of Art',
    )
    expect(line).not.toContain('1427')
    expect(line).toContain('Shen Zhou')
    expect(line).toContain('after 1490')
    expect(line).toContain('《Distant View of Tiger Hill》')
    expect(line).toContain('The Cleveland Museum of Art')
  })

  it('omits the brackets rather than printing an empty 《》', () => {
    const line = creditLine('Unattributed', '1500s', '', 'Some Museum')
    expect(line).not.toContain('《')
    expect(line).toBe('Unattributed　1500s　Some Museum')
  })

  it('keeps a nested parenthesis out of the artist name', () => {
    // `Bada Shanren (Zhu Da), Chinese, 1626–1705` — a greedy strip would take the
    // whole tail, including the culture, and print nothing.
    const line = creditLine('Bada Shanren (Zhu Da), Chinese, 1626–1705', 'c. 1680', 'X', 'M')
    expect(line).toContain('Bada Shanren')
    expect(line).not.toContain('1626')
  })

  it('renders for all 31 without producing an empty piece', () => {
    for (const s of SCROLLS) {
      const line = creditLine(s.artist, s.date, s.title, s.museum)
      expect(line.trim().length).toBeGreaterThan(0)
      expect(line).not.toContain('《》')
    }
  })
})
