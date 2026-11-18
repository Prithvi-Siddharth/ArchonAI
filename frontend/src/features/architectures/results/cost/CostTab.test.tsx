import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { makeResult } from '@/test/job-fixtures'
import { REAL_COST_EMPTY_BREAKDOWN, REAL_COST_OTHER_DISCLAIMER, REAL_COST_SEVEN_AREAS } from '@/test/real-cost-analyses'
import type { CostAnalysis } from '@/types/api'

import { costLevel } from './cost-levels'
import { CostTab } from './CostTab'

const renderCost = (cost: CostAnalysis) => render(<CostTab result={makeResult({ cost_analysis: cost })} />)
const card = (title: string) => screen.getByRole('heading', { name: title }).closest('.rounded-lg') as HTMLElement
const rows = () => within(screen.getByRole('table', { name: 'Relative cost breakdown by area' })).getAllByRole('row').slice(1)

afterEach(() => cleanup())

describe('costLevel', () => {
  it('recognises only the low / medium / high scale', () => {
    expect(['low', 'medium', 'high', ' High ', 'MEDIUM'].map(costLevel)).toEqual([1, 2, 3, 3, 2])
    expect(['very high', '40%', '$1,200', '', 'moderate'].map(costLevel)).toEqual([null, null, null, null, null])
  })
})

describe('CostTab with real data', () => {
  it('shows the estimated range exactly as returned, marked as an estimate', () => {
    renderCost(REAL_COST_SEVEN_AREAS)
    expect(screen.getByText(REAL_COST_SEVEN_AREAS.estimated_monthly_range)).toBeTruthy()
    expect(screen.getByText('Educational estimate')).toBeTruthy()
  })

  it('shows the backend disclaimer verbatim, including other wordings', () => {
    renderCost(REAL_COST_SEVEN_AREAS)
    expect(within(card('Disclaimer')).getByText(REAL_COST_SEVEN_AREAS.disclaimer)).toBeTruthy()
    cleanup()
    renderCost(REAL_COST_OTHER_DISCLAIMER)
    expect(screen.getByText(REAL_COST_OTHER_DISCLAIMER.disclaimer)).toBeTruthy()
  })

  it('lists every major cost driver', () => {
    renderCost(REAL_COST_SEVEN_AREAS)
    expect(within(card('Major cost drivers')).getAllByRole('listitem').map((li) => li.textContent)).toEqual(REAL_COST_SEVEN_AREAS.major_cost_drivers)
  })

  it('shows every breakdown area and its original value, in order, as levels (not amounts)', () => {
    renderCost(REAL_COST_SEVEN_AREAS)
    const expected = Object.entries(REAL_COST_SEVEN_AREAS.relative_cost_breakdown)
    expect(rows().map((r) => [r.dataset.area, r.querySelectorAll('td')[0].textContent])).toEqual(expected)
    expect(rows().map((r) => r.dataset.level)).toEqual(expected.map(([, v]) => String(costLevel(v))))
    expect(screen.getByText(/A ranking, not amounts or percentages of spend/)).toBeTruthy()
    const text = card('Relative cost breakdown').textContent ?? ''
    expect(text).not.toMatch(/%|\$/)
  })

  it('lists every optimization and every trade-off', () => {
    renderCost(REAL_COST_SEVEN_AREAS)
    expect(within(card('Cost optimization recommendations')).getAllByRole('listitem').map((li) => li.textContent)).toEqual(REAL_COST_SEVEN_AREAS.optimizations)
    expect(within(card('Architectural trade-offs')).getAllByRole('listitem').map((li) => li.textContent)).toEqual(REAL_COST_SEVEN_AREAS.trade_offs)
    expect(screen.getByText(/not guaranteed/)).toBeTruthy()
    expect(screen.getByText(/not necessarily savings/)).toBeTruthy()
  })

  it('shows an empty state for an empty breakdown (real result bab8871e)', () => {
    renderCost(REAL_COST_EMPTY_BREAKDOWN)
    expect(screen.getByText('No breakdown provided')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(within(card('Cost optimization recommendations')).getAllByRole('listitem')).toHaveLength(1)
  })
})

describe('CostTab edge cases', () => {
  it('shows values off the low / medium / high scale as text, without a meter', () => {
    renderCost({ ...REAL_COST_SEVEN_AREAS, relative_cost_breakdown: { compute: 'high', 'data transfer': 'significant', egress: '40%' } })
    expect(rows().map((r) => [r.dataset.area, r.dataset.level, r.querySelectorAll('td')[0].textContent])).toEqual([
      ['compute', '3', 'high'],
      ['data transfer', 'text', 'significant'],
      ['egress', 'text', '40%'],
    ])
    expect(screen.getAllByText('Not on the low / medium / high scale')).toHaveLength(2)
    expect(screen.queryByText(/on the low \/ medium \/ high scale the cost agent used/)).toBeNull()
  })

  it.each([
    'Roughly $2k-$5k monthly, depending on traffic',
    '€3.000 – €9.000 / Monat',
    'Not estimated: insufficient information',
  ])('shows an unusual range unchanged: %s', (range) => {
    renderCost({ ...REAL_COST_SEVEN_AREAS, estimated_monthly_range: range })
    expect(screen.getByText(range)).toBeTruthy()
  })

  it('handles empty lists and a blank range or disclaimer', () => {
    renderCost({
      estimated_monthly_range: '  ',
      major_cost_drivers: [],
      relative_cost_breakdown: {},
      optimizations: [],
      trade_offs: [],
      disclaimer: '',
    })
    for (const title of ['Not provided', 'No cost drivers listed', 'No breakdown provided', 'No optimizations suggested', 'No trade-offs listed']) {
      expect(screen.getByText(title)).toBeTruthy()
    }
    expect(screen.getByText(/No disclaimer was provided/)).toBeTruthy()
  })
})
