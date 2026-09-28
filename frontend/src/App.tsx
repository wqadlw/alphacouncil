import { useEffect } from 'react'
import InstrumentPage from './InstrumentPage'
import PoolPage from './PoolPage'
import RetrospectivePage from './RetrospectivePage'
import ReviewPage from './ReviewPage'
import TodayPage from './TodayPage'
import { POOL_HREF, titleFor, useRoute } from './routing'
import { AppShell } from './ui'

export default function App() {
  const route = useRoute()
  const name = titleFor(route)

  // The title comes off the route table now. It was a nested ternary here, which
  // meant a new view silently inherited another view's title and nothing
  // complained.
  useEffect(() => {
    document.title = `${name} · AlphaCouncil`
  }, [name])

  return (
    <AppShell>
      {/*
        Written as a switch over the route name rather than a chain of early
        returns, so that adding a view is a visible omission here instead of a
        line that happens to be missing somewhere.
      */}
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
      {route.name === 'unknown' ? <UnknownRoute raw={route.raw} /> : null}
    </AppShell>
  )
}

/**
 * An unrecognised address says so.
 *
 * Falling back to the today page would show a plausible page for a mistyped link,
 * which is the kind of failure that looks like success — the same reason the
 * backend reports an ambiguous ticker instead of picking a market for you.
 *
 * It renders **inside the shell**, so even a bad address keeps the nav: a reader
 * who mistypes should be able to get out by clicking, not by editing the URL bar.
 * That is the whole reason the shell exists.
 */
function UnknownRoute({ raw }: { raw: string }) {
  return (
    <div className="mx-auto max-w-[860px] px-8 py-10">
      <h1 className="serif text-[26px] leading-tight">这个地址看不懂</h1>
      <p className="mt-2 text-ink-soft">
        没有一条路由匹配 <code className="num text-ink">{raw}</code>。标的页的地址形如{' '}
        <code className="num text-ink">#/i/sh/600519</code>。
      </p>
      <p className="mt-4">
        <a href={POOL_HREF} className="text-navy">
          ← 回到关注池
        </a>
      </p>
    </div>
  )
}
