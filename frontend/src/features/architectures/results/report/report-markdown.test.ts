import { describe, expect, it } from 'vitest'

import { REAL_REPORT, REAL_REPORT_JOB_ID } from '@/test/real-report'
import type { FinalReport } from '@/types/api'

import { REPORT_SECTIONS } from './report-content'
import { escapeMarkdownLine, NONE_LISTED, NOT_PROVIDED, REPORT_TITLE, reportFilename, reportToMarkdown } from './report-markdown'

/** Undo backslash escapes, as a Markdown renderer would, to compare with the original text. */
const unescape = (md: string) => md.replace(/\\([!-/:-@[-`{-~])/g, '$1')

/** The body under each `## ` heading, in document order. */
const bodies = (md: string) =>
  md
    .split(/^## /m)
    .slice(1)
    .map((chunk) => {
      const [heading, ...rest] = chunk.split('\n')
      return [heading, rest.join('\n').trim()] as const
    })

const EMPTY: FinalReport = {
  executive_summary: '',
  requirements_summary: '',
  architecture_overview: '',
  aws_services_summary: '',
  data_flow_summary: '',
  scalability_strategy: '',
  high_availability_strategy: '',
  security_summary: '',
  reliability_summary: '',
  observability_summary: '',
  cost_summary: '',
  bottlenecks: [],
  trade_offs: [],
  critic_findings_summary: '',
  final_recommendations: [],
  open_recommendations: [],
}

describe('reportToMarkdown with a real report (job 2c9cd4ce)', () => {
  const md = reportToMarkdown(REAL_REPORT, REAL_REPORT_JOB_ID)

  it('starts with the title and job ID', () => {
    expect(md.startsWith(`# ${REPORT_TITLE}\n\nJob ID: ${REAL_REPORT_JOB_ID}\n\n## Executive summary\n`)).toBe(true)
    expect(md.endsWith('\n')).toBe(true)
  })

  it('has all sixteen sections as headings, in the backend order', () => {
    expect(bodies(md).map(([heading]) => heading)).toEqual(REPORT_SECTIONS.map((s) => s.title))
  })

  it('keeps every text section and every list item with its original wording and order', () => {
    const byHeading = Object.fromEntries(bodies(md))
    for (const section of REPORT_SECTIONS) {
      const body = byHeading[section.title]
      if (section.kind === 'text') {
        expect(unescape(body)).toBe(REAL_REPORT[section.key])
      } else {
        const ordered = section.key === 'final_recommendations'
        const expected = REAL_REPORT[section.key].map((item, i) => `${ordered ? `${i + 1}.` : '-'} ${item}`).join('\n')
        expect(unescape(body)).toBe(expected)
      }
    }
  })

  it('escapes only what Markdown would misread in the real text', () => {
    // "~99.9%" would start strikethrough in GFM; "->" and "$" are left alone.
    expect(md).toContain('\\~99.9%')
    expect(md).toContain('User -> CloudFront + WAF')
    expect(md).toMatch(/\$\d/)
  })
})

describe('reportToMarkdown edge cases', () => {
  it('keeps paragraph breaks and turns single line breaks into hard breaks', () => {
    const md = reportToMarkdown({ ...EMPTY, executive_summary: 'Line one\r\nLine two\n\n\nSecond paragraph.  ' })
    expect(bodies(md)[0][1]).toBe('Line one\\\nLine two\n\nSecond paragraph.')
  })

  it('indents the continuation lines of a multiline list item', () => {
    const md = reportToMarkdown({ ...EMPTY, bottlenecks: ['First line\nsecond line', 'Next'], final_recommendations: ['A\nB'] })
    const byHeading = Object.fromEntries(bodies(md))
    expect(byHeading.Bottlenecks).toBe('- First line\\\n  second line\n- Next')
    expect(byHeading['Final recommendations']).toBe('1. A\\\n   B')
  })

  it.each([
    ['*bold* and _under_', '\\*bold\\* and \\_under\\_'],
    ['`code` [link](x) <b>html</b>', '\\`code\\` \\[link\\](x) \\<b>html\\</b>'],
    ['~~struck~~ and C:\\path', '\\~\\~struck\\~\\~ and C:\\\\path'],
    ['&amp; &#169; & plain', '\\&amp; \\&#169; & plain'],
    ['# not a heading', '\\# not a heading'],
    ['> not a quote', '\\> not a quote'],
    ['- not a list', '\\- not a list'],
    ['+ not a list', '\\+ not a list'],
    ['12. not a list', '12\\. not a list'],
    ['---', '\\---'],
    ['===', '\\==='],
    ['Costs $5 -> $10 (≈ 100%) – ok → “quoted” ünïcödé 日本', 'Costs $5 -> $10 (≈ 100%) – ok → “quoted” ünïcödé 日本'],
  ])('escapes %j', (input, expected) => {
    expect(escapeMarkdownLine(input)).toBe(expected)
    expect(unescape(expected)).toBe(input)
  })

  it('marks empty sections and lists instead of dropping them', () => {
    const md = reportToMarkdown({ ...EMPTY, executive_summary: 'Only this.', trade_offs: ['One'] })
    const byHeading = Object.fromEntries(bodies(md))
    expect(byHeading['Executive summary']).toBe('Only this.')
    expect(byHeading['Trade-offs']).toBe('- One')
    expect(byHeading['Cost summary']).toBe(NOT_PROVIDED)
    expect(byHeading['Open recommendations']).toBe(NONE_LISTED)
    expect(bodies(md)).toHaveLength(16)
  })

  it('handles an absent report and a missing job ID', () => {
    const md = reportToMarkdown(undefined)
    expect(md).not.toContain('Job ID')
    expect(md.startsWith(`# ${REPORT_TITLE}\n\n## Executive summary\n`)).toBe(true)
    expect(bodies(md).map(([, body]) => body)).toEqual(REPORT_SECTIONS.map((s) => (s.kind === 'text' ? NOT_PROVIDED : NONE_LISTED)))
    expect(reportToMarkdown(EMPTY, '   ')).not.toContain('Job ID')
  })
})

describe('reportFilename', () => {
  it.each([
    [REAL_REPORT_JOB_ID, `archonai-report-${REAL_REPORT_JOB_ID}.md`],
    ['job-1', 'archonai-report-job-1.md'],
    ['../my job/ü', 'archonai-report-my-job.md'],
    [undefined, 'archonai-report.md'],
    ['', 'archonai-report.md'],
    ['///', 'archonai-report.md'],
  ])('%j -> %s', (jobId, expected) => {
    expect(reportFilename(jobId)).toBe(expected)
  })
})
