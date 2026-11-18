/** Job lifecycle states -- the same values as the backend's JobStatus enum (jobs/models.py). */
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

/** What the UI knows about a job's status while reading it from the API. */
export type JobStatusView =
  | { state: 'loading' }
  | { state: 'known'; status: JobStatus }
  /** The API has no job with this id (404). */
  | { state: 'not-found' }
  /** The status couldn't be read (API unreachable or erroring). */
  | { state: 'unavailable' }

/** One architecture job as the UI lists it (built from a local submission record plus its API status). */
export interface ArchitectureSummary {
  jobId: string
  /** Preview of the user's request text. */
  request: string
  status: JobStatusView
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
