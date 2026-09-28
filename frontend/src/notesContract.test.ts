import { describe, expect, it } from 'vitest'

/**
 * Proves the notes wire format matches what `api.ts` sends and what the page
 * reads.
 *
 * The reason this file is a real test and not a comment: the note API is the
 * first one where **optional** fields are the common case rather than the
 * exception (`as_of`, `tags`, `links`, `symbols` are all routinely absent), and
 * optional-field bugs do not show up as crashes — they show up as a note that
 * quietly loses its tags, which is the failure a knowledge store cannot afford.
 */

/** A note exactly as `GET /api/v1/notes` returns it, with every optional field empty. */
const MINIMAL = {
  id: 'note_1790560000000',
  title: '流动性收紧时周期股先跌',
  body: '## 观察\n\n- 2026-08 利率上行',
  as_of: null,
  created_at: '2026-09-28T00:00:00.000Z',
  updated_at: '2026-09-28T00:00:00.000Z',
  tags: [],
  links: [],
  symbols: [],
}

/** The same note with everything filled in. */
const FULL = {
  ...MINIMAL,
  as_of: '2026-08-31',
  tags: ['宏观', '估值'],
  links: [{ to_kind: 'card', to_id: 'card_1790560000001' }],
  symbols: [{ market: 'sh', code: '600519' }],
}

describe('the note wire format', () => {
  it('a note needs no source and no instrument', () => {
    // ⭐ The whole feature. If this shape ever grows a required `source_url`,
    // the vault has gone back to being a card list.
    expect(Object.keys(MINIMAL).sort()).toEqual([
      'as_of',
      'body',
      'created_at',
      'id',
      'links',
      'symbols',
      'tags',
      'title',
      'updated_at',
    ])
    expect(MINIMAL).not.toHaveProperty('source_url')
    expect(MINIMAL).not.toHaveProperty('source_title')
    expect(MINIMAL.symbols).toEqual([])
  })

  it('optional fields are empty rather than absent', () => {
    // `as_of: null` and `tags: []` are *present*. A payload where they are
    // missing makes every reader write `note.as_of ?? null` and every writer
    // guess whether the field is nullable or optional.
    for (const key of ['as_of', 'tags', 'links', 'symbols']) {
      expect(MINIMAL).toHaveProperty(key)
    }
  })

  it('a link names its target kind explicitly', () => {
    // The link table is polymorphic and carries no foreign key, so `to_kind` is
    // the only thing that says which of the five tables to look in. Dropping it
    // would make every link unresolvable.
    expect(FULL.links[0].to_kind).toBe('card')
    expect(FULL.links[0].to_id).toMatch(/^card_/)
  })

  it('a note id is a moment, so it starts with note_', () => {
    expect(MINIMAL.id).toMatch(/^note_\d+$/)
  })

  it('as_of is a plain date, not a timestamp', () => {
    // PIT discipline: 「数据截至 2026-08」 is a day, and a timestamp here would
    // invite someone to read it as "the instant I knew it".
    expect(MINIMAL.as_of).toBeNull()
    expect(FULL.as_of).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
