import { FileDown } from 'lucide-react'
import { useRef, useState } from 'react'

import { Button } from '@/components/ui'
import { toast } from '@/stores/toast.store'
import type { ArchitectureResult } from '@/types/api'

import type { PdfJob } from './generate-pdf'

/**
 * Download the full architecture report as a PDF, built in the browser from the saved result. The
 * generator is loaded only when clicked; a second click while it runs is ignored.
 */
export function DownloadPdfButton({ result, job }: { result: ArchitectureResult; job: PdfJob }) {
  const [busy, setBusy] = useState(false)
  const running = useRef(false)

  const handleClick = async () => {
    if (running.current) return
    running.current = true
    setBusy(true)
    try {
      const { downloadArchitecturePdf } = await import('./generate-pdf')
      await downloadArchitecturePdf(result, job)
    } catch (error) {
      // For whoever opens the browser console; the user gets the plain message below.
      console.error('PDF export failed', error)
      toast({ tone: 'danger', title: "Couldn't create the PDF", description: 'Something went wrong while building the report. Please try again.' })
    } finally {
      running.current = false
      setBusy(false)
    }
  }

  return (
    <Button variant="outline" onClick={() => void handleClick()} loading={busy} aria-busy={busy || undefined}>
      {!busy && <FileDown className="size-4" aria-hidden="true" />}
      {busy ? 'Creating PDF…' : 'Download PDF'}
    </Button>
  )
}
