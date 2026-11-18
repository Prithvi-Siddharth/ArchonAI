import { describe, expect, it } from 'vitest'

import { makeResult } from '@/test/job-fixtures'
import { REAL_TRACE_ONE_REVISION, REAL_TRACE_TWO_REVISIONS } from '@/test/real-traces'
import type { ArchitectureResult, TraceEntry } from '@/types/api'

import { iterationLabel, readTrace } from './trace-model'

const traceOf = (execution_trace: TraceEntry[]) => readTrace(makeResult({ execution_trace }))
const entry = (node: string, iteration: number, output_summary = `${node} output`): TraceEntry => ({ node, action: `${node} ran`, output_summary, iteration })

describe('readTrace with real traces', () => {
  it('17e8c5b5: 18 steps in returned order, 13 distinct nodes, revision rounds 1 and 2', () => {
    const t = traceOf(REAL_TRACE_TWO_REVISIONS)
    expect(t.steps.map((s) => [s.seq, s.node, s.action, s.summary, s.iteration])).toEqual(
      REAL_TRACE_TWO_REVISIONS.map((e, i) => [i + 1, e.node, e.action, e.output_summary, e.iteration]),
    )
    expect(t.distinctNodes).toBe(13)
    expect(t.iterations).toEqual([0, 1, 2])
    expect(t.revisionRounds).toEqual([1, 2])
    expect(t.groups.map((g) => [g.iteration, g.steps.map((s) => s.seq)])).toEqual([
      [0, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]],
      [1, [12, 13, 14]],
      [2, [15, 16, 17, 18]],
    ])
    expect(t.repeated).toEqual([
      { node: 'Architecture Validator', runs: 3 },
      { node: 'Architecture Critic', runs: 3 },
      { node: 'Architecture Revision', runs: 2 },
    ])
  })

  it('keeps the recorded order of parallel nodes (Cost Agent before Reliability Agent here)', () => {
    const nodes = traceOf(REAL_TRACE_TWO_REVISIONS).steps.map((s) => s.node)
    expect(nodes.indexOf('Cost Agent')).toBeLessThan(nodes.indexOf('Reliability Agent'))
  })

  it('2c9cd4ce: one revision round', () => {
    const t = traceOf(REAL_TRACE_ONE_REVISION)
    expect(t.steps).toHaveLength(15)
    expect(t.revisionRounds).toEqual([1])
    expect(t.groups.map((g) => g.steps.length)).toEqual([11, 4])
  })
})

describe('readTrace edge cases', () => {
  it('numbers each run of a repeated node', () => {
    const t = traceOf([entry('Critic', 0), entry('Revision', 1), entry('Critic', 1), entry('Report', 1)])
    expect(t.steps.map((s) => [s.node, s.run, s.runs])).toEqual([
      ['Critic', 1, 2],
      ['Revision', 1, 1],
      ['Critic', 2, 2],
      ['Report', 1, 1],
    ])
  })

  it('groups only consecutive steps, so out-of-order iterations never move a step', () => {
    const t = traceOf([entry('A', 0), entry('B', 2), entry('C', 1), entry('D', 1), entry('E', 0)])
    expect(t.groups.map((g) => [g.iteration, g.steps.map((s) => s.node)])).toEqual([
      [0, ['A']],
      [2, ['B']],
      [1, ['C', 'D']],
      [0, ['E']],
    ])
    expect(t.steps.map((s) => s.node)).toEqual(['A', 'B', 'C', 'D', 'E'])
  })

  it('treats negative, fractional, non-number and missing iterations as unexpected, not as revision rounds', () => {
    const odd = [
      { node: 'A', action: '', output_summary: '', iteration: -1 },
      { node: 'B', action: '', output_summary: '', iteration: 1.5 },
      { node: 'C', action: '', output_summary: '', iteration: '2' },
      { node: 'D', action: '', output_summary: '' },
      { node: 'E', action: '', output_summary: '', iteration: Number.NaN },
    ] as unknown as TraceEntry[]
    const t = traceOf(odd)
    expect(t.steps.map((s) => [s.iteration, s.rawIteration])).toEqual([
      [null, '-1'],
      [null, '1.5'],
      [null, '2'],
      [null, ''],
      [null, 'NaN'],
    ])
    expect(t.revisionRounds).toEqual([])
    expect(t.hasUnexpectedIteration).toBe(true)
    expect(t.groups).toHaveLength(5)
    expect(iterationLabel(null, '-1')).toBe('Unexpected iteration "-1"')
    expect(iterationLabel(null, '')).toBe('Iteration not recorded')
    expect(iterationLabel(3, '3')).toBe('Iteration 3')
  })

  it('survives a missing trace, a non-array, and malformed entries', () => {
    const result: Record<string, unknown> = { ...makeResult() }
    delete result.execution_trace
    expect(readTrace(result as unknown as ArchitectureResult).steps).toEqual([])
    expect(readTrace({ ...makeResult(), execution_trace: 'nope' } as unknown as ArchitectureResult).steps).toEqual([])
    const t = readTrace({ ...makeResult(), execution_trace: [null, 7, { node: '  X  ', output_summary: 'a\r\nb' }] } as unknown as ArchitectureResult)
    expect(t.steps.map((s) => [s.seq, s.node, s.action, s.summary])).toEqual([
      [1, '', '', ''],
      [2, '', '', ''],
      [3, 'X', '', 'a\nb'],
    ])
    expect(t.distinctNodes).toBe(1)
  })
})
