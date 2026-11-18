/**
 * The final report of a real result (job 2c9cd4ce) from
 * GET /api/v1/architectures/jobs/{id}, copied verbatim for tests.
 */
import type { FinalReport } from '@/types/api'

export const REAL_REPORT_JOB_ID = '2c9cd4ce-5521-4fd8-9077-99ed27d0b570'

export const REAL_REPORT: FinalReport = {
  "executive_summary": "Multi-region e-commerce platform serving 500,000 concurrent users with sub-200ms responses and ~99.9% uptime. Estimated $3,920–$33,200/month.",
  "requirements_summary": "e-commerce platform: Supports 500,000 concurrent users; Requires high availability; Requires low latency; Secure payment processing; Must scale during traffic spikes.",
  "architecture_overview": "CloudFront/WAF routes to Global Accelerator/ALB, then ECS Fargate APIs. DynamoDB+Redis serve catalog; Aurora Global Database handles orders; SQS decouples payments.",
  "aws_services_summary": "Services: Amazon CloudFront + AWS WAF (Edge-caches static assets and product images; filters malicious tra...); AWS Global Accelerator + ALB (Routes read-heavy traffic to multi-AZ load balancer endpoints); Amazon ECS Fargate + Auto Scaling (Runs stateless API containers with auto scaling across private subnets); Amazon Aurora PostgreSQL Global Database (Strongly consistent orders/payments with cross-region DR, automated...); Amazon DynamoDB + ElastiCache Redis (DynamoDB serves read-heavy catalog with automated backups and point...); Amazon S3 (Stores product images, user profiles, and order history with encryp...); Amazon SQS (Decouples order and payment processing to absorb spiky traffic); AWS IAM + KMS + Secrets Manager + CloudTrail (Least-privilege IAM, KMS encryption, Secrets Manager, CloudTrail fo...).",
  "data_flow_summary": "User -> CloudFront + WAF; CloudFront + WAF -> Global Accelerator + ALB; Global Accelerator + ALB -> ECS Fargate; ECS Fargate -> DynamoDB + Redis; ECS Fargate -> Aurora PostgreSQL; ECS Fargate -> SQS",
  "scalability_strategy": "Fargate auto scaling absorbs spiky sales traffic; DynamoDB and ElastiCache Redis absorb read-heavy catalog load during bursts.",
  "high_availability_strategy": "Multi-AZ Fargate, Aurora read replicas, and cross-region Global Database keep serving during regional or AZ failures.",
  "security_summary": "KMS encryption, Secrets Manager, least-privilege IAM, and CloudTrail auditing protect PII and satisfy PCI-DSS payment requirements.",
  "reliability_summary": "Aurora automated backups, PITR, cross-region snapshots, and DynamoDB backups enable recovery; S3 stores images and order history.",
  "observability_summary": "CloudTrail logs API and security events for PCI-DSS audit and debugging across the multi-region stack.",
  "cost_summary": "$3,920 - $33,200 per month (educational estimate); major cost drivers: Compute, Database, Networking. Recommended first optimization: Apply Savings Plans/Reserved Instances to steady-state Fargate and Aurora capacity, reserving only the baseline and paying on-demand for spikes.",
  "bottlenecks": [
    "Fargate cold starts may breach sub-200ms during spikes",
    "Aurora read replica lag under spike load",
    "Global Accelerator adds latency vs regional routing"
  ],
  "trade_offs": [
    "Multi-region raises networking cost for stronger availability",
    "Aurora multi-AZ replicas trade cost for consistency",
    "Fargate trades per-task cost for zero server management"
  ],
  "critic_findings_summary": "Critic score 82/100 (approved) after 1 revision cycle. 7 verified changes were made during revision. It raised 4 issues (3 medium, 1 low) in scalability, reliability, networking.",
  "final_recommendations": [
    "Add Lambda for bursty async payment handlers",
    "Add DynamoDB global tables for hot catalog",
    "Define RTO/RPO and add circuit breakers/retries",
    "Add API Gateway in front of ALB for rate limiting"
  ],
  "open_recommendations": [
    "Add Lambda for bursty async payment/order handlers.",
    "Add DynamoDB global tables for hot catalog reads.",
    "Define RTO/RPO and add circuit-breaker/retry patterns.",
    "Add API Gateway in front of ALB for rate limiting."
  ]
}
