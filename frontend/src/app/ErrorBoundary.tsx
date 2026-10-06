import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '../components/ui'

/**
 * The last thing between a rendering bug and a blank window.
 *
 * ## Why this exists
 *
 * Without it, any throw during render unmounts the whole React tree. The reader
 * gets a white window, and the only trace is one line in a console they have never
 * opened. For a local-first application whose entire reason to exist is the
 * reader's own record, "the interface broke" and "the record is gone" look exactly
 * the same from the outside — so the honest thing is to make sure they are not the
 * same thing.
 *
 * ## What it says, and what it must not
 *
 * It states that the page could not be shown and that the record is unaffected.
 * Both are true and the second is the one that matters: a rendering failure never
 * writes to the database, so nothing about the reader's data depends on this
 * component working.
 *
 * ⭐ **It names no provider, no upstream, no health and no cooldown** (红线 8). A
 * failure here is a failure *in this program*, and the sentence has to point at
 * that rather than outward — a reader who sees 「行情源超时」 learns something they
 * cannot act on and concludes their record is at someone else's mercy.
 *
 * ⭐ **It scores nothing and nudges nothing** (红线 11): no count of how often this
 * happened, no "try again later", no suggestion to do anything else. One sentence
 * about what happened, one sentence about what did not, one way out.
 */
interface Props {
  children: ReactNode
}

interface State {
  failed: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  // A class, because this is the one React component that cannot be a function:
  // `getDerivedStateFromError` has no hook equivalent, and the repo's dependency
  // budget (V-07, approved list only) rules out a library.
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Console, not storage and not the network: this is a diagnosis trail for
    // whoever is developing the app, and a crash report that left the machine
    // would be a new copy of the reader's record to look after.
    console.error('这一页没能显示出来', error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="pane-scroll min-h-0 flex-1 px-4 py-6" data-testid="render-failure">
        {/*
          `type-claim`, not `type-page-title`, and V-12 is what made that
          decision rather than taste: the page-title size may appear **once** per
          page, and the shell already spends it on the pane's own heading. A
          failure notice is a claim about what happened, not the title of a
          document — writing it at title size would also have made two things on
          screen compete for the reader's first glance, which is the opposite of
          what a failure notice is for.
        */}
        <h1 className="serif type-claim text-ink">这一页没能显示出来</h1>
        <p className="mt-2 type-prose text-ink">
          是这个程序自己的问题，不是数据取不到。
        </p>
        <p className="mt-1 type-prose text-ink-soft">
          你的记录没有受影响 —— 它们在库里，不在屏幕上。
        </p>
        <div className="mt-3 flex items-center gap-2">
          {/* The repo's own button, not a bare `<button>`. The frontend holds a
              measured property of zero native `<button>` elements, and spec 025
              turned the application vocabulary into that count; a raw element here
              would quietly undo it. */}
          <Button size="sm" onClick={() => window.location.reload()} data-testid="render-failure-reload">
            重新载入
          </Button>
        </div>
      </div>
    )
  }
}
