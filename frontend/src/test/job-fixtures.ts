/** Test data: GET /jobs/{id} replies (JobStatusResponse) for each job situation. */
import type { JobStatusResponse } from '@/types/api'

export const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString()

export const RETRY_ERROR = { status_code: 429, message: 'LLM provider rate limit reached. Please retry later.' }

export function makeJob(overrides: Partial<JobStatusResponse> = {}): JobStatusResponse {
  return {
    job_id: 'job-1',
    status: 'queued',
    attempts: 0,
    created_at: minutesAgo(2),
    started_at: null,
    finished_at: null,
    error: null,
    result: null,
    ...overrides,
  }
}

/** One job per situation the tracking page distinguishes. */
export const JOBS = {
  queued: makeJob(),
  running: makeJob({ status: 'running', attempts: 1, started_at: minutesAgo(1) }),
  retryWaiting: makeJob({ status: 'queued', attempts: 1, started_at: minutesAgo(1), error: RETRY_ERROR }),
  retryRunning: makeJob({ status: 'running', attempts: 2, started_at: minutesAgo(0.5), error: RETRY_ERROR }),
  succeeded: makeJob({
    status: 'succeeded',
    attempts: 1,
    started_at: minutesAgo(1.5),
    finished_at: minutesAgo(0.2),
    result: { approved: true, architecture: { services: [] }, critic_review: { score: 80 } },
  }),
  failed: makeJob({
    status: 'failed',
    attempts: 2,
    started_at: minutesAgo(1.5),
    finished_at: minutesAgo(0.2),
    error: RETRY_ERROR,
  }),
} satisfies Record<string, JobStatusResponse>

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
