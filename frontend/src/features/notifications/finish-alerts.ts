/**
 * Working out which jobs just finished, from two successive reads of the user's job list.
 * Pure logic, so it is easy to test; the watcher in FinishAlerts.tsx does the showing.
 */
import { requestTitle } from '@/features/architectures/history/HistoryEntry'
import type { JobHistoryItem } from '@/types/api'
import type { JobStatus } from '@/types/architecture'
import { readStorage, writeStorage } from '@/utils/storage'

export type StatusMap = ReadonlyMap<string, JobStatus>

export const statusMap = (items: JobHistoryItem[]): StatusMap => new Map(items.map((item) => [item.job_id, item.status]))

const isUnfinished = (status: JobStatus | undefined) => status === 'queued' || status === 'running'
const isFinished = (status: JobStatus) => status === 'succeeded' || status === 'failed'

/**
 * Jobs that were queued or running in `previous` and are succeeded or failed now. Nothing is
 * reported for jobs that were already finished (or unknown) the first time they were seen, so
 * opening the app never replays old results. A job waiting to retry is still queued, not finished.
 */
export function newlyFinished(previous: StatusMap, items: JobHistoryItem[]): JobHistoryItem[] {
  return items.filter((item) => isFinished(item.status) && isUnfinished(previous.get(item.job_id)))
}

// --- One alert per job, even with several tabs open -----------------------------------------

export const ALERTED_STORAGE_KEY = 'archonai-alerted-jobs'
const REMEMBER = 50

function readAlerted(): string[] {
  try {
    const parsed: unknown = JSON.parse(readStorage(ALERTED_STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

/**
 * True the first time any tab claims this job, false afterwards. Tabs share browser storage, so
 * only one of them announces it. (Two tabs checking in the same instant can still both win; that
 * is rare and harmless.)
 */
export function claimAlert(jobId: string): boolean {
  const alerted = readAlerted()
  if (alerted.includes(jobId)) return false
  writeStorage(ALERTED_STORAGE_KEY, JSON.stringify([...alerted, jobId].slice(-REMEMBER)))
  return true
}

// --- Wording ----------------------------------------------------------------------------------

const clip = (text: string, max: number) => (text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text)

export interface AlertText {
  title: string
  body: string
  tone: 'success' | 'danger'
  /** "View results" or "View job". */
  actionLabel: string
  /** Where the action leads. */
  path: string
}

/** The words and destination for a finished job. */
export function alertText(job: JobHistoryItem): AlertText {
  const request = clip(requestTitle(job.user_request), 70) || 'Your request'
  const id = encodeURIComponent(job.job_id)
  if (job.status === 'succeeded') {
    const withResults = job.summary !== null
    return {
      title: 'Architecture ready',
      body: request,
      tone: 'success',
      actionLabel: withResults ? 'View results' : 'View job',
      path: withResults ? `/architectures/${id}/results` : `/architectures/${id}`,
    }
  }
  return {
    title: 'Generation failed',
    body: job.error?.message ? `${request} — ${clip(job.error.message, 90)}` : request,
    tone: 'danger',
    actionLabel: 'View job',
    path: `/architectures/${id}`,
  }
}
