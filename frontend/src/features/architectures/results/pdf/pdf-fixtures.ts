/** Results built from real stored results (src/test/real-*.ts) for the PDF tests. */
import { makeResult } from '@/test/job-fixtures'
import { REAL_ANALYSES } from '@/test/real-analyses'
import { REAL_ARCHITECTURE_BACKWARD, REAL_ARCHITECTURE_COMBINED } from '@/test/real-architectures'
import { REAL_COST_EMPTY_BREAKDOWN, REAL_COST_SEVEN_AREAS } from '@/test/real-cost-analyses'
import { REAL_REPORT, REAL_REPORT_JOB_ID } from '@/test/real-report'
import { REAL_REVIEW_APPROVED, REAL_REVIEW_NOT_APPROVED } from '@/test/real-reviews'
import { REAL_TRACE_ONE_REVISION, REAL_TRACE_TWO_REVISIONS } from '@/test/real-traces'
import type { ArchitectureResult } from '@/types/api'

export const REAL_JOB = {
  job_id: REAL_REPORT_JOB_ID,
  user_request:
    'Design an e-commerce platform that supports 500,000 concurrent users, requires 99.99% availability, handles payment processing securely, supports global users, and keeps infrastructure costs optimized.',
  created_at: '2026-11-14T18:06:17Z',
  finished_at: '2026-11-14T18:12:29Z',
}

/** A not-approved result that hit the revision limit, with real analyses, cost, review, report and trace. */
export const REAL_LIKE_RESULT: ArchitectureResult = makeResult({
  ...REAL_ANALYSES,
  ...REAL_REVIEW_NOT_APPROVED,
  architecture: REAL_ARCHITECTURE_COMBINED,
  cost_analysis: REAL_COST_SEVEN_AREAS,
  final_report: REAL_REPORT,
  execution_trace: REAL_TRACE_TWO_REVISIONS,
})

/** An approved result with a back-edge data flow and an empty cost breakdown. */
export const REAL_LIKE_APPROVED: ArchitectureResult = makeResult({
  ...REAL_ANALYSES,
  ...REAL_REVIEW_APPROVED,
  architecture: REAL_ARCHITECTURE_BACKWARD,
  cost_analysis: REAL_COST_EMPTY_BREAKDOWN,
  final_report: REAL_REPORT,
  execution_trace: REAL_TRACE_ONE_REVISION,
})

/** A big architecture: many services and steps, for layout limits. */
export function largeResult(services = 28, steps = 30): ArchitectureResult {
  const names = ['Amazon CloudFront + AWS WAF', 'Amazon Route 53', 'Application Load Balancer', 'Amazon ECS (Fargate) + Auto Scaling', 'AWS Lambda', 'Amazon API Gateway', 'Amazon Aurora PostgreSQL', 'Amazon DynamoDB', 'Amazon ElastiCache (Redis)', 'Amazon S3', 'Amazon SQS', 'Amazon SNS', 'Amazon EventBridge', 'AWS Step Functions', 'Amazon Kinesis Data Streams', 'Amazon OpenSearch Service', 'Amazon Cognito', 'AWS KMS', 'AWS Secrets Manager', 'AWS IAM', 'Amazon CloudWatch', 'AWS CloudTrail', 'AWS X-Ray', 'AWS Backup', 'Amazon Redshift', 'AWS Glue', 'Amazon Athena', 'Third-party payment gateway']
  const list = Array.from({ length: services }, (_, i) => names[i % names.length] + (i >= names.length ? ` ${i}` : ''))
  const base = makeResult()
  return makeResult({
    architecture: {
      ...base.architecture,
      services: list.map((name, i) => ({ name, category: ['Networking', 'Compute', 'Database', 'Storage', 'Security', 'Observability'][i % 6], purpose: `Purpose of ${name}. `.repeat(3), justification: `Why ${name} was chosen. `.repeat(3) })),
      data_flow: Array.from({ length: steps }, (_, i) => ({ step: i + 1, source: list[i % list.length], destination: list[(i * 3 + 1) % list.length], description: `Step ${i + 1} moves data along. `.repeat(2) })),
    },
  })
}
