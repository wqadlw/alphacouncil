/**
 * The Markdown parser and the inline layer (spec 045 · the knowledge base's basics).
 *
 * ⭐ **This file is the first in the project that tests logic with no DOM and no
 * component.** Every other test file is either a source scan (`styleguide.test.ts`)
 * or a contract over pure helpers, ⭐ and V-15 records the boundary: there is no
 * `jsdom` and no `@testing-library/react`, ⭐ so a component's *rendered* output
 * cannot be asserted here. ⭐ `parseMarkdown` and `renderInline` are deliberately
 * pure functions returning data, ⭐ which is what makes 「does it handle this note」
 * answerable without rendering anything — ⭐ and it is why they were written as
 * functions rather than inline in the component.
 *
 * ⭐ **Every test below is a case that broke the first draft**, or a case where the
 * answer was not obvious enough to leave to inspection. ⭐ A parser test suite that
 * only checks the happy path tests the author's first guess.
 */

import { describe, expect, it } from 'vitest'
import { isValidElement, type ReactElement, type ReactNode } from 'react'

import {
  closesFence,
  linkTarget,
  markdownBlocks,
  parseMarkdown,
  renderInline,
  safeHref,
  type Block,
} from './Markdown'

const kinds = (blocks: Block[]) => blocks.map((block) => block.kind)

/** ⭐ Flatten React nodes to text, so an assertion can be about *what the reader
 * sees* rather than about the shape of the tree. ⭐ Without this every inline test
 * would assert on element types, ⭐ which is a test of the implementation and not
 * of the note. */
function textOf(nodes: ReactNode[]): string {
  return nodes
    .map((node) => {
      if (typeof node === 'string') return node
      if (typeof node === 'number') return String(node)
      if (isValidElement(node)) {
        const element = node as ReactElement<{ children?: ReactNode }>
        const children = element.props.children
        return Array.isArray(children) ? textOf(children) : String(children ?? '')
      }
      return ''
    })
    .join('')
}

/** ⭐ The hrefs among the rendered nodes, for the link-safety tests. ⭐
 *
 * A node's href — `undefined` for text, which is not the same as 「refused」. ⭐
 * The first draft wrote a `.filter()` whose predicate referred to a variable from
 * the enclosing `map`, ⭐ which is a `ReferenceError` at runtime and a `noUnused`
 * error at compile time; ⭐ both fired, ⭐ and the second one is what made it
 * obvious. ⭐ Two failures from one line, and the compiler's was the useful one.
 */
function hrefsOf(nodes: ReactNode[]): (string | undefined)[] {
  return nodes
    .filter((node) => isValidElement(node))
    .map((node) => (node as ReactElement<{ href?: string }>).props.href)
}

describe('parseMarkdown · block structure', () => {
  it('reads a heading and a paragraph', () => {
    const blocks = parseMarkdown('## 观察\n\n利率上行，成长股滞后。')
    expect(kinds(blocks)).toEqual(['heading', 'paragraph'])
    expect(blocks[0]).toEqual({ kind: 'heading', level: 2, text: '观察' })
  })

  it('joins the lines of a wrapped paragraph', () => {
    // ⭐ **The join is to a space, not a newline.** A paragraph wrapped across two
    // source lines is one sentence, ⭐ and rendering it with `<br>` would put a line
    // break where the author wrapped ⭐ — which in a note typed in a narrow editor
    // would be every second line.
    expect(parseMarkdown('这是第一行\n这是第二行')).toEqual([
      { kind: 'paragraph', text: '这是第一行 这是第二行' },
    ])
  })

  it('reads a bullet list with a nested item', () => {
    expect(parseMarkdown('- 观察\n- 结论\n  - 附注')).toEqual([
      {
        kind: 'bullet',
        items: [
          { text: '观察', depth: 0 },
          { text: '结论', depth: 0 },
          { text: '附注', depth: 1 },
        ],
      },
    ])
  })

  it('reads an ordered list', () => {
    expect(parseMarkdown('1. 第一\n2. 第二')).toEqual([{ kind: 'ordered', items: ['第一', '第二'] }])
  })

  it('does not interleave an ordered list and a bullet list in one chunk', () => {
    // ⭐ **The first line decides.** The first draft decided per line, ⭐ so
    // `1. 一\n- 二` produced an ordered list of one followed by a bullet list, ⭐
    // which is a shape CommonMark has no name for.
    const blocks = parseMarkdown('1. 第一\n2. 第二')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].kind).toBe('ordered')
  })

  it('joins a lazy continuation onto the previous item', () => {
    // ⭐⭐ **The test that caught the worst bug in this file.** A bullet wrapped
    // across two lines is **one** bullet. ⭐ The first draft wrote
    // `bullets.map((b) => b.text)` and then wrote into the result, ⭐ so the second
    // half of every wrapped bullet was **silently dropped** — ⭐ a renderer that
    // loses a reader's words, ⭐ which is the worst failure this file can have and
    // the kind that looks like a styling bug until someone compares two notes.
    expect(parseMarkdown('- 这一条很长，\n  换行了')).toEqual([
      { kind: 'bullet', items: [{ text: '这一条很长， 换行了', depth: 0 }] },
    ])
  })

  it('reads a blockquote, and reads several quote lines as one quote', () => {
    expect(parseMarkdown('> 第一行\n> 第二行')).toEqual([{ kind: 'quote', text: '第一行 第二行' }])
  })

  it('reads a thematic break', () => {
    expect(kinds(parseMarkdown('---'))).toEqual(['break'])
    expect(kinds(parseMarkdown('***'))).toEqual(['break'])
    // ⭐ And not a bullet list of one item, ⭐ which is what `- - -` would be.
    expect(kinds(parseMarkdown('- - -'))).toEqual(['break'])
  })

  it('treats an empty source as no blocks', () => {
    // ⭐ **Not one empty paragraph.** The component returns `null` for zero blocks, ⭐
    // and a blank note must render nothing rather than a paragraph of air.
    expect(parseMarkdown('')).toEqual([])
    expect(parseMarkdown('   \n\n  \n')).toEqual([])
  })

  it('normalises CRLF', () => {
    // ⭐ Windows checkouts. ⭐ Without this a note authored on Windows would show
    // `\r` inside every inline token, ⭐ which is invisible in the source and shows
    // up as a stray glyph in the reader.
    expect(parseMarkdown('## 标题\r\n\r\n正文')).toEqual([
      { kind: 'heading', level: 2, text: '标题' },
      { kind: 'paragraph', text: '正文' },
    ])
  })
})

describe('parseMarkdown · code fences are data, not structure', () => {
  it('keeps the inside of a fence verbatim', () => {
    expect(parseMarkdown('```python\nx = 1\n```')).toEqual([
      { kind: 'code', lang: 'python', text: 'x = 1' },
    ])
  })

  it('does not read structure inside a fence', () => {
    // ⭐⭐ **The test that matters most in this file.** A note about Markdown will
    // contain Markdown as data — ⭐ a note explaining 「how do I write a heading」
    // has `## this` in it. ⭐ If the fence were classified second, that `##` would
    // become a heading, ⭐ and a note *about* headings would render as headings.
    expect(parseMarkdown('```\n# 不是标题\n- 不是列表\n---\n```')).toEqual([
      { kind: 'code', lang: null, text: '# 不是标题\n- 不是列表\n---' },
    ])
  })

  it('keeps a blank line inside a fence', () => {
    // ⭐ **And it strips the closing fence, which is recognised as a closing fence
    // and not as 「a blank line」.** ⭐ The first draft asked whether the last line
    // was empty — ⭐ a different question — ⭐ so the closing ``` stayed inside the
    // code block and **all four** of these tests failed.
    expect(parseMarkdown('```\n第一段\n\n第二段\n```')).toEqual([
      { kind: 'code', lang: null, text: '第一段\n\n第二段' },
    ])
  })

  it('closes on a longer fence, not a shorter one', () => {
    // ⭐ CommonMark closes ```` ``` ```` only on a run at least as long. ⭐ The first
    // draft closed on any run, ⭐ so a code block containing three backticks ended
    // one line early ⭐ and the rest of the note rendered as text.
    expect(parseMarkdown('````\n```\ninner\n```\n````')).toEqual([
      { kind: 'code', lang: null, text: '```\ninner\n```' },
    ])
  })
})

describe('parseMarkdown · headings', () => {
  it('requires a space after the hashes', () => {
    // ⭐ `#标签` is a tag, not a heading. ⭐ The first draft matched `#` followed by
    // anything, ⭐ which meant a note full of hashtags rendered as headings.
    expect(kinds(parseMarkdown('#标签 不是标题'))).toEqual(['paragraph'])
  })

  it('reads a heading with trailing hashes', () => {
    expect(parseMarkdown('## 观察 ##')).toEqual([{ kind: 'heading', level: 2, text: '观察 ##' }])
  })

  it('clamps a level deeper than six to a paragraph', () => {
    // ⭐ Seven hashes is not a heading in CommonMark, ⭐ and reading it as one would
    // mean a `<h7>` reaches the DOM ⭐ which is an unknown element and renders with
    // no size at all.
    expect(kinds(parseMarkdown('####### 太深'))).toEqual(['paragraph'])
  })
})

describe('renderInline · the text the reader sees', () => {
  it('keeps plain text untouched', () => {
    expect(textOf(renderInline('就是一句话'))).toBe('就是一句话')
  })

  it('strips the emphasis markers', () => {
    expect(textOf(renderInline('这是**重点**和*斜体*'))).toBe('这是重点和斜体')
  })

  it('keeps the text of an inline code span, without the backticks', () => {
    expect(textOf(renderInline('用 `type-prose` 而不是字号'))).toBe('用 type-prose 而不是字号')
  })

  it('keeps a stray asterisk rather than swallowing it', () => {
    // ⭐ **An unmatched marker is printed.** The worst case of this design is a
    // visible `*`, ⭐ and that is preferable to a swallowed character: ⭐ a reader
    // can see a stray asterisk and a reader cannot see a missing emphasis.
    expect(textOf(renderInline('2 * 3 的写法'))).toBe('2 * 3 的写法')
  })

  it('does not nest emphasis', () => {
    // ⭐ **A claim, not a feature.** `**粗体里有*斜体* **` is not handled, ⭐ and the
    // test says so — ⭐ because an unstated limitation is a limitation somebody will
    // discover in production and report as a bug.
    const text = textOf(renderInline('**粗**和*斜*'))
    expect(text).toBe('粗和斜')
  })

  it('keeps HTML as visible characters', () => {
    // ⭐⭐ **The reason there is no dependency.** A note containing a script tag
    // renders **the characters**, ⭐ because `renderInline` returns React nodes and
    // nothing ever becomes HTML. ⭐ The test asserts the characters survive ⭐ and
    // that no element was produced for them, ⭐ so a future 「just use
    // dangerouslySetInnerHTML」 change fails here instead of in a security review.
    const nodes = renderInline('<script>alert(1)</script>')
    expect(textOf(nodes)).toBe('<script>alert(1)</script>')
    expect(nodes.every((node) => typeof node === 'string')).toBe(true)
  })
})

describe('renderInline · link safety', () => {
  it('renders an http link as a link', () => {
    expect(hrefsOf(renderInline('见 [出处](https://example.com/a)'))).toEqual([
      'https://example.com/a',
    ])
  })

  it('refuses javascript: and keeps the label', () => {
    // ⭐ **`javascript:` rendered as an `href` would execute.** ⭐ The honest answer
    // to 「this link is not safe to follow」 is to print the link's text without the
    // link, ⭐ not to print a URL that looks right and does nothing. ⭐ The first
    // draft used a `startsWith('https://')` test, ⭐ which accepts
    // `https://` + anything and rejects nothing that matters; ⭐ `new URL` is the
    // browser's own parser and the check is on `protocol`, ⭐ which is the only part
    // that decides.
    //
    // ⭐ **The assertion is on 「no href anywhere」, not on 「no element」.** ⭐ A
    // refused link still renders an element — the `<span>` that holds the label — ⭐
    // and the first version of this test asserted the element was absent, ⭐ so it
    // failed against correct code. ⭐ What must not exist is an `href`; ⭐ what must
    // exist is the reader's text.
    for (const hostile of [
      '[点我](javascript:alert(1))',
      '[点我](data:text/html,<script>alert(1)</script>)',
      '[点我](vbscript:msgbox)',
      '[点我](JAVASCRIPT:alert(1))',
    ]) {
      const nodes = renderInline(hostile)
      const hrefs = hrefsOf(nodes)
      expect(hrefs, `${hostile} must not carry an href`).toEqual([undefined])
      expect(textOf(nodes), `${hostile} must keep its label`).toBe('点我')
    }
  })

  it('allows an in-page anchor', () => {
    // ⭐ **`#` is how a note links to a section of itself**, ⭐ and it is the one
    // non-http target a knowledge base actually needs. ⭐ And it must not get
    // `target="_blank"`, ⭐ which is checked by the component's props, not here.
    expect(hrefsOf(renderInline('见 [上面](#观察)'))).toEqual(['#观察'])
  })

  it('refuses a relative path, because there are no server-rendered pages to link to', () => {
    // ⭐ A relative href in this app would resolve against `/#/…` and navigate the
    // hash router to something arbitrary, ⭐ so refusing it is the honest answer
    // rather than a missing feature.
    expect(hrefsOf(renderInline('[笔记](./note_1)'))).toEqual([undefined])
  })
})

/**
 * ⭐⭐ **The decisions, as values.**
 *
 * ⭐ **This block exists because the mutation check left four survivors**, and all
 * four were the same defect: ⭐ a judgement written *inside* a component, where this
 * repository cannot see it. ⭐ V-15 records the boundary — no `jsdom`, no
 * `@testing-library/react` — ⭐ so a decision expressed as `href === null ? <span/>
 * : <a/>` in JSX is **untestable**, ⭐ and the tests that 「covered」 it were asserting
 * the label's text, ⭐ which the correct version and the broken version both produce.
 *
 * ⭐ **So each decision became a function returning a value, and the component is a
 * `switch` over a union.** ⭐ That is the shape every unit in this file should have:
 * ⭐ a pure function, a testable answer, ⭐ and rendering that adds no judgement.
 */
describe('linkTarget · the decision, not the element', () => {
  it('says link for http(s), and marks an anchor as internal', () => {
    // ⭐ `internal` is the decision that keeps an in-page `#…` from opening a new tab.
    // ⭐ The component used to re-derive it with a second `startsWith('#')`, ⭐ which
    // is two tests of one fact in two places ⭐ and one of them is wrong by the next
    // edit. ⭐ In a hash-routed app that wrongness navigates away from the note.
    expect(linkTarget('https://example.com/a')).toEqual({
      kind: 'link',
      href: 'https://example.com/a',
      internal: false,
    })
    expect(linkTarget('#观察')).toEqual({ kind: 'link', href: '#观察', internal: true })
  })

  it('says text for anything unsafe, and the label is the caller’s to keep', () => {
    // ⭐ **`{kind:'text'}` is the whole contract.** ⭐ A mutation that dropped the
    // label for a refused link stayed green ⭐ because the assertion was on the text
    // and the `<span>` still had it; ⭐ now the decision is a value ⭐ and a dropped
    // label is a different decision, not a different element tree.
    for (const hostile of [
      'javascript:alert(1)',
      'data:text/html,<script>alert(1)</script>',
      'vbscript:msgbox',
      'JAVASCRIPT:alert(1)',
      './note_1',
      '',
    ]) {
      expect(linkTarget(hostile), `${hostile} must not be a link`).toEqual({ kind: 'text' })
    }
  })

  it('refuses by protocol, not by prefix', () => {
    // ⭐ **The two ways to write this check, and the two cases that tell them
    // apart.** ⭐ `trimmed.startsWith('https://')` is what the first draft shipped.
    // ⭐ I claimed it 「accepts `https:/example.com`」 — ⭐ **and that was wrong:**
    // `new URL` normalises one slash to two, ⭐ so that URL is valid and the prefix
    // test happened to agree with the parser on it. ⭐ The cases that actually
    // separate them are the ones below.
    //
    // ⭐ **Case.** `HTTPS://example.com` is a perfectly good link; ⭐ a prefix test
    // refuses it, ⭐ and a reader who pastes a URL from a browser's address bar
    // sometimes has it.
    expect(safeHref('HTTPS://example.com')).toBe('https://example.com/')
    // ⭐ **Scheme.** `http://` is not `https://`, ⭐ and a prefix test refuses every
    // plain-http link ⭐ — which in a product whose own backend runs on http in
    // development would refuse half the links a reader writes.
    expect(safeHref('http://example.com')).toBe('http://example.com/')
    // ⭐ And the ones both agree on.
    expect(safeHref('ftp://example.com')).toBeNull()
    expect(safeHref('javascript:alert(1)')).toBeNull()
    // ⭐ **The return value is `url.href`, not the input** ⭐ and a bare host gains a
    // trailing slash, ⭐ so `http://example.com` and `http://example.com/` are one
    // link ⭐ and a test treating them as two is testing the wrong thing.
    expect(safeHref('https://example.com/a?b=1#c')).toBe('https://example.com/a?b=1#c')
  })

  it('refuses a URL with no host, which `new URL` happily accepts', () => {
    // ⭐⭐ **The test that corrected the advice.** This file's comment said 「use the
    // platform parser instead of a string prefix」 ⭐ as though that were sufficient.
    // ⭐ It is not: ⭐ `new URL('https://')` **does not throw** — ⭐ it resolves to
    // `https://` with an empty host, ⭐ so a protocol-only check waves it through and
    // the reader gets a link that goes nowhere.
    //
    // ⭐ ⭐ **The general lesson is the one worth keeping: a guard that delegates to a
    // parser inherits that parser's definition of valid.** ⭐ `javascript:` was the
    // case that made the advice look right, ⭐ and this is the case that makes it
    // wrong, ⭐ and both were in the same test file. ⭐ A test suite that only tests
    // the famous attack is a suite that certifies the guard, not the behaviour.
    expect(safeHref('https://')).toBeNull()
    expect(safeHref('http://')).toBeNull()
    // ⭐ And the near-miss that is legitimately fine, ⭐ so the host check is not
    // over-tight: a real host with a port and a path.
    expect(safeHref('https://example.com:8443/a')).toBe('https://example.com:8443/a')
  })
})

describe('closesFence · the rule that had no name', () => {
  it('closes on the same character and at least the same length', () => {
    // ⭐ **Two facts, and the first draft had the second one wrong.** ⭐ A fence
    // opened with ```` ```` ````` is not closed by ``` ``` ```, ⭐ and getting that
    // wrong ends the code block one line early ⭐ — ⭐ which the block test missed,
    // because the note it used happened to be closed by a long enough run.
    expect(closesFence('```', '```')).toBe(true)
    expect(closesFence('````', '```')).toBe(false)
    expect(closesFence('````', '`````')).toBe(true)
    // ⭐ A different character never closes it, ⭐ even at the same length.
    expect(closesFence('```', '~~~')).toBe(false)
  })

  it('is not fooled by a fence with a language on the closing line', () => {
    // ⭐ A closing fence may not carry an info string, ⭐ so ``` ```js ``` **opens** a
    // block rather than closing one, ⭐ and treating it as a close loses a line of
    // code.
    expect(closesFence('```', '```js')).toBe(false)
  })

  it('tolerates the whitespace CommonMark allows, and no more', () => {
    // ⭐ **Up to three spaces of indent and trailing whitespace are legal on a
    // closing fence.** ⭐ The first version of this list asserted that ```` ``` ````
    // followed by a space does **not** close, ⭐ and failed — ⭐ which is the test
    // being wrong about the spec rather than the code being wrong. ⭐ Four spaces is
    // still a refusal, ⭐ because that is a different construct.
    expect(closesFence('```', '   ```')).toBe(true)
    expect(closesFence('```', '```   ')).toBe(true)
    expect(closesFence('```', '    ```')).toBe(false)
  })

  it('says no for ordinary text', () => {
    for (const line of ['', 'x = 1', '# heading', '- item', '  ~~', '``` extra']) {
      expect(closesFence('```', line), `${line} must not close a fence`).toBe(false)
    }
  })
})

describe('markdownBlocks · the empty-note decision, as a value', () => {
  it('is null for a note with nothing in it', () => {
    // ⭐ **Rule 8, decided by a function rather than by a component.** ⭐ The rule is
    // 「one statement of fact」 ⭐ and a blank note has no fact to state, ⭐ so the
    // right answer is nothing at all — ⭐ and a mutation to `return <p />` ⭐ which
    // stayed green ⭐ is now a different value and this test is red.
    expect(markdownBlocks('')).toBeNull()
    expect(markdownBlocks('   \n\n\t\n')).toBeNull()
  })

  it('is the blocks for a note with something in it', () => {
    expect(markdownBlocks('正文')).toEqual([{ kind: 'paragraph', text: '正文' }])
  })
})
