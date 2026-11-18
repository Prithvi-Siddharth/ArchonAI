// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { REAL_ARCHITECTURE_BACKWARD, REAL_ARCHITECTURE_COMBINED } from '@/test/real-architectures'
import type { DataFlowStep } from '@/types/api'

import { buildDiagram, connectionsOf, NODE_HEIGHT, NODE_WIDTH } from './diagram-layout'
import { possibleServiceMatches } from './service-matching'

const step = (n: number, source: string, destination: string): DataFlowStep => ({ step: n, source, destination, description: `step ${n}` })

describe('buildDiagram on real backend data', () => {
  it('uses every unique label exactly as written, in first-appearance order', () => {
    const { nodes } = buildDiagram(REAL_ARCHITECTURE_COMBINED.data_flow)
    expect(nodes.map((n) => n.label)).toEqual([
      'User browser',
      'CloudFront + WAF',
      'Route 53 + ALB',
      'ALB',
      'ECS Fargate',
      'DynamoDB + ElastiCache',
      'Aurora + SQS',
    ])
  })

  it('draws one edge per step, in backend order, with the original source and destination', () => {
    const steps = REAL_ARCHITECTURE_COMBINED.data_flow
    const { edges } = buildDiagram(steps)
    expect(edges.map((e) => [e.step.step, e.step.source, e.step.destination])).toEqual(steps.map((s) => [s.step, s.source, s.destination]))
  })

  it('places every destination to the right of its source for forward steps', () => {
    const { nodes, edges } = buildDiagram(REAL_ARCHITECTURE_COMBINED.data_flow)
    const at = new Map(nodes.map((n) => [n.label, n]))
    for (const e of edges.filter((x) => x.kind === 'forward')) {
      expect(at.get(e.step.destination)!.column).toBeGreaterThan(at.get(e.step.source)!.column)
    }
  })

  it('does not invent a link between distinct labels ("Route 53 + ALB" and "ALB" stay separate)', () => {
    const { nodes, edges } = buildDiagram(REAL_ARCHITECTURE_COMBINED.data_flow)
    expect(nodes.filter((n) => n.label.includes('ALB'))).toHaveLength(2)
    expect(edges.some((e) => e.step.source === 'Route 53 + ALB' && e.step.destination === 'ALB')).toBe(false)
  })

  it('handles fan-out (multiple outgoing steps from one endpoint)', () => {
    const { outgoing, incoming } = connectionsOf('ECS Fargate', REAL_ARCHITECTURE_COMBINED.data_flow)
    expect(outgoing.map((s) => s.step)).toEqual([4, 5])
    expect(incoming.map((s) => s.step)).toEqual([3])
  })

  it('draws a step back to an earlier endpoint as a back edge, not a cycle', () => {
    const { edges, nodes } = buildDiagram(REAL_ARCHITECTURE_BACKWARD.data_flow)
    const back = edges.filter((e) => e.kind === 'back')
    expect(back.map((e) => [e.step.step, e.step.source, e.step.destination])).toEqual([[6, 'ECS (Fargate) + Lambda', 'User']])
    expect(nodes.find((n) => n.label === 'User')!.column).toBe(0)
  })

  it('keeps nodes from overlapping and inside the drawing', () => {
    for (const architecture of [REAL_ARCHITECTURE_COMBINED, REAL_ARCHITECTURE_BACKWARD]) {
      const { nodes, width, height } = buildDiagram(architecture.data_flow)
      for (const a of nodes) {
        expect(a.x).toBeGreaterThanOrEqual(0)
        expect(a.y).toBeGreaterThanOrEqual(0)
        expect(a.x + NODE_WIDTH).toBeLessThanOrEqual(width)
        expect(a.y + NODE_HEIGHT).toBeLessThanOrEqual(height)
        for (const b of nodes) {
          if (a === b) continue
          const overlap = a.x < b.x + NODE_WIDTH && b.x < a.x + NODE_WIDTH && a.y < b.y + NODE_HEIGHT && b.y < a.y + NODE_HEIGHT
          expect(overlap).toBe(false)
        }
      }
    }
  })
})

describe('buildDiagram edge cases', () => {
  it('returns an empty drawing for no steps', () => {
    expect(buildDiagram([])).toMatchObject({ nodes: [], edges: [] })
  })

  it('separates repeated steps between the same two endpoints', () => {
    const { edges } = buildDiagram([step(1, 'A', 'B'), step(2, 'A', 'B')])
    expect(edges[0].path).not.toBe(edges[1].path)
    expect(edges[0].labelY).not.toBe(edges[1].labelY)
  })

  it('gives multiple back edges different depths', () => {
    const { edges } = buildDiagram([step(1, 'A', 'B'), step(2, 'B', 'C'), step(3, 'C', 'A'), step(4, 'B', 'A')])
    const back = edges.filter((e) => e.kind === 'back')
    expect(back).toHaveLength(2)
    expect(back[0].labelY).not.toBe(back[1].labelY)
  })

  it('draws a step to itself as a loop', () => {
    expect(buildDiagram([step(1, 'Queue', 'Queue')]).edges[0].kind).toBe('self')
  })
})

describe('possibleServiceMatches (name-based, unconfirmed)', () => {
  const services = REAL_ARCHITECTURE_COMBINED.services

  it.each([
    ['DynamoDB + ElastiCache', ['Amazon ElastiCache Redis', 'Amazon DynamoDB + Aurora PITR']],
    ['Aurora + SQS', ['Amazon Aurora PostgreSQL', 'Amazon SQS', 'Amazon DynamoDB + Aurora PITR']],
    ['CloudFront + WAF', ['Amazon CloudFront + AWS WAF']],
    ['User browser', []],
  ])('%s', (label, expected) => {
    expect(possibleServiceMatches(label, services).map((s) => s.name)).toEqual(expected)
  })

  it('matches acronyms and parentheses', () => {
    const real = REAL_ARCHITECTURE_BACKWARD.services
    expect(possibleServiceMatches('ALB', real).map((s) => s.name)).toEqual(['Application Load Balancer'])
    expect(possibleServiceMatches('ECS (Fargate) + Lambda', real).map((s) => s.name)).toEqual(['Amazon ECS (Fargate) + Auto Scaling + AWS Lambda'])
    expect(possibleServiceMatches('User', real)).toEqual([])
  })
})
