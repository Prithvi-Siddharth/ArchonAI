/**
 * What a job is doing, derived from the backend's status and error fields
 * (see jobs/repository.py). The backend reports no percentage or per-agent
 * progress, so these six phases are everything there is to show.
 */
import type { JobStatusResponse } from '@/types/api'

export type JobPhase =
  /** queued, no error: waiting for a worker. */
  | 'queued'
  /** running, no error: first attempt in progress. */
  | 'running'
  /** queued with an error: a temporary failure; an automatic retry is pending. */
  | 'retry-waiting'
  /** running with an error: the retry attempt is in progress. */
  | 'retry-running'
  | 'succeeded'
  | 'failed'

/**
 * The fields a job's progress is worked out from. A job's status reply and a
 * history row (GET /jobs) both have them, so either can be shown as progress.
 */
export type JobProgress = Pick<JobStatusResponse, 'job_id' | 'status' | 'attempts' | 'created_at' | 'started_at' | 'finished_at' | 'error'>

export function jobPhase(job: JobProgress): JobPhase {
  switch (job.status) {
    case 'queued':
      return job.error ? 'retry-waiting' : 'queued'
    case 'running':
      return job.error ? 'retry-running' : 'running'
    case 'succeeded':
      return 'succeeded'
    case 'failed':
      return 'failed'
  }
}

/** Finished jobs never change again: the backend refuses status changes after succeeded/failed. */
export function isFinalJob(job: JobProgress | undefined): boolean {
  return job?.status === 'succeeded' || job?.status === 'failed'
}

/**
 * The backend stops an attempt at its time limit (JOB_TIMEOUT_SECONDS, 15
 * minutes by default), so a phase lasting longer than this is unusual.
 */
export const LONG_RUNNING_MS = 15 * 60 * 1000

/**
 * Whether the job has been in its current phase for longer than expected:
 * an attempt running past the time limit, or a first wait for a worker that
 * long. (The backend reports no time for a retry wait, so that isn't timed.)
 */
export function isTakingLong(job: JobProgress, now: number): boolean {
  const phase = jobPhase(job)
  const since =
    phase === 'running' || phase === 'retry-running' ? job.started_at : phase === 'queued' ? job.created_at : null
  return since !== null && now - new Date(since).getTime() > LONG_RUNNING_MS
}
