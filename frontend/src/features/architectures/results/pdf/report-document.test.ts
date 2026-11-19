/**
 * The PDF's document definition, built from real stored results. Pure checks: every section, the
 * cover and contents, honesty about missing data, no invented figures, and figures that fit a page.
 */
import type { Content, TDocumentDefinitions } from 'pdfmake/interfaces'
import { describe, expect, it } from 'vitest'

import type { ArchitectureResult } from '@/types/api'

import { REPORT_SECTIONS } from '../report/report-content'
import { ICON_SVGS } from './icon-svgs'
import { largeResult, REAL_JOB, REAL_LIKE_APPROVED, REAL_LIKE_RESULT } from './pdf-fixtures'
import { pdfFilename } from './pdf-filename'
import { buildReportDocument, FIGURE, projectName, SECTION_TITLES } from './report-document'

function build(result: ArchitectureResult, job: Partial<typeof REAL_JOB> = REAL_JOB): TDocumentDefinitions {
  return buildReportDocument({
    result,
    jobId: job.job_id ?? 'job-0000',
    request: job.user_request ?? null,
    createdAt: job.created_at,
    finishedAt: job.finished_at,
    generatedAt: new Date('2026-11-19T10:00:00Z'),
    appVersion: '1.0.0',
    icons: (key) => ICON_SVGS.get(key),
  })
}

/** Every node in the content tree, depth first. */
function nodes(content: unknown, out: Array<Record<string, unknown>> = []): Array<Record<string, unknown>> {
  if (Array.isArray(content)) content.forEach((c) => nodes(c, out))
  else if (content && typeof content === 'object') {
    const node = content as Record<string, unknown>
    out.push(node)
    for (const key of ['stack', 'columns', 'ul', 'ol', 'text']) if (key in node) nodes(node[key], out)
    if (node.table && typeof node.table === 'object') nodes((node.table as { body: unknown }).body, out)
  }
  return out
}

/** All visible text of the document body (not the SVG figures). */
function textOf(content: unknown): string {
  const parts: string[] = []
  const walk = (value: unknown) => {
    if (typeof value === 'string') parts.push(value)
    else if (Array.isArray(value)) value.forEach(walk)
    else if (value && typeof value === 'object') {
      const node = value as Record<string, unknown>
      for (const key of ['text', 'stack', 'columns', 'ul', 'ol']) if (key in node) walk(node[key])
      if (node.table && typeof node.table === 'object') walk((node.table as { body: unknown }).body)
    }
  }
  walk(content)
  return parts.join('\n')
}

const headings = (doc: TDocumentDefinitions) => nodes(doc.content).filter((n) => n.tocItem === true).map((n) => n.text)

describe('report document', () => {
  const doc = build(REAL_LIKE_RESULT)
  const text = textOf(doc.content)

  it('has every section, numbered, in the brief’s order, each listed in the contents', () => {
    expect(headings(doc)).toEqual(SECTION_TITLES.map(([n, title]) => `${n}. ${title}`))
    expect(nodes(doc.content).some((n) => 'toc' in n)).toBe(true)
  })

  it('starts every section on a new page, with the diagram on landscape pages', () => {
    const sections = nodes(doc.content).filter((n) => Array.isArray(n.stack) && (n.stack as Array<{ tocItem?: boolean }>)[0]?.tocItem)
    expect(sections.every((n) => n.pageBreak === 'before')).toBe(true)
    expect(sections.map((n) => n.pageOrientation ?? '-')).toEqual(['-', 'landscape', 'portrait', '-', '-', '-', '-', '-', '-', '-', '-', '-'])
  })

  it('has a cover with the request, job, score and verdict, and no header or footer on it', () => {
    expect(text).toContain(REAL_JOB.user_request)
    expect(text).toContain(REAL_JOB.job_id)
    expect(text).toContain('68/100')
    expect(text).toContain('Not approved by the critic')
    expect(text).toContain('AWS ARCHITECTURE DESIGN REPORT')
    const header = doc.header as (page: number, count: number, size: { width: number }) => unknown
    const footer = doc.footer as (page: number, count: number) => Content | null
    expect(header(1, 20, { width: 595 })).toBeNull()
    expect(footer(1, 20)).toBeNull()
    expect(textOf(footer(3, 20))).toContain('Page 3 of 20')
  })

  it('includes every service with its purpose and reason', () => {
    for (const service of REAL_LIKE_RESULT.architecture.services) {
      expect(text).toContain(service.name)
      expect(text).toContain(service.purpose)
      expect(text).toContain(service.justification)
    }
  })

  it('includes every data-flow step, specialist recommendation and risk', () => {
    for (const step of REAL_LIKE_RESULT.architecture.data_flow) expect(text).toContain(step.description)
    for (const key of ['compute_analysis', 'database_analysis', 'networking_analysis', 'security_analysis', 'reliability_analysis'] as const) {
      const analysis = REAL_LIKE_RESULT[key]
      for (const line of [...analysis.recommendations, ...analysis.risks]) expect(text, key).toContain(line)
      expect(text).toContain(analysis.reasoning)
    }
  })

  it('includes the complete final report, every field, under its own title', () => {
    for (const section of REPORT_SECTIONS) {
      expect(text).toContain(section.title)
      const value = REAL_LIKE_RESULT.final_report[section.key as keyof typeof REAL_LIKE_RESULT.final_report]
      for (const line of Array.isArray(value) ? value : [value]) if (line) expect(text, section.key).toContain(line)
    }
  })

  it('includes the cost analysis as written, with relative levels only', () => {
    const cost = REAL_LIKE_RESULT.cost_analysis
    for (const line of [cost.estimated_monthly_range, cost.disclaimer, ...cost.major_cost_drivers, ...cost.optimizations, ...cost.trade_offs]) expect(text).toContain(line)
    expect(text).toContain('not amounts or percentages')
  })

  it('invents no money figures or percentages: every one in the report is in the saved result', () => {
    const source = JSON.stringify(REAL_LIKE_RESULT) + REAL_JOB.user_request
    for (const figure of text.match(/\$[\d,.]+[kKmM]?|\b\d+(?:\.\d+)?%/g) ?? []) expect(source, figure).toContain(figure)
  })

  it('treats required changes as blocking and states the rule', () => {
    expect(text).toContain('Blocking: required changes')
    expect(text).toContain('ArchonAI does not label findings as blocking')
    for (const change of REAL_LIKE_RESULT.critic_review.required_changes) expect(text).toContain(change)
    for (const issue of REAL_LIKE_RESULT.critic_review.issues) expect(text).toContain(issue.issue)
  })

  it('lists every trace step in order and says timestamps are not recorded', () => {
    for (const entry of REAL_LIKE_RESULT.execution_trace) expect(text).toContain(entry.action)
    expect(text).toContain('Not recorded: the trace stores the order of steps, not their times.')
  })

  it('says what the result does not contain instead of drawing it', () => {
    expect(text).toContain('VPCs, availability zones and subnets are not drawn because the generated result does not describe them.')
    expect(text).toContain('It does not record configuration or sizing, so none is shown.')
  })

  it('uses no characters the bundled font cannot draw (such as arrows)', () => {
    expect(text).not.toMatch(/[→←⇒➝]/)
  })

  it('sizes every figure block to fit on one page (pdfmake drops a block taller than a page)', () => {
    for (const result of [REAL_LIKE_RESULT, REAL_LIKE_APPROVED, largeResult(28, 30), largeResult(60, 80)]) {
      for (const node of nodes(build(result).content).filter((n) => typeof n.svg === 'string' && Array.isArray(n.fit))) {
        const [, height] = node.fit as [number, number]
        expect(height + FIGURE.headingAllowance).toBeLessThanOrEqual(FIGURE.pageHeight)
      }
    }
  })
})

describe('report document: missing data', () => {
  it('builds from an almost empty result without throwing, saying what is missing', () => {
    const doc = build({ approved: false } as unknown as ArchitectureResult, { job_id: 'abc12345', user_request: '' })
    const text = textOf(doc.content)
    expect(headings(doc)).toHaveLength(12)
    expect(text).toContain('Not provided in the generated result.')
    expect(text).toContain('The generated result has no data-flow steps, so there is no diagram to draw.')
    expect(text).toContain('No services are listed in the generated result.')
    expect(text).toContain('The result has no execution trace.')
  })

  it('handles wrong types inside the result', () => {
    const odd = { ...REAL_LIKE_RESULT, architecture: { services: 'nope', data_flow: [null, 5], summary: 42 }, critic_review: null, execution_trace: 'x' } as unknown as ArchitectureResult
    expect(() => build(odd)).not.toThrow()
  })
})

describe('names', () => {
  it('the project name comes from the application type', () => {
    expect(projectName(REAL_LIKE_RESULT)).toBe('Test E-commerce Platform')
    expect(projectName({} as ArchitectureResult)).toBe('AWS Architecture')
  })

  it('the file name is archonai-{project}-{short job id}.pdf', () => {
    expect(pdfFilename(REAL_LIKE_RESULT, '2c9cd4ce-5521-4fd8-9077-99ed27d0b570')).toBe('archonai-test-e-commerce-platform-2c9cd4ce.pdf')
    expect(pdfFilename({} as ArchitectureResult, '../../etc')).toBe('archonai-aws-architecture-etc.pdf')
    expect(pdfFilename({ requirements: { application_type: 'Café / Bäckerei — Order App!!' } } as unknown as ArchitectureResult, 'abcdef1234')).toBe('archonai-cafe-backerei-order-app-abcdef12.pdf')
  })
})
