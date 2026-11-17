/** Job lifecycle states -- the same values as the backend's JobStatus enum (jobs/models.py). */
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

/**
 * One architecture job as the UI lists it. This is a UI shape, not an API
 * response: when the API is connected, responses are mapped onto it.
 */
export interface ArchitectureSummary {
  jobId: string
  /** The user's request text. */
  request: string
  status: JobStatus
  /** ISO 8601 timestamp. */
  createdAt: string
  /** Number of AWS services in the design; null until the job has succeeded. */
  serviceCount: number | null
  /** The critic's 0-100 score; null until the job has succeeded. */
  criticScore: number | null
}

export interface JobStats {
  total: number
  succeeded: number
  failed: number
}
