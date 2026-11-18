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

// ---------------------------------------------------------------------------
// A finished job's result: ArchitectureResponse (api/schemas.py), built from
// the models in models/schemas.py. No field inside it is nullable; fields the
// backend gives defaults (noted below) are always present because the API
// re-validates stored results before replying. Free-text fields stay `string`.
// ---------------------------------------------------------------------------

/** TrafficPattern enum. */
export type TrafficPattern = 'steady' | 'spiky' | 'seasonal' | 'unpredictable'

/** Severity enum, shared by critic issues and validation issues. */
export type Severity = 'low' | 'medium' | 'high' | 'critical'

/** Requirements extracted from the user's request. Quantities are free text (e.g. "2 million"). */
export interface Requirements {
  application_type: string
  expected_users: string
  concurrent_users: string
  /** Default "steady". */
  traffic_pattern: TrafficPattern
  traffic_characteristics: string
  latency_requirements: string
  availability_requirements: string
  scalability_requirements: string
  storage_requirements: string
  database_requirements: string
  security_requirements: string
  /** Default "None specified". */
  compliance_requirements: string
  /** Default "Not specified". */
  geographic_requirements: string
  /** Default "Not specified". */
  budget_constraints: string
  /** What the user actually stated. Default []. */
  explicit_requirements: string[]
  /** What the analyst assumed rather than read. Default []. */
  inferred_assumptions: string[]
}

/** The planner's high-level plan: one consideration per concern. */
export interface ArchitecturePlan {
  frontend: string
  networking: string
  compute: string
  database: string
  caching: string
  storage: string
  messaging: string
  security: string
  observability: string
  reliability: string
  scalability: string
  cost: string
}

export interface AWSService {
  name: string
  /** Free text, e.g. "Compute", "Networking/CDN". */
  category: string
  purpose: string
  justification: string
}

/**
 * One hop of the data flow. `source` and `destination` are free text and are
 * NOT guaranteed to match a service name (e.g. "User", "CloudFront + WAF").
 */
export interface DataFlowStep {
  step: number
  source: string
  destination: string
  description: string
}

export interface Architecture {
  summary: string
  services: AWSService[]
  data_flow: DataFlowStep[]
  /** 1 + accepted revisions (a rejected revision keeps the previous version). Default 1. */
  version: number
  /** Cumulative plain-text entries; not tagged with a version. Default []. */
  change_log: string[]
}

/** A specialist analysis (compute, database, networking, security, reliability). */
export interface AnalysisResult {
  domain: string
  recommendations: string[]
  reasoning: string
  /** Default []. */
  risks: string[]
}

export interface CostAnalysis {
  /** Free text, e.g. "$4,120 - $34,800 per month (educational estimate)". */
  estimated_monthly_range: string
  major_cost_drivers: string[]
  /** Component -> relative weight; both free text (values seen: "high", "medium", "low"). Default {}. */
  relative_cost_breakdown: Record<string, string>
  optimizations: string[]
  trade_offs: string[]
  /** Has a backend default. */
  disclaimer: string
}

/** An issue from the rule-based validator. */
export interface ValidationIssue {
  /** Rule name, e.g. "database_without_backups" (seven rules exist in tools/architecture_validator.py). */
  rule: string
  message: string
  severity: Severity
}

export interface ValidationResult {
  passed: boolean
  /** Default []. */
  issues: ValidationIssue[]
}

export interface CriticIssue {
  issue: string
  severity: Severity
  /** Free text, e.g. "security", "cost". */
  category: string
}

/** The critic's final review (earlier rounds are not returned). */
export interface CriticReview {
  approved: boolean
  /** 0-100. */
  score: number
  /** Default []. */
  issues: CriticIssue[]
  /** Default []. */
  required_changes: string[]
  /** Default []. */
  strengths: string[]
}

export interface FinalReport {
  executive_summary: string
  requirements_summary: string
  architecture_overview: string
  aws_services_summary: string
  data_flow_summary: string
  scalability_strategy: string
  high_availability_strategy: string
  security_summary: string
  reliability_summary: string
  observability_summary: string
  cost_summary: string
  bottlenecks: string[]
  trade_offs: string[]
  critic_findings_summary: string
  final_recommendations: string[]
  /** Requested or proposed changes the final architecture does not contain. Default []. */
  open_recommendations: string[]
}

/** One recorded workflow step (graph/state.py TraceEntry). */
export interface TraceEntry {
  /** Agent display name, e.g. "Requirements Analyzer". */
  node: string
  action: string
  output_summary: string
  /** Revision round the step ran in (0 = before any revision). */
  iteration: number
}

/** The full result of a succeeded job (ArchitectureResponse). */
export interface ArchitectureResult {
  approved: boolean
  /** True if the revision limit was reached before the critic approved. */
  max_revisions_reached: boolean
  /** Critic-driven revision rounds performed. */
  revision_count: number
  requirements: Requirements
  architecture_plan: ArchitecturePlan
  architecture: Architecture
  compute_analysis: AnalysisResult
  database_analysis: AnalysisResult
  networking_analysis: AnalysisResult
  security_analysis: AnalysisResult
  reliability_analysis: AnalysisResult
  cost_analysis: CostAnalysis
  validation_results: ValidationResult
  critic_review: CriticReview
  final_report: FinalReport
  execution_trace: TraceEntry[]
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
