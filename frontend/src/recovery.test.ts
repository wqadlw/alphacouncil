import { describe, expect, it } from 'vitest'
import {
  DEFAULT_ANNUAL_RATE,
  DEPTHS,
  depthsIncluding,
  formatGain,
  formatRate,
  formatYears,
  gainNeeded,
  isOwnDepth,
  yearsToRecover,
} from './recovery'

describe('gainNeeded', () => {
  it('states the asymmetry: half gone, double needed', () => {
    // The single most useful sentence in this file. A reader who believes a 50%
    // loss needs a 50% gain is not being careless — they are being human, and
    // the number is the correction.
    expect(gainNeeded(0.5)).toBe(1)
  })

  it('grows faster than the loss does', () => {
    expect(gainNeeded(0.9)).toBeCloseTo(9, 10)
    expect(gainNeeded(0.3)).toBeCloseTo(0.428571, 5)
  })

  it('asks for nothing when nothing was lost', () => {
    expect(gainNeeded(0)).toBe(0)
    expect(gainNeeded(-0.1)).toBe(0)
  })

  it('never claims a wiped-out position can come back', () => {
    expect(gainNeeded(1)).toBe(Number.POSITIVE_INFINITY)
  })
})

describe('yearsToRecover', () => {
  it('compounds, rather than dividing the loss by the rate', () => {
    // 0.5 / 0.15 = 3.33 years, and that answer is wrong. Compounding gives
    // ~4.96. The naive division understates the wait at every size, and this
    // panel exists precisely to not understate it — so the naive answer is
    // asserted *against*, not just left untested.
    const years = yearsToRecover(0.5, DEFAULT_ANNUAL_RATE)

    expect(years).toBeCloseTo(4.9595, 3)
    expect(years).toBeGreaterThan(0.5 / DEFAULT_ANNUAL_RATE)
  })

  it('reproduces the figure the product has been quoting', () => {
    // "A 50% loss takes about seven years to undo" is at 10%, not at the 15%
    // default. Both are correct and the difference is the assumed rate, which
    // is exactly why the rate is visible on screen instead of baked in here.
    expect(yearsToRecover(0.5, 0.1)).toBeCloseTo(7.2725, 3)
  })

  it('makes the last stretch the expensive one', () => {
    // Read down this column and the shape of the thing appears: the first
    // figure is a bad year, the last is most of a working life.
    expect(yearsToRecover(0.1)).toBeCloseTo(0.7539, 3)
    expect(yearsToRecover(0.9)).toBeCloseTo(16.4751, 3)
  })

  it('costs more than twice as much for twice the depth', () => {
    // The non-linearity is the point. If this ever became proportional the
    // panel would stop saying anything a reader did not already assume.
    expect(yearsToRecover(0.9)).toBeGreaterThan(2 * yearsToRecover(0.5))
  })

  it('increases strictly with depth', () => {
    const series = DEPTHS.map((depth) => yearsToRecover(depth))
    for (let i = 1; i < series.length; i += 1) {
      expect(series[i]).toBeGreaterThan(series[i - 1])
    }
  })

  it('takes no time when there is nothing to recover', () => {
    expect(yearsToRecover(0)).toBe(0)
    expect(yearsToRecover(-0.2)).toBe(0)
  })

  it('says "never" rather than a very large number', () => {
    // Three different ways to never get back: everything gone, an assumed rate
    // of zero, and a negative rate. All three are Infinity rather than a
    // throw, because "never" is the true answer to all three.
    expect(yearsToRecover(1)).toBe(Number.POSITIVE_INFINITY)
    expect(yearsToRecover(1.4)).toBe(Number.POSITIVE_INFINITY)
    expect(yearsToRecover(0.5, 0)).toBe(Number.POSITIVE_INFINITY)
    expect(yearsToRecover(0.5, -0.05)).toBe(Number.POSITIVE_INFINITY)
  })

  it('gets shorter as the assumed rate rises', () => {
    // The assumption is doing real work, so it must be visible: a reader who
    // cannot see the rate cannot tell whether they are being flattered.
    expect(yearsToRecover(0.5, 0.2)).toBeLessThan(yearsToRecover(0.5, 0.1))
  })
})

describe('formatYears', () => {
  it('keeps one decimal, because the difference between 5.0 and 5.9 matters', () => {
    expect(formatYears(4.9595)).toBe('5.0')
    expect(formatYears(2.552)).toBe('2.6')
  })

  it('renders an unrecoverable position as 永远', () => {
    expect(formatYears(Number.POSITIVE_INFINITY)).toBe('永远')
  })

  it('does not let "not computed" wear the face of "never"', () => {
    // The empty input box produces NaN. Rendering that as 永远 would state a
    // fact about the world that nobody computed — the exact class of confident
    // wrong answer this project treats as a defect everywhere else.
    expect(formatYears(Number.NaN)).toBe('—')
    expect(formatGain(Number.NaN)).toBe('—')
  })

  it('stops counting past a century, rather than printing false precision', () => {
    expect(formatYears(140)).toBe('> 100')
  })
})

describe('formatGain', () => {
  it('renders the four figures a reader actually meets as themselves', () => {
    // These are the whole point of the panel, so they get an exact assertion
    // rather than an approximate one: a 10% loss needs 11.1%, a 30% loss needs
    // 42.9%, a 50% loss needs 100%, a 90% loss needs 900%.
    expect(formatGain(gainNeeded(0.1))).toBe('11.1%')
    expect(formatGain(gainNeeded(0.3))).toBe('42.9%')
    expect(formatGain(gainNeeded(0.5))).toBe('100%')
    expect(formatGain(gainNeeded(0.9))).toBe('900%')
  })

  it('drops the decimal above 100%, where it would be false precision', () => {
    expect(formatGain(gainNeeded(0.7))).toBe('233%')
  })

  it('has no percentage to give for an unrecoverable position', () => {
    expect(formatGain(Number.POSITIVE_INFINITY)).toBe('无法回本')
  })
})

describe('formatRate', () => {
  it('drops the decimal when it says nothing', () => {
    expect(formatRate(0.15)).toBe('15%')
  })

  it('keeps it when it does', () => {
    expect(formatRate(0.125)).toBe('12.5%')
  })
})

describe('DEPTHS', () => {
  it('is ascending, so reading down the panel reads as worse', () => {
    const sorted = [...DEPTHS].sort((a, b) => a - b)
    expect(DEPTHS).toEqual(sorted)
  })
})

describe('depthsIncluding', () => {
  it('adds the reader’s own figure when it is not already a row', () => {
    // Down 32% must see 32% in the column. Five fixed depths answer "here is
    // the curve"; only a row of their own answers "and where am I on it".
    expect(depthsIncluding(0.32)).toEqual([0.1, 0.3, 0.32, 0.5, 0.7, 0.9])
  })

  it('does not add a second row that would print identically', () => {
    // 30.2% renders as "30%" next to a fixed "30%" row. Two rows that read the
    // same and sit adjacent are worse than either alone.
    expect(depthsIncluding(0.302)).toHaveLength(DEPTHS.length)
  })

  it('adds nothing for a figure that is already a row', () => {
    expect(depthsIncluding(0.5)).toHaveLength(DEPTHS.length)
  })

  it('ignores figures that are not on this curve at all', () => {
    // 0 and 1 are not positions between "some loss" and "total loss" — and NaN
    // is an empty input box. Inventing a row for any of them would be the table
    // making up a fact.
    for (const loss of [0, 1, 1.5, -0.2, Number.NaN]) {
      expect(depthsIncluding(loss)).toHaveLength(DEPTHS.length)
    }
  })

  it('keeps the result ascending whatever was inserted', () => {
    const rows = depthsIncluding(0.05)
    expect(rows).toEqual([...rows].sort((a, b) => a - b))
    expect(rows[0]).toBe(0.05)
  })
})

describe('isOwnDepth', () => {
  it('marks a row the reader’s own at the precision the table prints', () => {
    expect(isOwnDepth(0.32, 0.32)).toBe(true)
    expect(isOwnDepth(0.32, 0.3)).toBe(false)
    expect(isOwnDepth(0.301, 0.3)).toBe(true)
  })
})
