/**
 * Builds the PDF in the browser from the saved result and downloads it. Loaded on demand (only when
 * Download PDF is clicked), so pdfmake, its fonts and the AWS icons never weigh on the normal app.
 * No request is made: the fonts are bundled, and pdfmake is told to refuse any URL.
 */
import { APP_VERSION } from '@/features/about/about-tabs'
import type { ArchitectureResult } from '@/types/api'
import { downloadBlob } from '@/utils/download'

import { ICON_SVGS } from './icon-svgs'
import { pdfFilename } from './pdf-filename'
import { buildReportDocument } from './report-document'

export interface PdfJob {
  job_id: string
  user_request?: string | null
  created_at?: string | null
  finished_at?: string | null
}

type PdfMake = typeof import('pdfmake/build/pdfmake')

let ready: Promise<PdfMake> | null = null

/** pdfmake with its bundled Roboto fonts, set up once. */
function loadPdfMake(): Promise<PdfMake> {
  ready ??= Promise.all([import('pdfmake/build/pdfmake'), import('pdfmake/build/vfs_fonts')])
    .then(([pdfMakeModule, vfsModule]) => {
      const pdfMake = ((pdfMakeModule as unknown as { default?: PdfMake }).default ?? pdfMakeModule) as PdfMake
      const vfs = (vfsModule as unknown as { default?: Record<string, string> }).default ?? (vfsModule as unknown as Record<string, string>)
      pdfMake.addVirtualFileSystem(vfs)
      // Nothing in the document points to a URL; refuse any, so the export never makes a request.
      pdfMake.setUrlAccessPolicy(() => false)
      return pdfMake
    })
    .catch((error: unknown) => {
      ready = null // let a later click try again
      throw error
    })
  return ready
}

/** The report as a PDF Blob. */
export async function createArchitecturePdf(result: ArchitectureResult, job: PdfJob, now = new Date()): Promise<Blob> {
  const pdfMake = await loadPdfMake()
  const definition = buildReportDocument({
    result,
    jobId: job.job_id,
    request: job.user_request ?? null,
    createdAt: job.created_at ?? null,
    finishedAt: job.finished_at ?? null,
    generatedAt: now,
    appVersion: APP_VERSION,
    icons: (key) => ICON_SVGS.get(key),
  })
  return pdfMake.createPdf(definition).getBlob()
}

/** Build the PDF and save it as archonai-{project}-{job}.pdf. */
export async function downloadArchitecturePdf(result: ArchitectureResult, job: PdfJob): Promise<void> {
  const blob = await createArchitecturePdf(result, job)
  downloadBlob(pdfFilename(result, job.job_id), blob)
}
