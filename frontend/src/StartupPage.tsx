/**
 * The launch screen: one painting, one line, one way in.
 *
 * ⭐ **It is not a route, and that is a decision rather than an omission.**
 * `routing.ts` exists so that "a view is declared in exactly one place" holds, and
 * its header is explicit that the table drives navigation, hash parsing, titles and
 * hrefs. A launch screen is none of those: it has no address, cannot be linked to,
 * Back does not return to it, and it must not appear in the nav — a 「开屏」 row in
 * a sidebar of five working views is a row that does nothing.
 *
 * So it renders **instead of** the shell rather than inside it, and `App` decides
 * when. Putting it in `ROUTES` would have bought a `#/start` URL nothing should be
 * able to reach, at the cost of the one property the table guarantees.
 *
 * ⭐ **It shows once a day, not once a session.** A tool somebody opens twenty
 * times a day cannot put a full-screen anything in front of that twenty times.
 * `launchLogic.ts` keeps the date; ⌘K gets the screen back on demand, and the
 * palette is this product's answer to 「where is that thing」 (see
 * `AppShellFrame`'s header).
 *
 * ⭐ **The painting keeps its own proportions.** `width`/`height` come from the
 * manifest's measured values so the browser reserves the right box before the JPEG
 * decodes, and `max-width`/`max-height` let it shrink. Nothing crops it. A
 * two-metre hanging scroll and a landscape album leaf are both 30-centimetre
 * objects of the same kind, and cropping one to match the other picks the wrong
 * one.
 *
 * ⭐ **The logic is in `launchLogic.ts`, not here,** because this repository has no
 * `jsdom` and no `@testing-library/react` — `styleguide.test.ts` records that
 * choice — so the decisions are unit-tested there and the rendering is asserted in
 * `e2e/launch.spec.ts`.
 */

import { useEffect } from 'react'
import { SCROLL_MUSEUM, scrollFor, scrollUrlFor } from './art/scroll/manifest'
import { creditLine } from './launchLogic'
import { cn } from './lib/cn'

export interface StartupPageProps {
  /** Called when the reader wants in. The caller records it and navigates. */
  onEnter: () => void
  /** Injected in tests and in `e2e/`; the real page reads the clock. */
  now?: Date
}

export function StartupPage({ onEnter, now }: StartupPageProps) {
  const today = now ?? new Date()
  const scroll = scrollFor(today)
  const src = scrollUrlFor(today)

  // Enter and Space are the two keys this screen has. The button is a link the
  // reader aims at; the keys are for the reader who has finished reading it.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        onEnter()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onEnter])

  return (
    <div className="startup" data-testid="startup" onClick={onEnter} role="presentation">
      <div className="startup-copy">
        {/* ⭐ `serif type-claim-lg`, and this is §2.1's one exception rather than a
            second one: the brand's own name is the only text in the product set in
            the serif face as a *name*. The slogan below it is not. */}
        <h1 className="serif type-claim-lg startup-rise text-ink">AlphaCouncil</h1>

        {/* The slogan, at `type-display` (24/28) — the largest size in the scale —
            and **not** serif, because §2.1 reserves the serif face for what the
            *reader* wrote, and this sentence is about the reader rather than
            written by them. Sans with wide tracking reads as a printed masthead
            rather than a claim, which is what it is. */}
        <p className="type-display startup-rise text-ink-soft">投资是一场修行</p>

        {/* ⭐ The date is `type-meta` and never `num`. `num` is tabular-and-mono for
            **data** — figures that change and must not make a column jitter
            (V-05). A launch screen's date changes once a day and is not data. */}
        <p className="type-meta startup-rise text-ink-faint" data-testid="launch-date">
          {today.toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            weekday: 'long',
          })}
          {`　第 ${scroll.day} / 31 幅`}
        </p>

        <button
          type="button"
          className={cn('type-prose startup-rise startup-enter')}
          onClick={(event) => {
            // The container's `onClick` would also fire, so `onEnter` would run
            // twice for one click — and `onEnter` writes storage and sets state.
            event.stopPropagation()
            onEnter()
          }}
          data-testid="launch-enter"
        >
          进入
        </button>
      </div>

      <div className="startup-wall">
        {/* ⭐ `startup-hang` on the frame, not the image, so the mat and the painting
            settle as one object. `ac-hang` is `scaleY` from the top: a hanging
            scroll comes down off its roller, and a fade would say 「an image
            appeared」 where this says 「an object was hung」. */}
        <figure className="startup-frame startup-hang">
          <img
            src={src}
            alt={`${scroll.artist}《${scroll.title}》，${scroll.date}`}
            width={scroll.width}
            height={scroll.height}
            // ⭐ The largest paint on the app's first screen, with nothing above it.
            // The other 30 paintings are never fetched by a reader who dismisses
            // this screen, which is why they are `import.meta.glob`bed rather than
            // bundled as data URLs.
            fetchPriority="high"
            decoding="async"
            data-testid="launch-art"
            data-day={scroll.day}
          />
        </figure>
        {/* ⭐ Rendered even though CC0 does not require it — see `PROVENANCE.md`.
            The screen's whole subject is 「where did this come from」, so hiding the
            answer in a file nobody opens would be the one dishonest thing on it. */}
        <figcaption className="type-badge startup-credit" data-testid="launch-credit">
          {creditLine(scroll.artist, scroll.date, scroll.title, SCROLL_MUSEUM)}
        </figcaption>
      </div>
    </div>
  )
}
