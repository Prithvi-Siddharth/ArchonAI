/**
 * The five specialist analyses of a real result (job 17e8c5b5) from
 * GET /api/v1/architectures/jobs/{id}, copied verbatim for tests.
 */
import type { ArchitectureResult } from '@/types/api'

export type SpecialistAnalyses = Pick<ArchitectureResult, 'compute_analysis' | 'database_analysis' | 'networking_analysis' | 'security_analysis' | 'reliability_analysis'>

export const REAL_ANALYSES: SpecialistAnalyses = {
  "compute_analysis": {
    "domain": "Compute",
    "recommendations": [
      "Keep ECS Fargate; add Lambda for spiky async order/payment processing."
    ],
    "reasoning": "Fargate suits stateless, auto-scaling API workloads with no server ops. Add Lambda for bursty async processing to absorb flash-sale spikes.",
    "risks": [
      "Fargate cold starts may breach sub-200ms latency."
    ]
  },
  "database_analysis": {
    "domain": "Database",
    "recommendations": [
      "Keep Aurora PostgreSQL for orders/payments; add DynamoDB for catalog reads.",
      "Use Aurora Global Database for cross-region low-latency reads.",
      "Add ElastiCache Redis in front of DB for hot catalog data.",
      "Enable PITR plus cross-region snapshots for recovery."
    ],
    "reasoning": "Aurora gives strong consistency for payments; DynamoDB scales catalog reads. Redis caching and Global Database cut latency and cross-region read cost.",
    "risks": [
      "Single-region Aurora write limits flash-sale throughput.",
      "Cross-region replication lag risks payment consistency.",
      "No sharding plan for 500K concurrent writes."
    ]
  },
  "networking_analysis": {
    "domain": "Networking",
    "recommendations": [
      "Use 3 AZs with public/private subnets per region for HA and isolation."
    ],
    "reasoning": "Multi-region active-active needs per-region VPCs with 3-AZ public/private segmentation. ALB in public subnets, Fargate in private, with NAT/egress controls.",
    "risks": [
      "No API Gateway; WAF alone may miss API-level rate limiting."
    ]
  },
  "security_analysis": {
    "domain": "Security",
    "recommendations": [
      "Use AWS Secrets Manager for all DB and payment credentials, rotated automatically."
    ],
    "reasoning": "Architecture lacks explicit IAM, secrets, and audit controls. Add least-privilege IAM, KMS encryption, and CloudTrail for PCI-DSS.",
    "risks": [
      "Missing audit logging fails PCI-DSS compliance."
    ]
  },
  "reliability_analysis": {
    "domain": "Reliability",
    "recommendations": [
      "Add explicit retry, timeout, and circuit-breaker policies between all services.",
      "Define RTO/RPO and test multi-region failover with automated DR drills.",
      "Add health checks, dead-letter queues, and idempotency for SQS consumers.",
      "Use Aurora Global Database for cross-region low-latency replication."
    ],
    "reasoning": "Architecture is solid but lacks explicit retry/timeout/circuit-breaker policies and tested DR. Multi-AZ and active-active help, but untested failover and missing idempotency risk data loss during spikes.",
    "risks": [
      "No defined RTO/RPO; untested multi-region failover.",
      "Missing circuit breakers risk cascading failures under spikes.",
      "SQS without idempotency may duplicate orders during retries."
    ]
  }
}
