import { useQueries, type UseQueryResult } from '@tanstack/react-query'

import { ApiError } from '@/api/client'
import { isFinalJob as isFinal } from '@/features/architectures/job-phase'
import { jobQueryOptions } from '@/features/architectures/useJob'
import { useSubmissionsStore } from '@/stores/submissions.store'
import type { ArchitectureSummary, JobStats, JobStatusView } from '@/types/architecture'
import type { JobStatusResponse } from '@/types/api'

/** The dashboard's table shows this many of the (at most 20) saved submissions. */
const RECENT_ROWS = 6

function statusView(query: UseQueryResult<JobStatusResponse>): JobStatusView {
  if (query.data) return { state: 'known', status: query.data.status }
  if (query.isPending) return { state: 'loading' }
  if (query.error instanceof ApiError && query.error.status === 404) return { state: 'not-found' }
  return { state: 'unavailable' }
}

/**
 * Jobs submitted from this browser, each with its status read once from
 * GET /jobs/{id} when the dashboard opens (no polling). Finished jobs are not
 * read again; `refresh` re-reads the rest.
 */
export function useDashboardData() {
  const submissions = useSubmissionsStore((state) => state.submissions)

  const queries = useQueries({
    // Shared with the tracking page; the dashboard reads each once and does not poll.
    queries: submissions.map((submission) => jobQueryOptions(submission.jobId)),
  })

  const rows: ArchitectureSummary[] = submissions.map((submission, index) => {
    const query = queries[index]
    const job = query.data
    const result = job?.status === 'succeeded' ? job.result : null
    return {
      jobId: submission.jobId,
      request: submission.requestPreview,
      status: statusView(query),
      createdAt: job?.created_at ?? submission.submittedAt,
      serviceCount: result ? result.architecture.services.length : null,
      criticScore: result ? result.critic_review.score : null,
    }
  })

  const stats: JobStats = {
    total: submissions.length,
    succeeded: queries.filter((query) => query.data?.status === 'succeeded').length,
    failed: queries.filter((query) => query.data?.status === 'failed').length,
  }

  const refresh = () => Promise.all(queries.filter((query) => !isFinal(query.data)).map((query) => query.refetch()))

  return {
    recent: rows.slice(0, RECENT_ROWS),
    stats,
    statsLoading: queries.some((query) => query.isPending),
    refresh,
    refreshing: queries.some((query) => query.isFetching),
  }
}
