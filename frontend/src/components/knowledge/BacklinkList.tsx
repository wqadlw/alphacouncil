/**
 * 「被这些记录引用」—— 知识库像知识库的地方。
 *
 * Authority: `docs/FRONTEND_STYLE_GUIDE.md` §8.2, which names this component and says
 * what it is for: **「知识库像知识库的地方」**.
 *
 * ⭐ **A note is worth more once something else points at it, and a backlink is the only
 * thing on the page that says so.** Every other element in the vault answers 「这是什���」;
 * this one answers 「我说过它吗，别人说过吗」 — which is the question that turns a list of
 * notes into something you can navigate by thinking.
 *
 * ⭐ **It renders titles, and the titles are the reader's own words.** A backlink list
 * showing ids would be a debugging view. Showing bodies would cost the panel
 * proportional to the vault — which is why the endpoint sends `from_note_id` and
 * `title` and nothing else (see `api/routes/notes.py`).
 *
 * ## Why this is a component and not a paragraph
 *
 * ⭐ Because it is **empty most of the time**, and the empty state is the interesting
 * case. A note with nothing pointing at it is not a note with missing data — ⭐ it is a
 * note nobody has thought about again, and saying so is information. The sentence
 * below says that rather than 「暂无反链」, and rule 8 applies: one statement of fact,
 * no 「还没有…」 phrasing, no illustration.
 */

/** ⭐ Mirrors `BacklinkRead` on the wire. Extra keys are rejected server-side. */
export interface Backlink {
  from_note_id: string
  title: string
}

export interface BacklinkListProps {
  backlinks: readonly Backlink[]
  /**
   * ⭐ **Opens the linked note.**
   *
   * ⚠️ **This is a callback, not an `href`, and that is a real limitation rather than
   * a preference.** The vault selects a note with component state — ⭐ the note id is
   * not in the hash — so there is no URL for a backlink to point at. ⭐ The first
   * version of this component took `hrefFor: (id) => string` and the call site passed
   * `undefined as never`, ⭐ which is a promise the component cannot keep and a lie the
   * type checker could not see. Making the vault URL-addressable is the real fix and is
   * **not** in this stage; ⭐ until it is done, the honest control is a button that does
   * what it says, because an `<a>` styled as a link announces as a link, middle-click
   * does nothing, and teaches the reader that this list is broken.
   */
  onSelect: (noteId: string) => void
}

export function BacklinkList({ backlinks, onSelect }: BacklinkListProps) {
  if (backlinks.length === 0) {
    return (
      <p className="type-prose text-ink-soft">
        没有别的记录指向它。这条笔记现在只在你自己的知识里。
      </p>
    )
  }

  return (
    <ul>
      {backlinks.map((backlink) => (
        <li
          key={backlink.from_note_id}
          // ⭐ A 2px left rule, not a bullet or a pill (规则 5). ⭐ And the same
          // `mark` class `RecallView` uses, so a backlink row and a recall row read as
          // two instances of one list rather than as two components.
          className="mark border-b border-[color:var(--color-rule-soft)] border-l-2 border-l-[color:var(--color-navy)] py-1.5"
        >
          <button
            type="button"
            onClick={() => onSelect(backlink.from_note_id)}
            // ⭐ `text-left` because a `button` defaults to `center`, and ⭐ a centred
            // note title in a left-ruled list reads as a heading rather than as
            // something you press.
            className="type-prose block w-full text-left text-navy no-underline hover:underline data-[motion=l1]"
          >
            {backlink.title}
          </button>
        </li>
      ))}
    </ul>
  )
}

/**
 * ⭐ The heading's count, and why it is not a badge.
 *
 * A backlink count is a fact about the list below it, so it belongs in the list's
 * heading — and `nav.spec.ts` asserts the **sidebar** carries no digits, which is a
 * different surface and a different rule. ⭐ It is `type-meta` next to the word rather
 * than a `Badge`: §4 forbids capsules, and a count beside a label is not a status.
 */
export function BacklinkCount({ count }: { count: number }) {
  if (count === 0) return null
  return <span className="num type-meta text-ink-faint">{count} 条引用</span>
}
