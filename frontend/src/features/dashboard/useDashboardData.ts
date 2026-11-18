import { useJobHistory } from '@/features/architectures/history/useJobHistory'
import type { JobStats } from '@/types/architecture'

/** The dashboard shows this many of the newest jobs; the History page has the rest. */
export const RECENT_ROWS = 6

/**
 * The signed-in user's newest jobs and their status counts, from the same history API
 * (and cache) as the History page. Re-read automatically while a listed job is unfinished.
 */
export function useDashboardData() {
  const query = useJobHistory({ limit: RECENT_ROWS, offset: 0 })
  const counts = query.data?.counts
  const stats: JobStats | null = counts
    ? { total: counts.queued + counts.running + counts.succeeded + counts.failed, succeeded: counts.succeeded, failed: counts.failed }
    : null
  return { query, recent: query.data?.items ?? [], stats }
}
