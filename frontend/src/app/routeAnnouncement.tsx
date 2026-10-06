import { useEffect, useRef } from 'react'

/**
 * Move the reader's focus where the page actually is, once per route.
 *
 * ## Why this exists
 *
 * The shell is persistent, so a route change replaces the content *inside* it and
 * leaves the browser's focus exactly where it was — usually on the sidebar link
 * that was just activated. A keyboard reader who navigates this way is therefore
 * still "on" the navigation after the page has changed, and their next Tab walks
 * the sidebar again rather than into the content they asked for. A screen reader
 * gets nothing at all: the document changed and nothing said so.
 *
 * Focusing the landmark says both things at once — where the reader is, and that
 * something moved.
 *
 * ## Not on the first render, and that is the load-bearing detail
 *
 * On arrival the browser has already put focus at the top of the document, which is
 * the correct place for it: the reader's next Tab reaches the skip link, and that is
 * the one thing the skip link is for. Moving focus to the landmark first would put
 * the reader *past* it, so the link would exist and be unreachable — measured, not
 * assumed: a first Tab landed after `<main>` and the skip link never received focus.
 *
 * From the second route onwards focus does move, because by then focus is sitting
 * on the control that caused the change — the sidebar link — and leaving it there
 * is what makes the next Tab re-walk the navigation.
 *
 * ## The version this replaced, and why it went
 *
 * The first attempt added a visually hidden `aria-live="polite"` region carrying
 * the page title, so a route change would be announced without taking focus. It
 * was measured and it was wrong twice over:
 *
 * 1. The region's text duplicated the `<h1>` that was already in the document, so
 *    a screen reader heard the page title twice. Three existing E2E tests failed on
 *    it, and they were right to: `getByRole('heading', { name })` resolved to two
 *    elements. A duplicated announcement is noise, and a live region that is noisy
 *    is a live region assistive technology learns to ignore.
 * 2. Announcing the title required the title to be inside the region, which is
 *    what made it collide in the first place.
 *
 * So the announcement is the focus move, and there is no live region.
 *
 * ## The palette
 *
 * It does not run while the command palette is open: `useModalFocus` owns focus
 * for as long as the palette is up and restores it on close, and taking focus back
 * mid-gesture would fight that. The palette's own tests cover the restore.
 */
export function useRouteFocus(name: string, ready: boolean, suspended = false) {
  const previous = useRef<string | null>(null)

  useEffect(() => {
    if (!ready || suspended) return
    const isFirst = previous.current === null
    if (previous.current === name) return
    previous.current = name

    const main = document.getElementById('main')
    if (!main) return
    // On the very first render focus is already at the top of the document, which
    // is where the skip link needs it to be. Moving it would put the reader past
    // the link that exists for them.
    if (isFirst) return
    // `preventScroll`, because the panes keep their own scroll position and a
    // jump back to the top of the document on every navigation is its own small
    // wrongness. The content the reader asked for is where they are looking.
    main.focus({ preventScroll: true })
  }, [name, ready, suspended])
}
