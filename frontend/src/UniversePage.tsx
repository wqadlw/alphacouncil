/**
 * 沪深300 成分史 —— 一个**只读参考**。
 *
 * ⭐⭐ **它只回答一个问题：「这只票是不是在指数里、什么时候进的、什么时候出的」。**
 * 没有排序、没有打分、也没有任何「该看哪几只」的入口。依据是 `constitution.md:802-803`：
 * 一份可检索的清单在 ✅ 那一边，而一份候选名单在 ❌ 那一边 ——
 * ⭐ **而两者的差别就是一个列：给不给 `sortValue`。**
 * `DataTable` 内建排序（`DataTable.tsx:95`），⭐ **不给 `sortValue` 的列就完全不出现排序控件**
 * ⭐ 所以这条边界是**结构上**成立的，而不只是写在文案里。
 *
 * ## ⭐⭐ 新鲜度必须上屏，而且这一页自己写那句话
 *
 * `.ai/data-sources.md:137` 记着「僵尸报价」的成因是「不报错、不崩溃，只是安静地骗人」，
 * 而成分名单是同一族的：**这个源每周一入库**，所以「当前」是那个周一的名单，至多落后七天。
 * ⭐ `grid_point` 由后端随每个答案一起送回来（`api.ts::UniverseFreshness`），
 * ⭐ **而那句话写在这里** —— 因为 `pyproject.toml:130-132` 记着 display wording 历来住在
 * `frontend/`，⭐ 而 `TodayPage.tsx:84-88` 已经为「最后交易日」做过同一件事，
 * ⭐ 包括**提前反驳误读**（「这不是故障，也不是过期的数据」）。
 *
 * ## ⚠️ 「没取过」与「名单是空的」是两件事
 *
 * ⭐ `ever_swept` 带着这个区别从后端过来，而第一版的后端把两句写进同一句话 ——
 * ⭐ **那正是 `F-218` 的形状穿着散文**：分不清的人会把后者报成前者。
 */

import { useCallback, useMemo, useState } from 'react'

import { DataTable, type Column } from './components/data/DataTable'
import { useResource } from './useResource'
import { getUniverse, type UniverseMembership } from './api'
import { instrumentHref } from './routing'

/** ⭐ **No column below carries a `sortValue`**, and that is the point ⭐ see the header. */
const COLUMNS: Column<UniverseMembership>[] = [
  {
    key: 'name',
    header: '名称',
    render: (row) => (
      <a href={instrumentHref(row.market, row.code)} className="text-navy hover:underline">
        {row.name}
      </a>
    ),
  },
  { key: 'code', header: '代码', render: (row) => <span className="num">{row.code}</span> },
  { key: 'market', header: '市场', render: (row) => row.market.toUpperCase() },
  {
    key: 'first_observed_on',
    header: '第一次观察到',
    render: (row) => <span className="num">{row.first_observed_on}</span>,
  },
  {
    key: 'last_observed_on',
    header: '最后一次观察到',
    render: (row) => <span className="num">{row.last_observed_on}</span>,
  },
]

export default function UniversePage() {
  const [q, setQ] = useState('')
  const [applied, setApplied] = useState('')

  const fetcher = useCallback(
    () => getUniverse(applied === '' ? undefined : applied),
    [applied],
  )
  const describe = useCallback(
    (cause: unknown) => (cause instanceof Error ? cause.message : String(cause)),
    [],
  )
  const { data, error, loading, reload } = useResource(fetcher, [applied], describe)

  const freshness = data?.freshness
  const members = useMemo(() => data?.members ?? [], [data])

  return (
    <div className="px-4 py-3">
      <div className="flex items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="type-meta text-ink-faint">
            按代码或名称找 ⭐ 这一页不排序、不打分，也不会告诉你该看哪几只
          </span>
          <input
            className="type-prose border-b border-rule bg-transparent"
            data-testid="universe-search"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') setApplied(q)
            }}
            placeholder="例如 600000 或 银行"
          />
        </label>
        <button
          type="button"
          className="type-prose"
          data-testid="universe-search-go"
          onClick={() => setApplied(q)}
        >
          查找
        </button>
      </div>

      {/* ⭐⭐ The freshness line. `grid_point` is a fact from the server; the sentence is
          ours, and it is on screen because a roster that does not say how old it is is
          `data-sources.md:137`'s 僵尸报价 in another costume. */}
      {freshness !== undefined && freshness.ever_swept ? (
        <p className="type-prose mt-3 text-ink-soft" data-testid="universe-freshness">
          名单是 <span className="num text-ink">{freshness.latest_grid_point}</span> 那天的，
          共 <span className="num text-ink">{freshness.members}</span> 只，来源{' '}
          <span className="num text-ink">{freshness.source}</span>。
          <span className="text-ink-faint">
            {' '}
            成分名单每周一入库，所以这里的「当前」是那个周一的名单，至多落后七天 ——
            这不是故障，也不是过期的数据，是这个源能给的分辨率。
          </span>
        </p>
      ) : null}

      {loading ? (
        <div className="px-0 py-3" data-testid="universe-loading">
          <p className="type-prose text-ink-faint">读取中…</p>
        </div>
      ) : null}

      {error !== null ? (
        <div className="mt-3 border-l-2 border-l-[color:var(--color-up)] px-4 py-2">
          <p className="type-prose text-[color:var(--color-up)]">{error}</p>
          <p className="type-prose text-ink-soft">
            取不到的时候这一行会写明原因 ⭐ **它不会静默显示成「名单是空的」。**
          </p>
        </div>
      ) : null}

      {/* ⭐ `ever_swept` false gets its own sentence ⭐ **and it is not 「暂无数据」** ⭐
          because 「我们从来没取过」 and 「我们取了、名单是空的」 are different facts. */}
      {!loading && error === null && freshness !== undefined && !freshness.ever_swept ? (
        <p className="mt-3 type-prose text-ink-soft" data-testid="universe-never-swept">
          我们还没有取过这个指数的成分名单 —— 下面没有内容，⭐ 而这不是「名单是空的」。
        </p>
      ) : null}

      {!loading && error === null && freshness?.ever_swept === true && members.length === 0 ? (
        <p className="mt-3 type-prose text-ink-soft" data-testid="universe-empty">
          {applied === ''
            ? `名单是空的 ⭐ 而成分名单任何一天都有约 300 只 —— 所以这更像是取数出了问题，而不是指数空了。`
            : `没有一只符合「${applied}」。`}
        </p>
      ) : null}

      {members.length > 0 ? (
        <div className="mt-3">
          <DataTable<UniverseMembership>
            columns={COLUMNS}
            rows={members}
            rowKey={(row) => `${row.market}:${row.code}`}
            dense
          />
        </div>
      ) : null}

      <div className="mt-4">
        <button type="button" className="type-prose" data-testid="universe-reload" onClick={reload}>
          重新读取
        </button>
      </div>

      {/* ⭐⭐ The boundary, in the same place `PoolPage.tsx:574-580` keeps its own. ⭐ The
          repository's position is that a boundary the reader cannot see is not a
          boundary, and `pool.spec.ts:77` asserts that line is present. */}
      <footer className="mt-6 border-t border-rule px-0 pt-3 type-meta text-ink-faint">
        这一页只显示事实：这只票什么时候在沪深300 的名单里、什么时候不在，
        以及我们知道的名单有多旧。
        <span className="text-ink-soft"> 它不排序、不打分，也不告诉你该看哪几只。</span>
        <br />
        名单来自数据源的**每周一批**入库 ⭐ **所以「当前」是那个周一，不是打开页面的那一天。**
      </footer>
    </div>
  )
}