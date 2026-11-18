/**
 * Execution traces of two real results from GET /api/v1/architectures/jobs/{id}, copied verbatim for tests.
 * 17e8c5b5: 18 steps, iterations 0-2 (revision limit reached). 2c9cd4ce: 15 steps, iterations 0-1 (approved).
 */
import type { TraceEntry } from '@/types/api'

export const REAL_TRACE_TWO_REVISIONS: TraceEntry[] = [
  {
    "node": "Requirements Analyzer",
    "action": "Extracted structured requirements from the user's natural-language request.",
    "output_summary": "Type: e-commerce platform | Concurrent users: 500,000 | Availability: High availability (user-stated); no specific uptime percentage given",
    "iteration": 0
  },
  {
    "node": "Architecture Planner",
    "action": "Determined architectural concerns to address across 12 dimensions.",
    "output_summary": "Compute plan: Auto-scaling container pools burst horizontally to absorb flash-sale write spikes while sustaining 500K concurrent sessi",
    "iteration": 0
  },
  {
    "node": "Architecture Designer",
    "action": "Searched the AWS service knowledge base and designed the initial architecture with 7 services.",
    "output_summary": "Amazon CloudFront + AWS WAF, Amazon Route 53 + ALB, Amazon ECS Fargate + Auto Scaling, Amazon Aurora PostgreSQL, Amazon ElastiCache Redis, Amazon S3, Amazon SQS",
    "iteration": 0
  },
  {
    "node": "Compute Agent",
    "action": "Analyzed compute service selection, scaling strategy, and bottlenecks.",
    "output_summary": "Keep ECS Fargate; add Lambda for spiky async order/payment processing.",
    "iteration": 0
  },
  {
    "node": "Database Agent",
    "action": "Analyzed data layer: consistency, replication, partitioning, and backups.",
    "output_summary": "Keep Aurora PostgreSQL for orders/payments; add DynamoDB for catalog reads.; Use Aurora Global Database for cross-region low-latency reads.",
    "iteration": 0
  },
  {
    "node": "Networking Agent",
    "action": "Analyzed VPC design, AZ distribution, load balancing, and network isolation.",
    "output_summary": "Use 3 AZs with public/private subnets per region for HA and isolation.",
    "iteration": 0
  },
  {
    "node": "Security Agent",
    "action": "Analyzed IAM, encryption, secrets management, WAF, and audit logging coverage.",
    "output_summary": "Use AWS Secrets Manager for all DB and payment credentials, rotated automatically.",
    "iteration": 0
  },
  {
    "node": "Cost Agent",
    "action": "Ran the rule-based cost estimator tool and layered trade-off analysis on top.",
    "output_summary": "$4,120 - $34,800 per month (educational estimate)",
    "iteration": 0
  },
  {
    "node": "Reliability Agent",
    "action": "Analyzed multi-AZ HA, disaster recovery, and failure-scenario resilience.",
    "output_summary": "Add explicit retry, timeout, and circuit-breaker policies between all services.; Define RTO/RPO and test multi-region failover with automated DR drills.",
    "iteration": 0
  },
  {
    "node": "Architecture Validator",
    "action": "Ran deterministic rule-based checks; found 1 issue(s).",
    "output_summary": "database_without_backups",
    "iteration": 0
  },
  {
    "node": "Architecture Critic",
    "action": "Reviewed architecture v1 against requirements and validator findings.",
    "output_summary": "REJECTED | score=62 | issues=4",
    "iteration": 0
  },
  {
    "node": "Architecture Revision",
    "action": "Revised architecture to v2, addressing 4 required changes. A first attempt introduced an unjustified regression -- it was corrected. Change log verified against the design: 5 implemented or removed, 0 proposed only (not in the design).",
    "output_summary": "Added DynamoDB for 500K concurrent catalog reads.; Added Aurora PITR plus cross-region snapshot backups.; Added CloudTrail, KMS, Secrets Manager for PCI-DSS.",
    "iteration": 1
  },
  {
    "node": "Architecture Validator",
    "action": "Ran deterministic rule-based checks; found 0 issue(s).",
    "output_summary": "No deterministic issues found.",
    "iteration": 1
  },
  {
    "node": "Architecture Critic",
    "action": "Reviewed architecture v2 against requirements and validator findings.",
    "output_summary": "REJECTED | score=68 | issues=4",
    "iteration": 1
  },
  {
    "node": "Architecture Revision",
    "action": "Rejected the revised architecture as a regression (new validator failure 'database_without_backups'); kept v2 and re-submitted it to the critic.",
    "output_summary": "Revision regressed earlier fixes -- architecture unchanged this round.",
    "iteration": 2
  },
  {
    "node": "Architecture Validator",
    "action": "Ran deterministic rule-based checks; found 0 issue(s).",
    "output_summary": "No deterministic issues found.",
    "iteration": 2
  },
  {
    "node": "Architecture Critic",
    "action": "Architecture v2 and its review context are unchanged since the last review; reused that review instead of reviewing it again.",
    "output_summary": "REJECTED | score=68 | issues=4 (reused)",
    "iteration": 2
  },
  {
    "node": "Final Report",
    "action": "Synthesized all agent outputs into the final architecture recommendation report. Removed claims about features not in the final architecture from 1 field(s).",
    "output_summary": "Multi-region AWS design serves 500K concurrent users with sub-200ms responses, PCI-DSS encryption, and 99.9% availability.",
    "iteration": 2
  }
]

export const REAL_TRACE_ONE_REVISION: TraceEntry[] = [
  {
    "node": "Requirements Analyzer",
    "action": "Extracted structured requirements from the user's natural-language request.",
    "output_summary": "Type: e-commerce platform | Concurrent users: 500,000 | Availability: High availability, minimal downtime",
    "iteration": 0
  },
  {
    "node": "Architecture Planner",
    "action": "Determined architectural concerns to address across 12 dimensions.",
    "output_summary": "Compute plan: Auto-scaling container fleet elastically scales to 500,000 concurrent users across spiky, bursty sales-event traffic.",
    "iteration": 0
  },
  {
    "node": "Architecture Designer",
    "action": "Searched the AWS service knowledge base and designed the initial architecture with 7 services.",
    "output_summary": "Amazon CloudFront + AWS WAF, AWS Global Accelerator + ALB, Amazon ECS Fargate + Auto Scaling, Amazon Aurora PostgreSQL, Amazon ElastiCache Redis, Amazon S3, Amazon SQS",
    "iteration": 0
  },
  {
    "node": "Compute Agent",
    "action": "Analyzed compute service selection, scaling strategy, and bottlenecks.",
    "output_summary": "Keep ECS Fargate; add Lambda for spiky async payment/order handlers.",
    "iteration": 0
  },
  {
    "node": "Database Agent",
    "action": "Analyzed data layer: consistency, replication, partitioning, and backups.",
    "output_summary": "Keep Aurora PostgreSQL for orders/payments; add DynamoDB for catalog reads.; Use Aurora Global Database for cross-region low-latency reads.",
    "iteration": 0
  },
  {
    "node": "Networking Agent",
    "action": "Analyzed VPC design, AZ distribution, load balancing, and network isolation.",
    "output_summary": "Use multi-AZ public/private subnets per region with NAT gateways.",
    "iteration": 0
  },
  {
    "node": "Security Agent",
    "action": "Analyzed IAM, encryption, secrets management, WAF, and audit logging coverage.",
    "output_summary": "Use AWS Secrets Manager for all DB and payment credentials, rotated automatically.",
    "iteration": 0
  },
  {
    "node": "Cost Agent",
    "action": "Ran the rule-based cost estimator tool and layered trade-off analysis on top.",
    "output_summary": "$3,920 - $33,200 per month (educational estimate)",
    "iteration": 0
  },
  {
    "node": "Reliability Agent",
    "action": "Analyzed multi-AZ HA, disaster recovery, and failure-scenario resilience.",
    "output_summary": "Add multi-region Aurora Global Database for DR failover.",
    "iteration": 0
  },
  {
    "node": "Architecture Validator",
    "action": "Ran deterministic rule-based checks; found 1 issue(s).",
    "output_summary": "database_without_backups",
    "iteration": 0
  },
  {
    "node": "Architecture Critic",
    "action": "Reviewed architecture v1 against requirements and validator findings.",
    "output_summary": "REJECTED | score=62 | issues=4",
    "iteration": 0
  },
  {
    "node": "Architecture Revision",
    "action": "Revised architecture to v2, addressing 4 required changes. A first attempt introduced an unjustified regression; it also left a blocking validator finding unresolved (database_without_backups) -- it was corrected. Change log verified against the design: 7 implemented or removed, 0 proposed only (not in the design).",
    "output_summary": "Added DynamoDB for read-heavy catalog to relieve Aurora.; Added Aurora Global Database for cross-region DR and low-latency reads.; Added IAM, KMS, Secrets Manager, CloudTrail for PCI-DSS compliance.",
    "iteration": 1
  },
  {
    "node": "Architecture Validator",
    "action": "Ran deterministic rule-based checks; found 0 issue(s).",
    "output_summary": "No deterministic issues found.",
    "iteration": 1
  },
  {
    "node": "Architecture Critic",
    "action": "Reviewed architecture v2 against requirements and validator findings.",
    "output_summary": "APPROVED | score=82 | issues=4",
    "iteration": 1
  },
  {
    "node": "Final Report",
    "action": "Synthesized all agent outputs into the final architecture recommendation report.",
    "output_summary": "Multi-region e-commerce platform serving 500,000 concurrent users with sub-200ms responses and ~99.9% uptime. Estimated $3,920–$33,200/month.",
    "iteration": 1
  }
]
