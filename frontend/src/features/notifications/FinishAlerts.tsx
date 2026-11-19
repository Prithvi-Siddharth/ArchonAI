import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { useJobHistory } from '@/features/architectures/history/useJobHistory'
import { toast } from '@/stores/toast.store'

import { desktopActive, showDesktop, tabIsAway } from './desktop'
import { alertText, claimAlert, newlyFinished, statusMap, type StatusMap } from './finish-alerts'

/** The same list the Activity page reads (newest 20), so they share one fetch. */
export const WATCHED_JOBS = { limit: 20, offset: 0 } as const

/** True when the user is already looking at this job's page or results, so no alert is needed. */
const isViewing = (pathname: string, jobId: string) => {
  const base = `/architectures/${jobId}`
  return pathname === base || pathname === `${base}/results`
}

/**
 * Mounted once in the app layout (renders nothing). When a job you submitted goes from queued or
 * running to succeeded or failed while you are using the app, it shows a toast, and a desktop
 * notification if you turned those on and the tab is out of sight.
 */
export function FinishAlerts() {
  // Keeps checking while the tab is hidden: that is exactly when a desktop notification is wanted.
  const query = useJobHistory(WATCHED_JOBS, { pollInBackground: true })
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const previous = useRef<StatusMap | null>(null)
  // Read at the moment a job finishes, without restarting the effect on every page change.
  const where = useRef({ pathname, navigate })
  where.current = { pathname, navigate }

  useEffect(() => {
    const items = query.data?.items
    if (!items) return
    // The first read only records what is there: jobs that finished before now never alert.
    const finished = previous.current ? newlyFinished(previous.current, items) : []
    previous.current = statusMap(items)

    for (const job of finished) {
      if (!claimAlert(job.job_id)) continue // another tab already announced it
      const text = alertText(job)
      const open = () => where.current.navigate(text.path)
      if (!isViewing(where.current.pathname, job.job_id)) {
        toast({ tone: text.tone, title: text.title, description: text.body, duration: 12_000, action: { label: text.actionLabel, onClick: open } })
      }
      if (desktopActive() && tabIsAway()) showDesktop(text.title, text.body, job.job_id, open)
    }
  }, [query.data])

  return null
}
