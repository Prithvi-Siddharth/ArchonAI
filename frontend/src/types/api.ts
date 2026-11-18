/**
 * Request and response shapes of the ArchonAI REST API, mirroring the backend's
 * Pydantic models in api/schemas.py. Field names stay snake_case, exactly as sent.
 */
import type { JobStatus } from './architecture'

/** One item of GET /api/v1/architectures/examples (ExamplePrompt). */
export interface ExamplePrompt {
  label: string
  prompt: string
}

/** Body of POST /api/v1/architectures/jobs (ArchitectureRequest). */
export interface ArchitectureRequest {
  /** Trimmed by the backend, then must be 10-4000 characters. */
  user_request: string
}

/** 202 reply of POST /api/v1/architectures/jobs (JobSubmittedResponse). */
export interface JobSubmittedResponse {
  job_id: string
  status: JobStatus
  /** Relative path of the job's status endpoint. */
  status_url: string
}

/** A job's `error` (JobError): set when it failed, or while it waits for an automatic retry. */
export interface JobError {
  status_code: number
  /** Client-safe message from the backend. */
  message: string
}

/**
 * The parts of a finished job's `result` (ArchitectureResponse) that the UI
 * reads so far. The real object is much larger; extend this as more is shown.
 */
export interface ArchitectureResult {
  approved: boolean
  architecture: { services: unknown[] }
  critic_review: { score: number }
}

/** 200 reply of GET /api/v1/architectures/jobs/{job_id} (JobStatusResponse). Times are ISO 8601, UTC. */
export interface JobStatusResponse {
  job_id: string
  status: JobStatus
  attempts: number
  created_at: string
  started_at: string | null
  finished_at: string | null
  error: JobError | null
  /** Set once status is "succeeded". */
  result: ArchitectureResult | null
}

/** One entry of a FastAPI 422 reply's `detail` list (request validation). */
export interface ValidationErrorItem {
  type: string
  /** Where the problem is, e.g. ["body", "user_request"]. */
  loc: Array<string | number>
  msg: string
  ctx?: Record<string, unknown>
}

/** Every error reply: `detail` is a message, or a list of problems for a 422. */
export interface ApiErrorBody {
  detail: string | ValidationErrorItem[]
}
