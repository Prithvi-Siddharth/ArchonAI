// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { PLAN_AREAS, splitCostRange } from './result-format'
import { parseResultTab, RESULT_TABS } from './results-tabs'

describe('splitCostRange', () => {
  it.each([
    ['$4,120 - $34,800 per month (educational estimate)', '$4,120 - $34,800', 'per month · educational estimate'],
    ['$8,000 – $15,000 (educational estimate)', '$8,000 – $15,000', 'educational estimate'],
    ['$1,000 per month', '$1,000', 'per month'],
    ['Roughly ten thousand dollars', 'Roughly ten thousand dollars', ''],
  ])('%s', (text, amount, note) => {
    expect(splitCostRange(text)).toEqual({ amount, note })
  })
})

describe('parseResultTab', () => {
  it('accepts every tab id', () => {
    for (const { id } of RESULT_TABS) expect(parseResultTab(id)).toBe(id)
  })

  it('falls back to Overview for missing or unknown values', () => {
    expect(parseResultTab(null)).toBe('overview')
    expect(parseResultTab('')).toBe('overview')
    expect(parseResultTab('diagram')).toBe('overview')
    expect(parseResultTab('Review')).toBe('overview') // case-sensitive, like the links the app creates
  })

  it('lists the seven sections in order', () => {
    expect(RESULT_TABS.map((t) => t.label)).toEqual(['Overview', 'Architecture', 'Cost', 'Review', 'Analyses', 'Report', 'Trace'])
  })
})

describe('PLAN_AREAS', () => {
  it('covers all 12 plan concerns', () => {
    expect(PLAN_AREAS).toHaveLength(12)
  })
})
