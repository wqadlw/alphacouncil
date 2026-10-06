import { useCallback, useEffect, useState, type ReactNode } from 'react'
import InstrumentPage from './InstrumentPage'
import { ErrorBoundary } from './app/ErrorBoundary'
import PoolPage from './PoolPage'
import RetrospectivePage from './RetrospectivePage'
import ReviewPage from './ReviewPage'
import { StartupPage } from './StartupPage'
import { isHomeAddress, launchSeenToday, markLaunchSeen } from './launchLogic'
import TodayPage from './TodayPage'
import UniversePage from './UniversePage'
import VaultPage from './VaultPage'
import { AppShellFrame } from './app/AppShellFrame'
import { DemoBanner } from './DemoBanner'
import { todayLabel } from './format'
import { POOL_HREF, titleFor, useRoute, type Route } from './routing'

/**
 * ⭐⭐ One page per enumerated view, as a `Record` ⭐ **and that is the fix, not the
 * tidying.**
 *
 * ⚠️⚠️ **This was six parallel ternaries**, and the repository already knows what that
 * costs: `F-211` and `regressions/0005` record a ternary over a union that was *not*
 * exhaustive, and the same lesson had to be learned twice in this file's neighbourhood ⭐
 * `routing.ts` fixed `queueHref` exactly this way ⭐ **and `App.tsx` kept the old shape.**
 *
 * ⭐ **The failure a parallel ternary cannot report.** Adding a row to `ROUTES` without
 * adding a line here compiles, passes `tsc`, passes vitest, passes Playwright ⭐ **and the
 * nav row, the ⌘K entry and `document.title` all work** ⭐ — because they are derived from
 * `ROUTES` ⭐ **while `#/universe` paints an empty frame. Zero red.**
 *
 * ⇒ A `Record<RouteName, ReactNode>` turns 「added a route, forgot the page」 from silence
 * into **a compile error**, ⭐ which is the same bargain `queueHref` made and the reason
 * `regressions/0005` exists at all.
 *
 * ⭐ `instrument` is **not** here ⭐ **on purpose**: it is a parsed route rather than an
 * enumerated one (`routing.ts` `Route`), it carries two parameters, and it is the one that
 * needs a `key` so switching targets remounts the page ⭐ — so it stays an explicit branch
 * above, where its `key` and its arguments are visible.
 */
/**
 * ⭐⭐ **They are thunks, not elements, and the first version of this was not.**
 *
 * ⭐ A module-level `Record<ViewName, ReactNode>` holding *elements* **passed `tsc`,
 * passed vitest, and failed E2E** ⭐ with `strict mode violation: getByTestId('card-schedule-out')
 * resolved to 2 elements` ⭐ — ⭐ **the review page mounted twice.**
 *
 * ⭐ The reason: a ternary `{c ? <X /> : null}` builds a **fresh element every render**,
 * and React's reconciler relies on that to unmount the old page when the type changes. ⭐
 * A constant element is one object reused forever, ⭐ so the old subtree was never torn
 * down and the new one went in beside it.
 *
 * ⇒ **The `Record` buys exhaustiveness and costs element freshness, and only the second
 * one is visible ⭐ ** in a gate, and only as a duplicated test id.** ⭐ That is the most
 * expensive shape this repository knows: a defect whose symptom is three files away from
 * its cause.
 */
type ViewName = Exclude<Route['name'], 'instrument'>

const VIEWS: Record<ViewName, () => ReactNode> = {
  pool: () => <PoolPage />,
  review: () => <ReviewPage />,
  retrospective: () => <RetrospectivePage />,
  today: () => <TodayPage />,
  universe: () => <UniversePage />,
  vault: () => <VaultPage />,
  unknown: () => <UnknownRoute raw={window.location.hash} />,
}
export default function App() {
  const route = useRoute()
  const name = titleFor(route)

  /**
   * ⭐ **The launch screen's visibility lives here and nowhere else.**
   *
   * It is `useState` seeded from `localStorage` rather than read during render,
   * because the read has to happen exactly once: reading it on every render would
   * mean a reader who opens the ⌘K palette, picks 重看开屏, and then reloads gets
   * the screen again, because entering it rewrites the key. Seeding once and
   * keeping it in state makes the launch screen's state a fact about **this app
   * run**, and the key a fact about **the day**.
   *
   * ⭐ **A deep link is a reason to skip the launch screen, and this is not a
   * convenience — it is what 101 failing E2E tests were.**
   *
   * The first version put the launch screen in front of *every* route on a first
   * launch, and the whole `e2e/` suite broke: Playwright gives each test a fresh
   * context but `localStorage` is per-origin, so whichever spec ran first and
   * looked at the launch screen left the key set for all the others. Ten tests
   * passed, 101 failed, and every failure had the same cause — the shell was not
   * on screen.
   *
   * The two available fixes were both wrong:
   *
   * - **Clear the key in each of the twelve specs.** That makes the suite green and
   *   leaves the product broken, because the bug is not a test bug. A reader who
   *   opens `#/i/sh/600519` from a link — a bookmark, a note, an ⌘K jump after a
   *   restart — should land on that instrument, not be asked to dismiss a
   *   full-screen painting first. Twelve edits to twelve files to preserve a
   *   behaviour no reader asked for.
   * - **Only show the screen on `#/`.** Simpler, and wrong in the other direction:
   *   `#` and `#/` both mean today, and a reader who restarts the app onto today
   *   would see it — correct — but so would a reader whose browser restored the
   *   last hash for any reason.
   *
   * So the rule is: **the launch screen is shown when the reader arrives with no
   * particular destination in mind.** `#/` is 「let me start here」 and is the only
   * address that means it. Anything else is an answer to a question they asked
   * earlier, and the right thing to do with it is to answer it.
   */
  const [launchDone, setLaunchDone] = useState(() => {
    if (!isHomeAddress(window.location.hash)) return true
    return launchSeenToday(
      new Date(),
      // ⭐ Read through a guard rather than bare. `localStorage` is `undefined` in
      // some non-browser contexts and **throws on access** under a `file://`
      // origin in some webviews, so `launchLogic` takes the storage as a parameter
      // and this is the one place that decides whether there is any to pass.
      typeof window === 'undefined' ? null : window.localStorage,
    )
  })

  const enter = useCallback(() => {
    markLaunchSeen(
      new Date(),
      typeof window === 'undefined' ? null : window.localStorage,
    )
    setLaunchDone(true)
    // ⭐ **Navigate only if the reader is not already on a view.** Entering from
    // `#/unknown` should land on today, because that is what 「进入」 means; but
    // entering from `#/vault` after using ⌘K to reach the palette must not throw
    // the reader out of the page they were on.
    if (window.location.hash === '' || window.location.hash === '#') {
      window.location.hash = '#/'
    }
  }, [])

  useEffect(() => {
    document.title = `${name} · AlphaCouncil`
  }, [name])

  // ⭐ The launch screen renders **instead of** the shell, not inside it. See
  // `StartupPage`'s header: it has no address, and putting it in `ROUTES` would
  // give it a `#/start` that nothing should be able to reach and a sidebar row
  // that does nothing.
  if (!launchDone) {
    return (
      // ⭐ **The banner is above BOTH branches, not inside the frame** (spec 057).
      // `StartupPage` renders *instead of* the shell — see the comment at this `if` — so a
      // banner inside `AppShellFrame` would be **invisible on the very first screen
      // someone sees**, ⭐ which is the one moment it most has to appear.
      <>
        <DemoBanner />
        <StartupPage onEnter={enter} />
      </>
    )
  }

  const instrument =
    route.name === 'instrument' ? { market: route.market, code: route.code } : null

  /*
   * ⭐ The pane header carries the date for the today page, as part of the title
   * rather than as a subtitle.
   *
   * It is one sentence — 「今天 · 2026-09-28 · 周一」 — and splitting it across a
   * title and a subtitle printed 今天 twice, which is the sort of redundancy a
   * reader registers as noise without being able to say why. The frame has a
   * `subtitle` slot and it would have read acceptably; the reason to avoid it is
   * that `TodayPage` is the frame's *child*, so a page cannot fill that slot for
   * itself, and threading a `useTodayLabel` up through `App` to feed it would have
   * been plumbing to protect a duplication.
   *
   * `today-hub.spec.ts:171` keys on the literal `今天 ·`, which is the right thing
   * to key on: the date is what distinguishes today's page from a static list,
   * so a test that ignored it would pass on a page that had quietly lost it.
   */
  const heading =
    route.name === 'today' ? `今天 · ${todayLabel(new Date())}` : name

  return (
    <>
      <DemoBanner />
      <AppShellFrame
        route={route.name}
      instrument={instrument}
      title={heading}
      commands={[
        // ⭐ How a reader gets the launch screen back after dismissing it.
        // `StartupPage` is not a route, so it has no entry in the nav and no
        // `href` — which means the ⌘K palette is the only place it can be
        // reached from, and this is that entry. It calls the same `enter` the
        // button does, so 「进入」 and 「重看开屏」 cannot drift apart.
        {
          id: 'launch-show',
          group: '去看',
          label: '重看开屏',
          hint: `${new Date().getDate()} / 31`,
          run: () => {
            // ⭐ **Nothing is written here, and the comment above used to say the
            // opposite.** It said "clear the day key first", then called
            // `markLaunchSeen` — which does not clear it, it *writes today's date*.
            // The reasoning was that a re-shown screen must not be acknowledged
            // again immediately, and the write was a leftover from a version that
            // used one key as a "currently showing" flag.
            //
            // With today's state living in React, the honest implementation is to
            // change nothing on disk: the key still says this day was seen, which
            // is **true** — the reader has seen it, they are choosing to look at it
            // again — and `launchDone` is what governs whether it is on screen. A
            // reader who now reloads gets the shell, which is what they had before
            // they opened the palette.
            setLaunchDone(false)
          },
        },
      ]}
    >
      {/*
        The boundary wraps the **route content only**, never the shell.

        That placement is the whole design: a page that throws costs the reader that
        page, and keeps the navigation, the search box and the command palette — so
        they can go somewhere else rather than stare at a white window. Wrapping
        the shell instead would defeat the purpose, because the shell is the only
        way out of a broken page.
      */}
      {/*
        Keyed on the route so a failed page does not follow the reader onward.

        A boundary that has caught an error holds that state until it unmounts,
        so without the key one broken page would blank every page after it — which
        is a strictly worse failure than the one it was built to contain, and one
        that reads as "the application is broken now" rather than "this page was".
        Measured: navigating away from the failure screen kept showing it.
      */}
      <ErrorBoundary key={route.name === 'instrument' ? `${route.market}/${route.code}` : route.name}>
        {route.name === 'instrument' ? (
          // Keyed on the instrument so switching targets remounts the page: without
          // it React would reuse the component, and the previous instrument's loaded
          // record would stay on screen until the new fetch resolved.
          <InstrumentPage
            key={`${route.market}/${route.code}`}
            market={route.market}
            code={route.code}
          />
        ) : (
          VIEWS[route.name]()
        )}
      </ErrorBoundary>
      </AppShellFrame>
    </>
  )
}

/**
 * An unrecognised address says so.
 *
 * Falling back to the today page would show a plausible page for a mistyped link,
 * which is the kind of failure that looks like success — the same reason the
 * backend reports an ambiguous ticker instead of picking a market for you.
 *
 * It renders **inside the frame**, so a reader who mistypes can leave by clicking
 * or by pressing ⌘K. That is the whole reason the frame is a frame.
 *
 * ⭐ **No heading here.** The frame's header already renders `titleFor('unknown')`,
 * which is this exact sentence, so writing it again put the same words on screen
 * twice. That was not cosmetic: `routing.spec.ts` and `nav.spec.ts` both locate
 * the message with `getByText('这个地址看不懂')`, and Playwright's strict mode
 * refuses a locator that resolves to more than one element — so the duplicate
 * turned two passing tests red. Naming the page is the frame's job; the content's
 * job is to say what the address was and how to leave.
 */
function UnknownRoute({ raw }: { raw: string }) {
  return (
    <div className="p-6">
      <p className="type-prose text-ink-soft">
        没有一条路由匹配 <code className="num text-ink">{raw}</code>。标的页的地址形如{' '}
        <code className="num text-ink">#/i/sh/600519</code>，或按 <kbd className="num">⌘K</kbd> 搜索。
      </p>
      <p className="mt-3 type-prose">
        <a href={POOL_HREF} className="text-navy hover:underline data-[motion=l1]">
          回到关注池
        </a>
      </p>
    </div>
  )
}
