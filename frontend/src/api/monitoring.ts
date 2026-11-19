/** One job's monitoring data, read from CloudWatch by the backend (api/routes/monitoring.py). Read-only: GET only. */
import type { JobMonitoring } from '@/types/api'

import { apiRequest } from './client'

export function fetchJobMonitoring(jobId: string, signal?: AbortSignal): Promise<JobMonitoring> {
  return apiRequest<JobMonitoring>(`/api/v1/architectures/jobs/${encodeURIComponent(jobId)}/monitoring`, { signal })
}
