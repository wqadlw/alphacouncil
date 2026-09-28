import { useEffect } from 'react'
import InstrumentPage from './InstrumentPage'
import PoolPage from './PoolPage'
import RetrospectivePage from './RetrospectivePage'
import ReviewPage from './ReviewPage'
import TodayPage from './TodayPage'
import VaultPage from './VaultPage'
import { AppShellFrame } from './app/AppShellFrame'
import { todayLabel } from './format'
import { POOL_HREF, titleFor, useRoute } from './routing'

export default function App() {
  const route = useRoute()
  const name = titleFor(route)

  useEffect(() => {
    document.title = `${name} · AlphaCouncil`
  }, [name])

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
    <AppShellFrame route={route.name} instrument={instrument} title={heading}>
      {route.name === 'instrument' ? (
        // Keyed on the instrument so switching targets remounts the page: without
        // it React would reuse the component, and the previous instrument's loaded
        // record would stay on screen until the new fetch resolved.
        <InstrumentPage
          key={`${route.market}/${route.code}`}
          market={route.market}
          code={route.code}
        />
      ) : null}
      {route.name === 'pool' ? <PoolPage /> : null}
      {route.name === 'review' ? <ReviewPage /> : null}
      {route.name === 'retrospective' ? <RetrospectivePage /> : null}
      {route.name === 'today' ? <TodayPage /> : null}
      {route.name === 'vault' ? <VaultPage /> : null}
      {route.name === 'unknown' ? <UnknownRoute raw={route.raw} /> : null}
    </AppShellFrame>
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
      <p className="text-[13px] text-ink-soft">
        没有一条路由匹配 <code className="num text-ink">{raw}</code>。标的页的地址形如{' '}
        <code className="num text-ink">#/i/sh/600519</code>，或按 <kbd className="num">⌘K</kbd> 搜索。
      </p>
      <p className="mt-3 text-[13px]">
        <a href={POOL_HREF} className="text-navy hover:underline">
          回到关注池
        </a>
      </p>
    </div>
  )
}
