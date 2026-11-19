/**
 * The real browser build of pdfmake, run in jsdom: the export produces a PDF file from the saved
 * result, named after the project and job, without making any request.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createArchitecturePdf, downloadArchitecturePdf } from './generate-pdf'
import { REAL_JOB, REAL_LIKE_RESULT } from './pdf-fixtures'

const read = (blob: Blob) =>
  new Promise<Uint8Array>((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer))
    reader.readAsArrayBuffer(blob)
  })

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('PDF export in the browser', () => {
  it('builds a PDF from the saved result without any request', async () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('the PDF export must not make requests')
    })
    vi.stubGlobal('fetch', fetchSpy)
    const XHR = vi.fn(() => {
      throw new Error('the PDF export must not make requests')
    })
    vi.stubGlobal('XMLHttpRequest', XHR)

    const blob = await createArchitecturePdf(REAL_LIKE_RESULT, REAL_JOB, new Date('2026-11-19T10:00:00Z'))
    const bytes = await read(blob)
    expect(blob.type).toBe('application/pdf')
    expect(new TextDecoder().decode(bytes.slice(0, 5))).toBe('%PDF-')
    expect(bytes.length).toBeGreaterThan(50_000)
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(XHR).not.toHaveBeenCalled()
  }, 120_000)

  it('saves it as archonai-{project}-{job}.pdf', async () => {
    const blobs: Blob[] = []
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: (blob: Blob) => (blobs.push(blob), 'blob:test'), revokeObjectURL: () => {} }))
    const clicked: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this.download)
    })
    await downloadArchitecturePdf(REAL_LIKE_RESULT, REAL_JOB)
    expect(clicked).toEqual(['archonai-test-e-commerce-platform-2c9cd4ce.pdf'])
    expect(blobs[0].type).toBe('application/pdf')
  }, 120_000)
})
