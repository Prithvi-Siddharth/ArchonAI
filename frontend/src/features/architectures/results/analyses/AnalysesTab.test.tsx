import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { makeResult } from '@/test/job-fixtures'
import { REAL_ANALYSES, type SpecialistAnalyses } from '@/test/real-analyses'
import type { AnalysisResult, ArchitectureResult } from '@/types/api'

import { AnalysesTab, SPECIALISTS } from './AnalysesTab'

type Key = keyof SpecialistAnalyses

const renderTab = (result: ArchitectureResult) => render(<AnalysesTab result={result} />)
const renderReal = (overrides: Partial<SpecialistAnalyses> = {}) => renderTab(makeResult({ ...REAL_ANALYSES, ...overrides }))
/** A result with the given analyses removed entirely, as an older or partial stored result might be. */
const withoutAnalyses = (...keys: Key[]) => {
  const result: Record<string, unknown> = { ...makeResult(REAL_ANALYSES) }
  for (const key of keys) delete result[key]
  return result as unknown as ArchitectureResult
}
const section = (key: Key) => document.getElementById(`analysis-${key.replace('_analysis', '')}`) as HTMLElement
const items = (el: HTMLElement, name: 'Recommendations' | 'Risks') =>
  within(el).getAllByRole('listitem').filter((li) => li.closest('ul')?.getAttribute('aria-label') === name).map((li) => li.textContent)
const overview = () =>
  Object.fromEntries(
    within(screen.getByRole('region', { name: 'Specialist analyses' })).getAllByRole('term').map((dt) => [dt.textContent, dt.nextElementSibling?.textContent]),
  )

const ALL_KEYS = SPECIALISTS.map((s) => s.key)
const EMPTY: AnalysisResult = { domain: '', recommendations: [], reasoning: '', risks: [] }

afterEach(() => cleanup())

describe('AnalysesTab with real data (job 17e8c5b5)', () => {
  it('overview: five analyses and totals summed from the lists', () => {
    renderReal()
    const recs = ALL_KEYS.reduce((n, k) => n + REAL_ANALYSES[k].recommendations.length, 0)
    const risks = ALL_KEYS.reduce((n, k) => n + REAL_ANALYSES[k].risks.length, 0)
    expect(overview()).toEqual({ 'Specialist analyses': '5', Recommendations: String(recs), Risks: String(risks) })
  })

  it('shows the five sections in workflow order with their original domain names', () => {
    renderReal()
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(headings).toEqual(ALL_KEYS.map((k) => REAL_ANALYSES[k].domain))
    const links = within(screen.getByRole('navigation', { name: 'Specialist sections' })).getAllByRole('link')
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['#analysis-compute', '#analysis-database', '#analysis-networking', '#analysis-security', '#analysis-reliability'])
  })

  it.each(ALL_KEYS)('%s: every recommendation and risk in order, and the full reasoning', (key) => {
    renderReal()
    const el = section(key)
    const analysis = REAL_ANALYSES[key]
    expect(items(el, 'Recommendations')).toEqual(analysis.recommendations)
    expect(items(el, 'Risks')).toEqual(analysis.risks)
    expect(within(el).getByText(analysis.reasoning)).toBeTruthy()
    expect(within(el).getByText(`${analysis.recommendations.length} recommendation${analysis.recommendations.length === 1 ? '' : 's'}`)).toBeTruthy()
  })

  it('keeps recommendations and risks visually distinct', () => {
    renderReal()
    const el = section('security_analysis')
    const recList = within(el).getByRole('list', { name: 'Recommendations' })
    const riskList = within(el).getByRole('list', { name: 'Risks' })
    expect(recList.querySelector('svg')?.getAttribute('class')).toContain('text-primary')
    expect(riskList.querySelector('svg')?.getAttribute('class')).toContain('text-warning')
    expect(riskList.parentElement?.className).toContain('bg-warning/5')
  })

  it('shows no scores, ratings or confidence levels', () => {
    renderReal()
    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/score|rating|confidence|\/100|%/i)
  })
})

describe('AnalysesTab edge cases', () => {
  it('preserves line breaks in long reasoning', () => {
    const reasoning = 'First paragraph about compute.\n\nSecond paragraph.\nA third line.'
    renderReal({ compute_analysis: { ...REAL_ANALYSES.compute_analysis, reasoning } })
    const p = within(section('compute_analysis')).getByText((_, node) => node?.textContent === reasoning && node.tagName === 'P')
    expect(p.textContent).toBe(reasoning)
    expect(p.className).toContain('whitespace-pre-line')
  })

  it('a missing analysis gets its own empty state; the others still render', () => {
    renderTab(withoutAnalyses('networking_analysis'))
    const net = section('networking_analysis')
    expect(within(net).getByText('Analysis not available')).toBeTruthy()
    expect(within(net).getByRole('heading', { level: 3 }).textContent).toBe('Networking')
    expect(within(net).queryByRole('list')).toBeNull()
    expect(items(section('security_analysis'), 'Risks')).toEqual(REAL_ANALYSES.security_analysis.risks)
    expect(overview()['Specialist analyses']).toBe('4')
  })

  it('an analysis with empty lists and reasoning gets its own empty state', () => {
    renderReal({ database_analysis: { ...EMPTY, domain: 'Database' } })
    expect(within(section('database_analysis')).getByText('No analysis content')).toBeTruthy()
    expect(within(section('database_analysis')).getByText('0 recommendations')).toBeTruthy()
    expect(within(section('compute_analysis')).queryByText('No analysis content')).toBeNull()
  })

  it('empty recommendations or risks alone are handled per list', () => {
    renderReal({
      compute_analysis: { ...REAL_ANALYSES.compute_analysis, risks: [] },
      database_analysis: { ...REAL_ANALYSES.database_analysis, recommendations: [], reasoning: '' },
    })
    expect(within(section('compute_analysis')).getByText('No risks identified.')).toBeTruthy()
    expect(within(section('compute_analysis')).getByText('0 risks')).toBeTruthy()
    expect(within(section('database_analysis')).getByText('No recommendations.')).toBeTruthy()
    expect(within(section('database_analysis')).getByText('No reasoning provided.')).toBeTruthy()
    expect(items(section('database_analysis'), 'Risks')).toEqual(REAL_ANALYSES.database_analysis.risks)
  })

  it('falls back to the specialist label when the domain is blank', () => {
    renderReal({ reliability_analysis: { ...REAL_ANALYSES.reliability_analysis, domain: '  ' } })
    expect(within(section('reliability_analysis')).getByRole('heading', { level: 3 }).textContent).toBe('Reliability')
  })

  it('shows one overall empty state when every analysis is missing or empty', () => {
    const result = withoutAnalyses('compute_analysis', 'database_analysis')
    renderTab({ ...result, networking_analysis: EMPTY, security_analysis: EMPTY, reliability_analysis: EMPTY })
    expect(screen.getByText('No specialist analyses')).toBeTruthy()
    expect(screen.queryByRole('heading', { level: 3 })).toBeNull()
  })
})
