import type { ArchitectureResult } from '@/types/api'

import { projectName } from './report-document'

/** "archonai-e-commerce-platform-2c9cd4ce.pdf": the project name as a short ASCII slug, then the short job id. */
export function pdfFilename(result: ArchitectureResult, jobId: string): string {
  const slug =
    projectName(result)
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '') // drop the accents NFKD separated out: "ä" -> "a"
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 48)
      .replace(/-+$/, '') || 'architecture'
  const id = jobId.replace(/[^A-Za-z0-9-]/g, '').slice(0, 8) || 'job'
  return `archonai-${slug}-${id}.pdf`
}
