import { keepPreviousData, useQuery, type QueryClient } from '@tanstack/react-query'

import { fetchJobHistory, type JobHistoryParams } from '@/api/architectures'
import type { JobHistoryResponse } from '@/types/api'

/** Every history list (History page, dashboard preview) starts with this key. */
export const HISTORY_QUERY_KEY = ['architectures', 'history'] as const

/** While a listed job is queued or running, re-read the list this often. */
export const HISTORY_POLL_MS = 10_000

const hasUnfinished = (data: JobHistoryResponse | undefined) =>
  Boolean(data?.items.some((item) => item.status === 'queued' || item.status === 'running'))

/**
 * One page of the signed-in user's jobs. The previous page stays on screen while the next loads.
 * Polling pauses while the tab is hidden, unless `pollInBackground` is set (the finish alerts need
 * to notice a job ending while you are in another tab).
 */
export function useJobHistory(params: JobHistoryParams, { pollInBackground = false }: { pollInBackground?: boolean } = {}) {
  return useQuery({
    queryKey: [...HISTORY_QUERY_KEY, params],
    queryFn: ({ signal }) => fetchJobHistory(params, signal),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (hasUnfinished(query.state.data) ? HISTORY_POLL_MS : false),
    refetchIntervalInBackground: pollInBackground,
  })
}

/** Mark every history list out of date (after a submission or a job finishing). */
export function invalidateJobHistory(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: HISTORY_QUERY_KEY })
}
