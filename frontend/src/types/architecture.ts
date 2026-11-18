/** Job lifecycle states -- the same values as the backend's JobStatus enum (jobs/models.py). */
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface JobStats {
  total: number
  succeeded: number
  failed: number
}
