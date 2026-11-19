// @vitest-environment node
/**
 * Renders real PDFs with pdfmake in Node (the same library and fonts the browser uses) from real
 * stored results. Set PDF_OUT=<folder> to keep the files for a visual check.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'

import type { TDocumentDefinitions } from 'pdfmake/interfaces'
import { describe, expect, it } from 'vitest'

import { makeResult } from '@/test/job-fixtures'
import type { ArchitectureResult } from '@/types/api'

import { ICON_SVGS } from './icon-svgs'
import { largeResult, REAL_JOB, REAL_LIKE_APPROVED, REAL_LIKE_RESULT } from './pdf-fixtures'
import { buildReportDocument } from './report-document'

const pdfmake = createRequire(import.meta.url)('pdfmake') as typeof import('pdfmake')
const FONTS = path.resolve('node_modules/pdfmake/fonts/Roboto')
pdfmake.setFonts({
  Roboto: {
    normal: path.join(FONTS, 'Roboto-Regular.ttf'),
    bold: path.join(FONTS, 'Roboto-Medium.ttf'),
    italics: path.join(FONTS, 'Roboto-Italic.ttf'),
    bolditalics: path.join(FONTS, 'Roboto-MediumItalic.ttf'),
  },
})
pdfmake.setUrlAccessPolicy(() => false)
pdfmake.setLocalAccessPolicy((file) => path.resolve(file).startsWith(FONTS))

const OUT = process.env.PDF_OUT

function definition(result: ArchitectureResult, job = REAL_JOB): TDocumentDefinitions {
  return buildReportDocument({
    result,
    jobId: job.job_id,
    request: job.user_request,
    createdAt: job.created_at,
    finishedAt: job.finished_at,
    generatedAt: new Date('2026-11-19T10:00:00Z'),
    appVersion: '1.0.0',
    icons: (key) => ICON_SVGS.get(key),
  })
}

async function render(name: string, result: ArchitectureResult, job = REAL_JOB): Promise<{ bytes: Buffer; pages: number }> {
  const bytes = (await pdfmake.createPdf(definition(result, job)).getBuffer()) as Buffer
  if (OUT) {
    mkdirSync(OUT, { recursive: true })
    writeFileSync(path.join(OUT, `${name}.pdf`), bytes)
  }
  const pages = (bytes.toString('latin1').match(/\/Type \/Page\b/g) ?? []).length
  return { bytes, pages }
}

describe('PDF rendering', () => {
  it('renders a complete report from a real not-approved result', async () => {
    const { bytes, pages } = await render('real-not-approved', REAL_LIKE_RESULT)
    expect(bytes.subarray(0, 5).toString()).toBe('%PDF-')
    expect(pages).toBeGreaterThanOrEqual(14) // cover, contents and twelve sections, each starting on a new page
  }, 60_000)

  it('renders a real approved result with a back-edge data flow and no cost breakdown', async () => {
    const { pages } = await render('real-approved', REAL_LIKE_APPROVED)
    expect(pages).toBeGreaterThanOrEqual(14)
  }, 60_000)

  it('renders a large architecture without failing', async () => {
    const { pages } = await render('large', largeResult(28, 30))
    expect(pages).toBeGreaterThanOrEqual(16)
  }, 90_000)

  it('renders even an almost empty result (missing fields never crash it)', async () => {
    const empty = { approved: false } as unknown as ArchitectureResult
    const { pages } = await render('empty', empty, { ...REAL_JOB, user_request: '' })
    expect(pages).toBeGreaterThanOrEqual(14)
  }, 60_000)

  it('renders a minimal valid result', async () => {
    const minimal = makeResult({ architecture: { summary: 'One function.', services: [{ name: 'AWS Lambda', category: 'Compute', purpose: 'Runs the code.', justification: 'Serverless.' }], data_flow: [], version: 1, change_log: [] } })
    const { pages } = await render('minimal', minimal)
    expect(pages).toBeGreaterThanOrEqual(14)
  }, 60_000)
})
