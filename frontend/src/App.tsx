import { useEffect } from 'react'
import InstrumentPage from './InstrumentPage'
import PoolPage from './PoolPage'
import TodayPage from './TodayPage'
import { POOL_HREF, useRoute } from './routing'

export default function App() {
  const route = useRoute()

  useEffect(() => {
    document.title =
      route.name === 'instrument'
        ? `${route.code}.${route.market.toUpperCase()} · AlphaCouncil`
        : route.name === 'pool'
          ? 'AlphaCouncil · 关注池'
          : 'AlphaCouncil · 今天'
  }, [route])

  if (route.name === 'instrument') {
    // Keyed on the instrument so switching targets remounts the page: without
    // it React would reuse the component, and the previous instrument's loaded
    // record would stay on screen until the new fetch resolved.
    return (
      <InstrumentPage
        key={`${route.market}/${route.code}`}
        market={route.market}
        code={route.code}
      />
    )
  }

  if (route.name === 'pool') return <PoolPage />
  if (route.name === 'today') return <TodayPage />

  // TypeScript narrowing leaves only `unknown` here.
  return <UnknownRoute raw={route.raw} />
}

/**
 * An unrecognised address says so.
 *
 * Falling back to the pool would show a plausible page for a mistyped link,
 * which is the kind of failure that looks like success — the same reason the
 * backend reports an ambiguous ticker instead of picking a market for you.
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
