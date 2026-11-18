import { toast } from '@/stores/toast.store'

/** Copy a job id to the clipboard, confirming (or explaining a failure) with a toast. */
export async function copyJobId(jobId: string) {
  try {
    await navigator.clipboard.writeText(jobId)
    toast({ tone: 'success', title: 'Job ID copied' })
  } catch {
    toast({ tone: 'danger', title: "Couldn't copy the job ID", description: 'Select it and copy it manually.' })
  }
}
