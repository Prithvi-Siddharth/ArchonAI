import { useQuery } from '@tanstack/react-query'

import { fetchJobMonitoring } from '@/api/monitoring'

/** While more log lines may still arrive (the job is live, or just ended), read again this often. */
export const MONITORING_POLL_MS = 10_000

export const monitoringQueryKey = (jobId: string) => ['monitoring', jobId] as const

/** One job's monitoring data. Read-only: it only ever sends GET requests. */
export function useJobMonitoring(jobId: string) {
  return useQuery({
    queryKey: monitoringQueryKey(jobId),
    queryFn: ({ signal }) => fetchJobMonitoring(jobId, signal),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.may_still_arrive ? MONITORING_POLL_MS : false),
    refetchIntervalInBackground: false,
  })
}
