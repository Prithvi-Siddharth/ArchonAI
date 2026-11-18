/** Architecture endpoints (backend: api/routes/architectures.py). */
import type { ArchitectureRequest, ExamplePrompt, JobStatusResponse, JobSubmittedResponse } from '@/types/api'

import { apiRequest } from './client'

export const ARCHITECTURES_PATH = '/api/v1/architectures'

/** GET /examples -- the example prompts (backend data/example_prompts.json), in display order. */
export function fetchExamplePrompts(signal?: AbortSignal): Promise<ExamplePrompt[]> {
  return apiRequest<ExamplePrompt[]>(`${ARCHITECTURES_PATH}/examples`, { signal })
}

/**
 * POST /jobs -- queue a design request; resolves with the new job's id (HTTP 202).
 * Never retried automatically: the backend has no idempotency key, so a retry
 * could create a second job.
 */
export function submitArchitectureJob(userRequest: string): Promise<JobSubmittedResponse> {
  const body: ArchitectureRequest = { user_request: userRequest }
  return apiRequest<JobSubmittedResponse>(`${ARCHITECTURES_PATH}/jobs`, { method: 'POST', body })
}

/** GET /jobs/{job_id} -- a job's current status (and its full result once it has succeeded). 404 if unknown. */
export function fetchJob(jobId: string, signal?: AbortSignal): Promise<JobStatusResponse> {
  return apiRequest<JobStatusResponse>(`${ARCHITECTURES_PATH}/jobs/${encodeURIComponent(jobId)}`, { signal })
}
