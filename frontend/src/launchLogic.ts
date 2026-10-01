/**
 * The launch screen's decisions, with no React in them.
 *
 * ⭐ **This file exists because the repository has no `jsdom` and no
 * `@testing-library/react`,** and that is a decision `styleguide.test.ts` records
 * rather than an accident — its header says a component cannot be rendered in a
 * unit test here, so rendering assertions belong to the Playwright specs in `e2e/`.
 *
 * The first version of `launch.spec.ts` imported `render` and `screen` and
 * failed to even parse, because the packages are not installed. The fix is not to
 * install them — `V-07` and 宪法 §3.2.1 exist so that a convenience does not
 * become a dependency — but to put the logic where it can be tested without a
 * DOM, and to leave the rendering to `e2e/launch.spec.ts`.
 *
 * So: which painting, whether today has been seen, and what the credit says.
 * Three decisions, no JSX, all of them the kind that are quietly wrong.
 */

/** Where the last acknowledgement is kept, and under what name. */
export const LAUNCH_SEEN_KEY = 'alphacouncil.launch.seen'

/**
 * ⭐ **Whether a hash means 「I have no particular destination in mind」.**
 *
 * Three spellings mean today, and `routing.ts`'s `parseHash` normalises exactly
 * these three onto one table entry — so this is deliberately the same set, written
 * out rather than imported from `parseHash`, because calling `parseHash` here would
 * make a launch-screen decision depend on the route table and the answer would
 * change if someone added a row.
 *
 * ⭐ **The reason this function exists at all is 101 failing tests.**
 *
 * The launch screen was first put in front of every route on a first launch. That
 * is correct for `#/` — it is the address that means 「start here」 — and wrong for
 * everything else: a reader who opens `#/i/sh/600519` from a bookmark or from a
 * note inside the product asked a specific question, and answering it with a
 * full-screen painting is the app deciding its own onboarding outranks the reader's
 * intent.
 *
 * It showed up in the suite first, and it showed up the way this repository keeps
 * meeting things: **not as a failure of the new test, but as 101 failures in twelve
 * unrelated specs.** Playwright hands each test a fresh context, but `localStorage`
 * is keyed on the origin, and `vite preview` serves every spec from one — so the
 * first spec to look at the launch screen wrote the key for all of them, and every
 * later assertion failed on 「the shell is not on screen」 rather than on anything
 * it was written to check.
 *
 * The alternative was to add a `localStorage.clear()` to twelve spec files. That
 * makes the suite green and leaves the product broken, and a suite that has to be
 * kept green by editing the tests it tests is a suite that has stopped testing the
 * product.
 */
export function isHomeAddress(hash: string): boolean {
  return hash === '' || hash === '#' || hash === '#/'
}

/**
 * `YYYY-MM-DD` in **local** time.
 *
 * Local, deliberately: the launch screen follows the reader's day, not UTC's. At
 * 23:30 in UTC+8, UTC has already rolled to tomorrow while the reader's clock and
 * their own sense of the day do not, so a `toISOString().slice(0, 10)` key would
 * store tomorrow's date — and tonight's screen would show tomorrow's painting
 * beside today's date. That is the whole reason this is written out instead of
 * delegated, and `launch.test.ts` pins it against a local-time hour boundary
 * rather than a `Z` literal, because a `Z` literal would test nothing here.
 */
export function localDayKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/**
 * Whether the launch screen has been dismissed today.
 *
 * `storage` is a parameter rather than a global read so this is testable without
 * a DOM, and so the failure case is the caller's to handle: a `localStorage` that
 * throws means the screen shows one extra time, which is a far smaller failure
 * than an app that will not start.
 */
export function launchSeenToday(
  now: Date,
  storage: Pick<Storage, 'getItem'> | null,
): boolean {
  if (storage === null) return false
  try {
    return storage.getItem(LAUNCH_SEEN_KEY) === localDayKey(now)
  } catch {
    return false
  }
}

/** Record the dismissal, for the same reason: silent on failure. */
export function markLaunchSeen(
  now: Date,
  storage: Pick<Storage, 'setItem'> | null,
): void {
  if (storage === null) return
  try {
    storage.setItem(LAUNCH_SEEN_KEY, localDayKey(now))
  } catch {
    /* see launchSeenToday */
  }
}

/**
 * The credit line under the painting.
 *
 * The artist's parenthetical life dates are stripped: `Cleveland Museum of Art`
 * already puts the object in a context, and a credit line is the one place on a
 * launch screen where a second date would read as a second thing to read. The
 * painting's own date stays, because 「哪一年」 is part of 「这是什么」.
 */
export function creditLine(
  artist: string,
  date: string,
  title: string,
  museum: string,
): string {
  const work = title.trim() === '' ? '' : `《${title.trim()}》`
  return `${artistName(artist)}${work}　${date}　${museum}`
}

/**
 * The artist's name, without the museum's metadata.
 *
 * ⭐ **Cleveland appends life dates and sometimes a birth name, in three shapes:**
 * `Shen Zhou (Chinese, 1427–1509)`, `Bada Shanren (Zhu Da), Chinese, 1626–1705`,
 * and `Zha Shibiao (Chinese, 1615–1698)`. The first version of this stripped a
 * trailing `\s*\(.*\)\s*$`, which is greedy and therefore ate **only the last
 * parenthesis pair** — so the second shape printed as
 * 「Bada Shanren (Zhu Da), Chinese, 1626–1705」 with the dates still on screen, in
 * a credit line whose whole purpose is to be short.
 *
 * ⭐ The fix is to stop trying to delete the metadata and instead **take the name
 * itself**: everything up to the first `(` or `,`. That handles all three shapes,
 * cannot leave a trailing comma, and does not depend on the metadata being
 * parenthesised at all — an artist recorded as `Unattributed, China` is handled by
 * the same rule as one recorded as `Shen Zhou (Chinese, 1427–1509)`.
 *
 * `launch.test.ts` pins the nested case, because this is a shape that only appears
 * once in 31 records and would have survived any test written from the other 30.
 */
function artistName(artist: string): string {
  const cut = artist.search(/[(,]/)
  const name = (cut === -1 ? artist : artist.slice(0, cut)).trim()
  return name === '' ? artist.trim() : name
}
