import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeResult } from '@/test/job-fixtures'
import { REAL_REPORT, REAL_REPORT_JOB_ID } from '@/test/real-report'
import type { ArchitectureResult, FinalReport } from '@/types/api'

import { REPORT_SECTIONS } from './report-content'
import { reportToMarkdown } from './report-markdown'
import { ReportTab } from './ReportTab'

const renderReport = (report: FinalReport) => render(<ReportTab result={makeResult({ final_report: report })} jobId={REAL_REPORT_JOB_ID} />)

const section = (title: string) => screen.getByRole('heading', { name: title }).closest('section') as HTMLElement
const items = (title: string) => within(section(title)).getAllByRole('listitem').map((li) => li.textContent)

const EMPTY: FinalReport = {
  ...REAL_REPORT,
  ...Object.fromEntries(REPORT_SECTIONS.map((s) => [s.key, s.kind === 'text' ? '' : []])),
} as FinalReport

/** Capture what the download writes, without touching the network or the file system. */
function captureDownloads() {
  const blobs: Blob[] = []
  const clicked: string[] = []
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: (blob: Blob) => (blobs.push(blob), 'blob:test'), revokeObjectURL: () => {} }))
  const fetchSpy = vi.fn()
  vi.stubGlobal('fetch', fetchSpy)
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this.download)
  })
  // jsdom's Blob has no .text(); FileReader reads it the same way.
  const read = (blob: Blob) =>
    new Promise<string>((resolve) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.readAsText(blob)
    })
  return { blobs, clicked, fetchSpy, read, restore: () => click.mockRestore() }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ReportTab with a real report (job 2c9cd4ce)', () => {
  it('renders all sixteen sections in the backend order', () => {
    renderReport(REAL_REPORT)
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(headings).toEqual(REPORT_SECTIONS.map((s) => s.title))
  })

  it('shows every text section with its original wording, untruncated', () => {
    renderReport(REAL_REPORT)
    for (const s of REPORT_SECTIONS) {
      if (s.kind !== 'text') continue
      const p = section(s.title).querySelector('p') as HTMLElement
      expect(p.textContent).toBe(REAL_REPORT[s.key])
    }
    expect(REAL_REPORT.aws_services_summary.length).toBeGreaterThan(800)
  })

  it('makes the executive summary the prominent first section', () => {
    renderReport(REAL_REPORT)
    const executive = section('Executive summary')
    const first = screen.getAllByRole('heading', { level: 3 })[0]
    expect(first.textContent).toBe('Executive summary')
    expect(executive.querySelector('p')?.className).toContain('text-section-title')
    expect(section('Cost summary').querySelector('p')?.className).not.toContain('text-section-title')
  })

  it('shows all four lists in their original order, final and open recommendations kept apart', () => {
    renderReport(REAL_REPORT)
    expect(items('Bottlenecks')).toEqual(REAL_REPORT.bottlenecks)
    expect(items('Trade-offs')).toEqual(REAL_REPORT.trade_offs)
    expect(items('Final recommendations')).toEqual(REAL_REPORT.final_recommendations)
    expect(items('Open recommendations')).toEqual(REAL_REPORT.open_recommendations)
    expect(section('Final recommendations').querySelector('ol')).toBeTruthy()
    expect(section('Final recommendations').contains(section('Open recommendations'))).toBe(false)
    expect(section('Open recommendations').className).toContain('bg-info/10')
    expect(within(section('Open recommendations')).getByText(/not included in the final architecture/)).toBeTruthy()
  })

  it('distinguishes bottlenecks from trade-offs', () => {
    renderReport(REAL_REPORT)
    expect(section('Bottlenecks').querySelector('svg')?.getAttribute('class')).toContain('text-warning')
    expect(section('Trade-offs').querySelector('svg')?.getAttribute('class')).toContain('text-muted-foreground')
  })
})

describe('ReportTab edge cases', () => {
  it('keeps line breaks and special characters as written', () => {
    const text = 'First line with <b>tags</b> & *stars*\nSecond line: $5 -> ~10% – “ok”\n\nNew paragraph 日本'
    renderReport({ ...REAL_REPORT, security_summary: text, bottlenecks: ['Item one\nstill item one', '<script>alert(1)</script>'] })
    const p = section('Security summary').querySelector('p') as HTMLElement
    expect(p.textContent).toBe(text)
    expect(p.className).toContain('whitespace-pre-line')
    expect(p.querySelector('b')).toBeNull()
    expect(items('Bottlenecks')).toEqual(['Item one\nstill item one', '<script>alert(1)</script>'])
    expect(document.querySelector('script')).toBeNull()
  })

  it('an empty text section gets its own empty state; the others still render', () => {
    renderReport({ ...REAL_REPORT, data_flow_summary: '   ', executive_summary: '' })
    expect(within(section('Data flow summary')).getByText('Not provided in this report.')).toBeTruthy()
    expect(within(section('Executive summary')).getByText('Not provided in this report.')).toBeTruthy()
    expect(screen.getAllByText('Not provided in this report.')).toHaveLength(2)
    expect(section('Architecture overview').querySelector('p')?.textContent).toBe(REAL_REPORT.architecture_overview)
  })

  it('empty lists get their own empty state', () => {
    renderReport({ ...REAL_REPORT, bottlenecks: [], trade_offs: [], final_recommendations: [], open_recommendations: [] })
    for (const title of ['Bottlenecks', 'Trade-offs', 'Final recommendations', 'Open recommendations']) {
      expect(within(section(title)).getByText('None listed in this report.')).toBeTruthy()
      expect(within(section(title)).queryByRole('listitem')).toBeNull()
    }
    expect(section('Open recommendations').className).not.toContain('bg-info/10')
  })

  it('an entirely empty report shows one overall empty state and no download', () => {
    renderReport(EMPTY)
    expect(screen.getByText('No final report')).toBeTruthy()
    expect(screen.queryByRole('heading', { level: 3 })).toBeNull()
    expect(screen.queryByRole('button', { name: /Download Markdown/ })).toBeNull()
  })

  it('a result with no final_report at all does not crash', () => {
    const result: Record<string, unknown> = { ...makeResult() }
    delete result.final_report
    render(<ReportTab result={result as unknown as ArchitectureResult} jobId="job-1" />)
    expect(screen.getByText('No final report')).toBeTruthy()
  })
})

describe('ReportTab Markdown download', () => {
  it('downloads the Markdown built in the browser, with no request', async () => {
    const d = captureDownloads()
    renderReport(REAL_REPORT)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Download Markdown' }))
    expect(d.clicked).toEqual([`archonai-report-${REAL_REPORT_JOB_ID}.md`])
    expect(d.blobs[0].type).toBe('text/markdown;charset=utf-8')
    expect(await d.read(d.blobs[0])).toBe(reportToMarkdown(REAL_REPORT, REAL_REPORT_JOB_ID))
    expect(d.fetchSpy).not.toHaveBeenCalled()
    d.restore()
  })

  it('works from the keyboard', async () => {
    const d = captureDownloads()
    renderReport(REAL_REPORT)
    const user = userEvent.setup()
    await user.tab()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Download Markdown' }))
    await user.keyboard('{Enter}')
    await user.keyboard(' ')
    expect(d.clicked).toHaveLength(2)
    d.restore()
  })

  it('without a job ID: generic filename and no Job ID line', async () => {
    const d = captureDownloads()
    render(<ReportTab result={makeResult({ final_report: REAL_REPORT })} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Download Markdown' }))
    expect(d.clicked).toEqual(['archonai-report.md'])
    const md = await d.read(d.blobs[0])
    expect(md).not.toContain('Job ID')
    expect(md).toBe(reportToMarkdown(REAL_REPORT))
    d.restore()
  })

  it('keeps special characters intact in the downloaded file (UTF-8)', async () => {
    const d = captureDownloads()
    renderReport({ ...REAL_REPORT, executive_summary: 'Café – 日本 → “quotes” ~99.9%' })
    await userEvent.setup().click(screen.getByRole('button', { name: 'Download Markdown' }))
    expect(await d.read(d.blobs[0])).toContain('Café – 日本 → “quotes” \\~99.9%')
    d.restore()
  })
})
