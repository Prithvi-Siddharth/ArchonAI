import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { makeResult } from '@/test/job-fixtures'
import { REAL_TRACE_ONE_REVISION, REAL_TRACE_TWO_REVISIONS } from '@/test/real-traces'
import type { TraceEntry } from '@/types/api'

import { TraceTab } from './TraceTab'

const renderTrace = (execution_trace: TraceEntry[]) => render(<TraceTab result={makeResult({ execution_trace })} />)
const steps = () => [...document.querySelectorAll<HTMLElement>('li[data-seq]')]
const overview = () =>
  Object.fromEntries(within(screen.getByRole('heading', { name: 'Execution trace' }).closest('.rounded-lg') as HTMLElement).getAllByRole('term').map((dt) => [dt.textContent, dt.nextElementSibling?.textContent]))
const groupTitles = () => [...document.querySelectorAll('[data-group] h2')].map((h) => h.textContent)
const entry = (node: string, iteration: number, output_summary = `${node} output`): TraceEntry => ({ node, action: `${node} ran`, output_summary, iteration })

afterEach(() => cleanup())

describe('TraceTab with a real trace (job 17e8c5b5)', () => {
  it('overview: counts calculated from the trace', () => {
    renderTrace(REAL_TRACE_TWO_REVISIONS)
    expect(overview()).toEqual({ Steps: '18', 'Distinct nodes': '13', 'Revision rounds': '2' })
    expect(screen.getByText(/Iteration values in the trace: 0, 1, 2\./)).toBeTruthy()
    const repeated = screen.getByRole('group', { name: 'Repeated nodes' })
    expect(within(repeated).getAllByText(/×/).map((b) => b.textContent)).toEqual(['Architecture Validator ×3', 'Architecture Critic ×3', 'Architecture Revision ×2'])
  })

  it('renders every entry in the returned order with sequence, node, action, summary and iteration', () => {
    renderTrace(REAL_TRACE_TWO_REVISIONS)
    expect(steps().map((li) => [li.dataset.seq, li.querySelector('h3')?.textContent, li.querySelectorAll('p')[0].textContent, li.querySelectorAll('p')[2].textContent, li.dataset.iteration])).toEqual(
      REAL_TRACE_TWO_REVISIONS.map((e, i) => [String(i + 1), `Step ${i + 1}: ${e.node}`, e.action, e.output_summary, String(e.iteration)]),
    )
    expect(steps().map((li) => li.querySelector('[aria-hidden="true"].rounded-full')?.textContent)).toEqual(REAL_TRACE_TWO_REVISIONS.map((_, i) => String(i + 1)))
  })

  it('separates iterations 0, 1 and 2 into their own groups, numbering continuing across them', () => {
    renderTrace(REAL_TRACE_TWO_REVISIONS)
    expect(groupTitles()).toEqual(['Iteration 0', 'Iteration 1', 'Iteration 2'])
    const lists = screen.getAllByRole('list').filter((l) => l.tagName === 'OL')
    expect(lists.map((ol) => [ol.getAttribute('aria-label'), ol.getAttribute('start'), ol.children.length])).toEqual([
      ['Iteration 0 steps', '1', 11],
      ['Iteration 1 steps', '12', 3],
      ['Iteration 2 steps', '15', 4],
    ])
    expect(screen.getByText(/Recorded before any revision/)).toBeTruthy()
    expect(screen.getByText(/revision count at 2\. Steps 15–18\./)).toBeTruthy()
  })

  it('makes iteration 0 look different from revision rounds', () => {
    renderTrace(REAL_TRACE_TWO_REVISIONS)
    const [zero, one] = [...document.querySelectorAll<HTMLElement>('[data-group]')]
    expect(zero.className).not.toContain('border-l-4')
    expect(one.className).toContain('border-l-info')
    const marker = (seq: number) => document.querySelector(`li[data-seq="${seq}"] > span.rounded-full`)?.className ?? ''
    expect(marker(1)).not.toEqual(marker(12))
  })

  it('marks repeated nodes with their run number', () => {
    renderTrace(REAL_TRACE_TWO_REVISIONS)
    const critics = steps().filter((li) => li.querySelector('h3')?.textContent?.endsWith('Architecture Critic'))
    expect(critics.map((li) => [li.dataset.seq, li.querySelector('[data-repeat]')?.textContent])).toEqual([
      ['11', 'Run 1 of 3'],
      ['14', 'Run 2 of 3'],
      ['17', 'Run 3 of 3'],
    ])
    expect(steps()[0].querySelector('[data-repeat]')).toBeNull() // Requirements Analyzer runs once
  })

  it('shows no timestamps, durations or invented timing', () => {
    renderTrace(REAL_TRACE_TWO_REVISIONS)
    // Only the UI's own text: backend wording such as "sub-200ms" is content, not timing the UI added.
    const clone = document.body.cloneNode(true) as HTMLElement
    clone.querySelectorAll('li[data-seq] p').forEach((p) => p.remove())
    const text = clone.textContent ?? ''
    expect(text).toContain('no timestamps or durations')
    expect(text.replace('no timestamps or durations', '')).not.toMatch(/\d+\s?(ms|s|sec|seconds|min|minutes)\b|\d{1,2}:\d{2}|elapsed|duration|timestamp|\bago\b/i)
    expect(document.querySelector('time')).toBeNull()
  })
})

describe('TraceTab edge cases', () => {
  it('a single-iteration trace stays compact: one timeline, no per-iteration cards', () => {
    renderTrace([entry('A', 0), entry('B', 0), entry('A', 0)])
    expect(groupTitles()).toEqual(['Timeline'])
    expect(overview()).toEqual({ Steps: '3', 'Distinct nodes': '2', 'Revision rounds': '0' })
    expect(screen.getByText(/Iteration values in the trace: 0\./)).toBeTruthy()
    expect(document.querySelector('[data-group]')?.className).not.toContain('border-l-4')
  })

  it('a real one-revision trace (2c9cd4ce) has two groups', () => {
    renderTrace(REAL_TRACE_ONE_REVISION)
    expect(groupTitles()).toEqual(['Iteration 0', 'Iteration 1'])
    expect(overview()['Revision rounds']).toBe('1')
  })

  it('a single entry', () => {
    renderTrace([entry('Final Report', 0, 'Done.')])
    expect(steps()).toHaveLength(1)
    expect(screen.getByText('Done.')).toBeTruthy()
    expect(screen.getByText(/Step 1\./)).toBeTruthy()
    expect(screen.queryByRole('group', { name: 'Repeated nodes' })).toBeNull()
    expect(steps()[0].querySelector('span.w-px')).toBeNull() // no connector after the last step
  })

  it('an empty trace shows an EmptyState', () => {
    renderTrace([])
    expect(screen.getByText('No execution trace')).toBeTruthy()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('missing node, action and output summary each get a placeholder; long and multiline summaries are kept whole', () => {
    const long = `${'Very long summary. '.repeat(60)}\nSecond line.`
    renderTrace([{ node: '', action: '', output_summary: '  ', iteration: 0 }, entry('B', 0, long)])
    const [first, second] = steps()
    expect(within(first).getByText('Unnamed step')).toBeTruthy()
    expect(within(first).getByText('No action recorded.')).toBeTruthy()
    expect(within(first).getByText('No output summary recorded.')).toBeTruthy()
    const summary = second.querySelectorAll('p')[2]
    expect(summary.textContent).toBe(long.trim())
    expect(summary.className).toContain('whitespace-pre-line')
  })

  it('unexpected iteration values are labelled, not hidden or counted as revisions', () => {
    renderTrace([entry('A', 0), { ...entry('B', 0), iteration: -1 }, { node: 'C', action: 'x', output_summary: 'y' } as unknown as TraceEntry])
    expect(groupTitles()).toEqual(['Iteration 0', 'Unexpected iteration "-1"', 'Iteration not recorded'])
    expect(overview()['Revision rounds']).toBe('0')
    expect(screen.getByText(/Some steps have no valid iteration value/)).toBeTruthy()
    expect(steps().map((li) => li.querySelector('h3')?.textContent)).toEqual(['Step 1: A', 'Step 2: B', 'Step 3: C'])
  })
})
