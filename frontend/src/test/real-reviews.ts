/**
 * Review-related fields of three real results from GET /api/v1/architectures/jobs/{id}
 * (jobs 17e8c5b5, c35dd965, 2c9cd4ce), copied verbatim for tests: not approved with a
 * critical issue and the revision limit reached; one with a low-severity issue; approved.
 * `withReview` (below) puts them into a complete result.
 */
import type { ArchitectureResult, CriticReview, ValidationResult } from '@/types/api'

import { makeResult } from './job-fixtures'

export interface ReviewFields {
  approved: boolean
  max_revisions_reached: boolean
  revision_count: number
  critic_review: CriticReview
  validation_results: ValidationResult
  version: number
  change_log: string[]
  open_recommendations: string[]
}

export function withReview(fields: ReviewFields): ArchitectureResult {
  const base = makeResult()
  return makeResult({
    approved: fields.approved,
    max_revisions_reached: fields.max_revisions_reached,
    revision_count: fields.revision_count,
    critic_review: fields.critic_review,
    validation_results: fields.validation_results,
    architecture: { ...base.architecture, version: fields.version, change_log: fields.change_log },
    final_report: { ...base.final_report, open_recommendations: fields.open_recommendations },
  })
}

export const REAL_REVIEW_NOT_APPROVED: ReviewFields = {
  "approved": false,
  "max_revisions_reached": true,
  "revision_count": 2,
  "critic_review": {
    "approved": false,
    "score": 68,
    "issues": [
      {
        "issue": "No sharding plan for 500K concurrent writes to single Aurora cluster.",
        "severity": "critical",
        "category": "scalability"
      },
      {
        "issue": "No explicit retry, timeout, or circuit-breaker policies between services.",
        "severity": "high",
        "category": "reliability"
      },
      {
        "issue": "No explicit least-privilege IAM roles defined for ECS, Aurora, or DynamoDB.",
        "severity": "high",
        "category": "security"
      },
      {
        "issue": "No defined RTO/RPO or tested multi-region failover for DR.",
        "severity": "medium",
        "category": "reliability"
      }
    ],
    "required_changes": [
      "Add Aurora sharding or partitioning strategy for 500K concurrent writes.",
      "Define retry, timeout, and circuit-breaker policies for all service calls.",
      "Add least-privilege IAM roles for ECS, Aurora, DynamoDB, and S3.",
      "Define RTO/RPO and automate multi-region failover DR drills."
    ],
    "strengths": [
      "Aurora PostgreSQL provides strong consistency for orders and payments.",
      "CloudFront plus WAF edge-caches catalog for sub-200ms latency.",
      "SQS with idempotency keys and dead-letter queues handles bursty writes."
    ]
  },
  "validation_results": {
    "passed": true,
    "issues": []
  },
  "version": 2,
  "change_log": [
    "Added DynamoDB for 500K concurrent catalog reads.",
    "Added Aurora PITR plus cross-region snapshot backups.",
    "Added CloudTrail, KMS, Secrets Manager for PCI-DSS.",
    "Added SQS idempotency keys and dead-letter queues.",
    "Restored Aurora read replicas for high-throughput catalog reads."
  ],
  "open_recommendations": [
    "Add Aurora sharding or partitioning strategy for 500K concurrent writes.",
    "Define retry, timeout, and circuit-breaker policies for all service calls.",
    "Add least-privilege IAM roles for ECS, Aurora, DynamoDB, and S3.",
    "Define RTO/RPO and automate multi-region failover DR drills."
  ]
}

export const REAL_REVIEW_WITH_LOW: ReviewFields = {
  "approved": false,
  "max_revisions_reached": true,
  "revision_count": 2,
  "critic_review": {
    "approved": false,
    "score": 68,
    "issues": [
      {
        "issue": "Aurora single-writer bottleneck during flash-sale order write spikes.",
        "severity": "high",
        "category": "scalability"
      },
      {
        "issue": "No explicit IAM least-privilege or Secrets Manager for PCI secrets.",
        "severity": "high",
        "category": "security"
      },
      {
        "issue": "No circuit breakers or retry policy on SQS-to-Aurora consumer.",
        "severity": "medium",
        "category": "reliability"
      },
      {
        "issue": "Cross-region Aurora restore plus S3 CRR adds unneeded DR cost.",
        "severity": "low",
        "category": "cost"
      }
    ],
    "required_changes": [
      "Add Aurora read-replica write sharding or DynamoDB for order writes.",
      "Define IAM least-privilege roles and Secrets Manager for PCI keys.",
      "Add circuit breaker and retry on SQS-to-Aurora consumer.",
      "Document cache invalidation strategy for catalog data."
    ],
    "strengths": [
      "SQS async order writes absorb flash-sale spikes off Aurora.",
      "Aurora read replicas plus ElastiCache meet sub-200ms catalog reads.",
      "Lambda plus KMS tokenizes PCI card data at the edge."
    ]
  },
  "validation_results": {
    "passed": true,
    "issues": []
  },
  "version": 3,
  "change_log": [
    "Added Lambda with KMS for PCI payment burst decoupling.",
    "Wired PCI tokenization and KMS into payment path.",
    "Added Aurora cross-region restore plus S3 CRR for DR.",
    "Added SQS async order writes to absorb flash-sale spikes."
  ],
  "open_recommendations": [
    "Add Aurora read-replica write sharding or DynamoDB for order writes.",
    "Define IAM least-privilege roles and Secrets Manager for PCI keys.",
    "Add circuit breaker and retry on SQS-to-Aurora consumer.",
    "Document cache invalidation strategy for catalog data."
  ]
}

export const REAL_REVIEW_APPROVED: ReviewFields = {
  "approved": true,
  "max_revisions_reached": false,
  "revision_count": 1,
  "critic_review": {
    "approved": true,
    "score": 82,
    "issues": [
      {
        "issue": "Fargate cold starts may breach sub-200ms during spikes.",
        "severity": "medium",
        "category": "scalability"
      },
      {
        "issue": "Aurora read replica lag can breach sub-200ms under spikes.",
        "severity": "medium",
        "category": "scalability"
      },
      {
        "issue": "No defined RTO/RPO or circuit-breaker strategy.",
        "severity": "medium",
        "category": "reliability"
      },
      {
        "issue": "Global Accelerator adds latency versus regional routing.",
        "severity": "low",
        "category": "networking"
      }
    ],
    "required_changes": [
      "Add Lambda for bursty async payment/order handlers.",
      "Add DynamoDB global tables for hot catalog reads.",
      "Define RTO/RPO and add circuit-breaker/retry patterns.",
      "Add API Gateway in front of ALB for rate limiting."
    ],
    "strengths": [
      "Aurora Global Database gives strong consistency plus cross-region DR.",
      "DynamoDB plus ElastiCache handles read-heavy catalog under spikes.",
      "CloudFront plus WAF plus KMS plus CloudTrail meet latency and PCI-DSS."
    ]
  },
  "validation_results": {
    "passed": true,
    "issues": []
  },
  "version": 2,
  "change_log": [
    "Added DynamoDB for read-heavy catalog to relieve Aurora.",
    "Added Aurora Global Database for cross-region DR and low-latency reads.",
    "Added IAM, KMS, Secrets Manager, CloudTrail for PCI-DSS compliance.",
    "Added Aurora automated backups, PITR, cross-region snapshots.",
    "Updated data flow to include DynamoDB catalog reads.",
    "Restored Aurora read replicas for availability and spike load.",
    "Added DynamoDB automated backups and point-in-time recovery."
  ],
  "open_recommendations": [
    "Add Lambda for bursty async payment/order handlers.",
    "Add DynamoDB global tables for hot catalog reads.",
    "Define RTO/RPO and add circuit-breaker/retry patterns.",
    "Add API Gateway in front of ALB for rate limiting."
  ]
}
