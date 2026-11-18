/** Test data: GET /jobs/{id} replies (JobStatusResponse) for each job situation. */
import type { AnalysisResult, ArchitectureResult, JobStatusResponse } from '@/types/api'

export const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString()

const analysis = (domain: string): AnalysisResult => ({
  domain,
  recommendations: [`${domain} recommendation`],
  reasoning: `${domain} reasoning.`,
  risks: [`${domain} risk`],
})

/** A complete result (ArchitectureResponse) with test values in every field. */
export function makeResult(overrides: Partial<ArchitectureResult> = {}): ArchitectureResult {
  return {
    approved: true,
    max_revisions_reached: false,
    revision_count: 1,
    requirements: {
      application_type: 'Test e-commerce platform',
      expected_users: '2 million registered users',
      concurrent_users: '500,000',
      traffic_pattern: 'spiky',
      traffic_characteristics: 'Large spikes during sales.',
      latency_requirements: 'Sub-200ms API responses',
      availability_requirements: '99.99% uptime',
      scalability_requirements: 'Scale 10x during spikes',
      storage_requirements: 'Product images',
      database_requirements: 'Strongly consistent orders',
      security_requirements: 'PCI-DSS payment handling',
      compliance_requirements: 'PCI-DSS',
      geographic_requirements: 'North America',
      budget_constraints: 'Not specified',
      explicit_requirements: ['Support 500,000 concurrent users', 'Process payments securely'],
      inferred_assumptions: ['Multi-AZ deployment is acceptable'],
    },
    architecture_plan: {
      frontend: 'CDN-backed web client.',
      networking: 'Multi-AZ VPC.',
      compute: 'Containers behind a load balancer.',
      database: 'Relational store for orders.',
      caching: 'Redis for catalog reads.',
      storage: 'Object storage for media.',
      messaging: 'Queue for order processing.',
      security: 'Least-privilege IAM.',
      observability: 'Central metrics and logs.',
      reliability: 'Multi-AZ with backups.',
      scalability: 'Auto scaling on load.',
      cost: 'Reserved capacity for baseline.',
    },
    architecture: {
      summary: 'A load-balanced, auto-scaling, multi-AZ test architecture.',
      services: [
        { name: 'Application Load Balancer', category: 'Networking', purpose: 'Distribute traffic', justification: 'High availability' },
        { name: 'Amazon ECS', category: 'Compute', purpose: 'Run services', justification: 'Managed containers' },
        { name: 'Amazon Aurora', category: 'Database', purpose: 'Store orders', justification: 'Relational, multi-AZ' },
      ],
      data_flow: [
        { step: 1, source: 'User', destination: 'ALB', description: 'Request hits the load balancer' },
        { step: 2, source: 'ALB', destination: 'Amazon ECS', description: 'Routed to a task' },
      ],
      version: 2,
      change_log: ['Added Aurora backups.'],
    },
    compute_analysis: analysis('Compute'),
    database_analysis: analysis('Database'),
    networking_analysis: analysis('Networking'),
    security_analysis: analysis('Security'),
    reliability_analysis: analysis('Reliability'),
    cost_analysis: {
      estimated_monthly_range: '$4,120 - $34,800 per month (educational estimate)',
      major_cost_drivers: ['Compute'],
      relative_cost_breakdown: { compute: 'high', database: 'medium' },
      optimizations: ['Use reserved capacity.'],
      trade_offs: ['Multi-AZ costs more.'],
      disclaimer: 'This is an educational, order-of-magnitude estimate only.',
    },
    validation_results: { passed: true, issues: [] },
    critic_review: {
      approved: true,
      score: 82,
      issues: [{ issue: 'No WAF in front of the API.', severity: 'medium', category: 'security' }],
      required_changes: [],
      strengths: ['Good use of managed services.'],
    },
    final_report: {
      executive_summary: 'Test executive summary.',
      requirements_summary: 'Requirements summary.',
      architecture_overview: 'Architecture overview.',
      aws_services_summary: 'Services summary.',
      data_flow_summary: 'Data flow summary.',
      scalability_strategy: 'Scalability strategy.',
      high_availability_strategy: 'HA strategy.',
      security_summary: 'Security summary.',
      reliability_summary: 'Reliability summary.',
      observability_summary: 'Observability summary.',
      cost_summary: 'Cost summary.',
      bottlenecks: ['Primary database writes.'],
      trade_offs: ['Cost for availability.'],
      critic_findings_summary: 'Critic findings summary.',
      final_recommendations: ['Run a load test.'],
      open_recommendations: [],
    },
    execution_trace: [
      { node: 'Requirements Analyzer', action: 'Extracted requirements', output_summary: 'e-commerce platform', iteration: 0 },
      { node: 'Final Report', action: 'Wrote the report', output_summary: 'Report ready', iteration: 1 },
    ],
    ...overrides,
  }
}

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
    result: makeResult(),
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
