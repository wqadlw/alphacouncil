/**
 * `DataTable` — the dense list, which is the reason a knowledge program is not a
 * stack of cards.
 *
 * Spec'd in `AlphaCouncil-前端资源与打磨规格.md` §4.3. Every line of that row is a
 * requirement, and three of them exist because of how badly a table goes wrong
 * without them:
 *
 * - **数字列右对齐 + `tabular-nums`.** Proportional digits mean a column of
 *   numbers changes width as the values change, and the reader's eye loses the
 *   row. This is the single highest-value line in the file.
 * - **表头全大写 11px + `letter-spacing: 0.06em`.** A header set in body size
 *   competes with the data it labels; smaller and tracked-out reads as a label.
 * - **0.5px 全表格线.** Hairlines instead of zebra striping and instead of shadow
 *   (§3.2, rule 4). Zebra striping is a spreadsheet, and this is a report.
 *
 * `⌨` is in a column header when a column can be sorted. It is a real character
 * rather than an icon because it is punctuation, and §5 forbids emoji as
 * functional icons but says nothing about text — and at 11px an icon is noisier
 * than a caret.
 */

import { useMemo, useState, type ReactNode } from 'react'
import { cn } from '../../lib/cn'

export interface Column<T> {
  key: string
  header: string
  /** Right-align and set tabular figures. Correct for anything numeric. */
  numeric?: boolean
  /** Supply a sort key; omit to make the column unsortable. */
  sortValue?: (row: T) => string | number
  width?: string
  render: (row: T) => ReactNode
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey,
  empty,
  dense,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  onRowClick?: (row: T) => void
  selectedKey?: string | null
  empty?: ReactNode
  /** 32px rows instead of 40. For logs and queues where volume beats comfort. */
  dense?: boolean
}) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const column = columns.find((c) => c.key === sort.key)
    if (!column?.sortValue) return rows
    const value = column.sortValue
    // `localeCompare` with numeric handling, so `600519` sorts after `60051`
    // rather than beside it. A ticker column sorted as text is a bug you feel
    // the first time a six-digit code follows a five-digit one.
    return [...rows].sort((a, b) => {
      const left = value(a)
      const right = value(b)
      if (typeof left === 'number' && typeof right === 'number') {
        return (left - right) * sort.dir
      }
      return String(left).localeCompare(String(right), 'zh-Hans-CN', { numeric: true }) * sort.dir
    })
  }, [rows, sort, columns])

  const toggle = (key: string) =>
    setSort((current) =>
      current?.key === key ? (current.dir === 1 ? { key, dir: -1 } : null) : { key, dir: 1 },
    )

  if (rows.length === 0 && empty) return <>{empty}</>

  return (
    <table className="w-full border-collapse" data-testid="data-table">
      <thead>
        <tr className="border-b border-rule">
          {columns.map((column) => (
            <th
              key={column.key}
              style={column.width ? { width: column.width } : undefined}
              className={cn(
                'type-meta caps px-3 py-1.5 font-normal text-ink-faint',
                column.numeric ? 'text-right' : 'text-left',
              )}
 >
              {column.sortValue ? (
                <button
                  type="button"
                  onClick={() => toggle(column.key)}
                  className="inline-flex items-center gap-0.5 data-[motion=l1] hover:text-ink"
                  data-testid={`sort-${column.key}`}
                  aria-sort={sort?.key === column.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}
 >
                  {column.header}
                  {/* A caret is punctuation here, not an icon (§5 forbids emoji
                      as functional icons, but says nothing about text). `↕` marks
"sortable"; the active column shows its actual direction.

                      The first draft used `⌨` for the unsorted state, which was a
                      guess that turned out to be unreadable in context — at 9px in
                      a table header it reads as a keyboard shortcut, and a reader
                      has no way to guess it means "click to sort". `↕` is the
                      conventional mark for exactly this.

                      ⭐ And 9px is now `.type-badge` — 11px, §2.2's smallest row. 9
                      was below *every* floor in the table, including the 11px badge
                      row, so no class could describe it and `V-12` caught it. A caret
                      one pixel taller in a column header costs nothing and stops the
                      product having a size the style guide has never approved. */}
                  <span className="type-badge">
                    {sort?.key === column.key ? (sort.dir === 1 ? '▲' : '▼') : '↕'}
                  </span>
                </button>
              ) : (
                column.header
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => {
          const key = rowKey(row)
          const selected = selectedKey === key
          return (
            <tr
              key={key}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === 'Enter') onRowClick(row)
                    }
                  : undefined
              }
              // Selection is a 2px left rule, matching the command palette: a
              // cursor, not a highlight.
              className={cn(
                'border-b border-[color:var(--color-rule-soft)] border-l-2 data-[motion=l1]',
                dense ? 'h-8' : 'h-10',
                selected
                  ? 'border-l-[color:var(--color-brass)] bg-paper-soft'
                  : 'border-l-transparent hover:bg-paper-soft',
                onRowClick && 'cursor-pointer',
              )}
              data-testid="data-row"
              data-selected={selected ? 'true' : 'false'}
 >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn(
                    // ⭐ §2.2's 表格单元格 row: 13 / 18. The cells previously took
                    // the table's `type-prose` (13/20) by inheritance, which is the
                    // **prose** row — a cell is legible text, not a paragraph, and
                    // §2.2 keeps them apart for exactly this reason. §8.2's 行高
                    // 32/40 lives on the `<tr>` above, so this is only the measure.
                    'type-cell px-3 align-middle',
                    column.numeric ? 'num text-right text-ink' : 'text-ink-soft',
                  )}
 >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
