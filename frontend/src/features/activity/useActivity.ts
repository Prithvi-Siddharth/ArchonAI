import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { fetchJobHistory, type JobHistoryParams } from '@/api/architectures'
import { HISTORY_POLL_MS, HISTORY_QUERY_KEY, invalidateJobHistory } from '@/features/architectures/history/useJobHistory'
import { POLL_INTERVAL_MS } from '@/features/architectures/useJob'
import type { JobHistoryItem, JobHistoryResponse } from '@/types/api'

/** The Activity page reads this many of the newest jobs; unfinished jobs are almost always among them. */
export const ACTIVITY_LIMIT = 20
/** Finished jobs shown under "Recently finished". */
export const RECENT_FINISHED = 5

const ACTIVITY_PARAMS: JobHistoryParams = { limit: ACTIVITY_LIMIT, offset: 0 }
// Only the counts are needed for the sidebar badge, so one row is enough.
const COUNT_PARAMS: JobHistoryParams = { limit: 1, offset: 0 }

/** Queued plus running jobs across the whole account (the counts ignore the page size). */
export const unfinishedCount = (data: JobHistoryResponse | undefined) => (data ? data.counts.queued + data.counts.running : 0)

const isUnfinished = (item: JobHistoryItem) => item.status === 'queued' || item.status === 'running'

/**
 * Running jobs first, then queued jobs in the order they will run (oldest first).
 * The list arrives newest first.
 */
function activeOrder(items: JobHistoryItem[]): JobHistoryItem[] {
  const running = items.filter((item) => item.status === 'running')
  const queued = items.filter((item) => item.status === 'queued').reverse()
  return [...running, ...queued]
}

/**
 * The signed-in user's jobs in progress and the last few that finished. While anything is
 * unfinished the list is re-read as often as a job page polls, and when a job finishes every
 * other history list (dashboard, History page, sidebar badge) is refreshed too.
 */
export function useActivity() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: [...HISTORY_QUERY_KEY, ACTIVITY_PARAMS],
    queryFn: ({ signal }) => fetchJobHistory(ACTIVITY_PARAMS, signal),
    refetchInterval: (q) => (unfinishedCount(q.state.data) > 0 ? POLL_INTERVAL_MS : false),
    refetchIntervalInBackground: false,
  })

  const unfinished = unfinishedCount(query.data)
  const previous = useRef<number | null>(null)
  useEffect(() => {
    if (!query.data) return
    if (previous.current !== null && unfinished < previous.current) void invalidateJobHistory(queryClient)
    previous.current = unfinished
  }, [query.data, unfinished, queryClient])

  const items = query.data?.items ?? []
  const active = activeOrder(items)
  const finished = items.filter((item) => !isUnfinished(item)).slice(0, RECENT_FINISHED)
  // Unfinished jobs older than the newest ACTIVITY_LIMIT jobs aren't in the list.
  const hiddenActive = Math.max(0, unfinished - active.length)
  return { query, active, finished, hiddenActive }
}

/** How many of the user's jobs are queued or running, for the sidebar badge. Polls only while some are. */
export function useActiveJobCount(): number {
  const query = useQuery({
    queryKey: [...HISTORY_QUERY_KEY, COUNT_PARAMS],
    queryFn: ({ signal }) => fetchJobHistory(COUNT_PARAMS, signal),
    refetchInterval: (q) => (unfinishedCount(q.state.data) > 0 ? HISTORY_POLL_MS : false),
    refetchIntervalInBackground: false,
  })
  return unfinishedCount(query.data)
}
