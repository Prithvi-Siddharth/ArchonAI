import { queryOptions, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { fetchJob } from '@/api/architectures'
import { ApiError } from '@/api/client'
import type { JobStatusResponse } from '@/types/api'

import { invalidateJobHistory } from './history/useJobHistory'
import { isFinalJob } from './job-phase'

/** How often the tracking page re-reads an unfinished job. */
export const POLL_INTERVAL_MS = 5_000

/** One cache entry per job, shared by the dashboard and the tracking page. */
export function jobQueryKey(jobId: string) {
  return ['architectures', 'job', jobId] as const
}

/**
 * GET /jobs/{id}. Finished jobs are cached for good; unfinished ones are
 * stale at once, so opening a page that shows them reads them again.
 */
export function jobQueryOptions(jobId: string) {
  return queryOptions({
    queryKey: jobQueryKey(jobId),
    queryFn: ({ signal }) => fetchJob(jobId, signal),
    staleTime: (query) => (isFinalJob(query.state.data) ? Infinity : 0),
  })
}

/**
 * Polling rule: every 5 s while the job is queued or running. Stops for a
 * finished job, for a 404, and when the first load failed (the page then
 * offers "Try again" instead of retrying blindly). After the first success, a
 * temporary failure doesn't stop polling: the last known status stays on screen.
 */
export function jobRefetchInterval(query: { state: { data?: JobStatusResponse; error: unknown } }): number | false {
  const { data, error } = query.state
  if (isFinalJob(data)) return false
  if (error instanceof ApiError && error.status === 404) return false
  if (!data && error) return false
  return POLL_INTERVAL_MS
}

/**
 * A job's live status for the tracking page. TanStack Query skips interval
 * refetches while the tab is hidden (refetchIntervalInBackground is false) and
 * refreshes an unfinished job as soon as the tab is visible again.
 */
export function useJob(jobId: string) {
  const query = useQuery({
    ...jobQueryOptions(jobId),
    refetchInterval: jobRefetchInterval,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  })
  // When the job finishes, the history (History page, dashboard) is out of date.
  const queryClient = useQueryClient()
  const finishedStatus = isFinalJob(query.data) ? query.data?.status : undefined
  useEffect(() => {
    if (finishedStatus) void invalidateJobHistory(queryClient)
  }, [finishedStatus, queryClient])
  return query
}
