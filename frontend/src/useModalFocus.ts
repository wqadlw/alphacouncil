/**
 * The three things a modal owes the reader, in one place.
 *
 * ⭐ **This exists because the work was done first and in the wrong file.** Stage D
 * added focus restore, a Tab trap and `inert` to `CommandPalette` because that is
 * where the missing behaviour turned up. ⭐ A Drawer is a modal that arrives from
 * the side and a Popover is a modal that does not steal focus, ⭐ and the plan for
 * both said 「reuse the palette's mechanism」 — ⭐ which, with the mechanism living
 * inside a page-level component, is not reuse but copy-paste with a delay. ⭐ So the
 * three things moved here, and `CommandPalette` now calls this.
 *
 * ⭐ **It is a native listener on the panel, not a `window` listener and not a React
 * `onKeyDown`.** Both of those were tried, in effect, and both are wrong in a way
 * that is invisible until the reader presses Tab:
 *
 * - a `window` listener sees `Tab` only when nothing above it handled the event, ⭐
 *   and a `keydown` on the focused input is handled by React's root listener first
 *   ⇒ **backward Tab would work and forward Tab would silently not**;
 * - a React `onKeyDown` on the panel works, ⭐ but only because the consumer put it
 *   there. ⭐ A hook that returns a handler is a hook that can be forgotten, ⭐ and
 *   forgetting it produces a modal that looks correct and is not.
 *
 * ⭐ `panel.addEventListener` sees the event on the way up, before React's root,
 * regardless of how the panel was written. That is the only placement where
 * 「the trap is installed」 is the same statement as 「the trap runs」.
 */
// ⭐ **Named imports, not `React.useX`.** Every other file in this source tree
// imports from `'react'` by name, ⭐ and `tsc` rejects the UMD global form outright
// (`TS2686`) rather than warning about it. ⭐ Worth one line because the *first*
// draft of this file used `React.useEffect` throughout and the compiler caught it ⭐
// — ⭐ which is the cheapest possible reminder that the style check is `tsc`, not
// review.
import { useEffect, useRef, type RefObject } from 'react'

/** The app shell's id. ⭐ Exported so `AppShellFrame` and a future Drawer agree. */
export const SHELL_ID = 'app-shell'

/**
 * ⭐ The focusable things inside a panel.
 *
 * A query, not a list of refs — the panel's contents are conditional, ⭐ so a
 * hand-maintained array is wrong the moment a row is added or the list is empty.
 * The selector matches what the panels render: ⭐ the palette's footer hints are
 * `<span>`s and must **not** be tab stops, because a hint that takes focus and does
 * nothing is a control that looks broken.
 */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'

export interface ModalFocusOptions {
  /** Whether the modal is on screen. Every effect here is a no-op when false. */
  open: boolean
  /** The modal's own element. ⭐ Must be a ref, not a node: the node does not exist yet. */
  panelRef: RefObject<HTMLElement | null>
  /**
   * ⭐ **What to disable while the modal is open, by id.**
   *
   * ⭐ A modal is not allowed to reach the page behind it, and `inert` is the
   * platform's way to say so. ⭐ It is an `id` and not a ref because the element is
   * the modal's **sibling**, not its parent: a modal inside the subtree it disables
   * freezes itself, ⭐ which is why the palette portals itself into `document.body`
   * first. ⭐ This sentence is a design constraint, not an observation about the DOM.
   */
  inertTargetId?: string
}

/**
 * Record where focus came from, keep Tab inside, and disable the page behind.
 *
 * ⭐ **The restore is scheduled and checked, and both halves are load-bearing.**
 * Restoring synchronously on `open` going false would fight a command that *intends*
 * to move focus elsewhere, ⭐ and restoring to a node that has since unmounted is a
 * silent no-op that looks like a successful restore ⭐ — the reader is dumped on
 * `body` and the code reads as though it worked.
 */
export function useModalFocus({ open, panelRef, inertTargetId = SHELL_ID }: ModalFocusOptions): void {
  const previousFocus = useRef<HTMLElement | null>(null)

  // ⭐ **Recorded on `open`, not in a click handler.** The palette opens by three
  // routes (⌘K, a sidebar button, a page-contributed command) and only one of them
  // is a click. ⭐ A ref set in `onClick` restores to `body` for the other two, ⭐
  // which is the shape of a fix that passes a test and fails in the app.
  useEffect(() => {
    if (!open) return
    previousFocus.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
  }, [open])

  useEffect(() => {
    if (open) return
    const target = previousFocus.current
    if (target === null) return
    const frame = requestAnimationFrame(() => {
      if (target.isConnected) target.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [open])

  // ⭐ **The previous value is restored, not `false`.** Something else may have made
  // the shell inert for its own reasons, ⭐ and a cleanup that hard-codes `false`
  // silently un-disables it.
  useEffect(() => {
    if (!open) return
    const target = document.getElementById(inertTargetId)
    if (target === null) return
    const wasInert = target.inert
    target.inert = true
    return () => {
      target.inert = wasInert
    }
  }, [open, inertTargetId])

  // ⭐ The trap, attached to the panel and re-attached when the panel's contents
  // change shape. An effect with `[open, panelRef]` deps runs once per open, ⭐ and
  // the list of stops is read fresh on every Tab, ⭐ so a filtered list that grows
  // from nothing is trapped correctly without re-subscribing.
  useEffect(() => {
    if (!open) return
    const panel = panelRef.current
    if (panel === null) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const stops = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
      // ⭐ **No stops means no trap to install, and the next Tab would land wherever
      // the browser put it.** Pulling focus to the panel itself is the honest
      // fallback: the reader is still inside the modal, ⭐ which is the promise
      // `aria-modal` makes and the DOM does not enforce.
      if (stops.length === 0) {
        event.preventDefault()
        panel.focus()
        return
      }
      const first = stops[0]
      const last = stops[stops.length - 1]
      const current = document.activeElement

      // ⭐ Outside entirely — the moment after the rows unmount, or a click on the
      // scrim. Pull it in from the end the reader was heading towards.
      if (!(current instanceof HTMLElement) || !panel.contains(current)) {
        event.preventDefault()
        ;(event.shiftKey ? last : first).focus()
        return
      }
      // ⭐ Two conditions, not one: `Tab` on the last stop and `Shift+Tab` on the
      // first are the only two that leave, ⭐ and measuring the wrong one of the
      // pair is the difference between a trap and half a trap. ⭐ Both directions
      // must be pressed **more times than there are stops** to be tested, ⭐ because
      // a panel that happens to sit at the end of the tab order looks correct for
      // exactly `rows` presses while having no trap at all.
      if (!event.shiftKey && current === last) {
        event.preventDefault()
        first.focus()
        return
      }
      if (event.shiftKey && current === first) {
        event.preventDefault()
        last.focus()
      }
    }

    panel.addEventListener('keydown', onKeyDown)
    return () => panel.removeEventListener('keydown', onKeyDown)
  }, [open, panelRef])
}
