/**
 * Two real `architecture` objects returned by GET /api/v1/architectures/jobs/{id}
 * (jobs 17e8c5b5 and 21c17890), copied verbatim for tests. They show what the
 * diagram must cope with: free-text, combined endpoint labels ("CloudFront + WAF"),
 * labels that are not service names ("User"), a disconnected pair ("Route 53 + ALB"
 * vs "ALB"), fan-out, and a step that points back to an earlier endpoint.
 */
import type { Architecture } from '@/types/api'

export const REAL_ARCHITECTURE_COMBINED: Architecture = {
  "summary": "Multi-region e-commerce on ECS, Aurora, DynamoDB, S3, SQS, CloudFront, WAF, KMS for 500K users.",
  "services": [
    {
      "name": "Amazon CloudFront + AWS WAF",
      "category": "Networking/CDN",
      "purpose": "Edge-caches catalog and static assets; filters malicious traffic.",
      "justification": "Edge caching meets sub-200ms latency for 500K users; WAF enforces PCI-DSS."
    },
    {
      "name": "Amazon Route 53 + ALB",
      "category": "Networking",
      "purpose": "Anycast DNS routes to nearest healthy region load balancer.",
      "justification": "Anycast routing gives low latency and high availability across regions."
    },
    {
      "name": "Amazon ECS Fargate + Auto Scaling",
      "category": "Compute",
      "purpose": "Auto scaling container pools run stateless API and order services.",
      "justification": "Fargate removes server ops; auto scaling absorbs flash-sale write spikes."
    },
    {
      "name": "Amazon Aurora PostgreSQL",
      "category": "Database",
      "purpose": "Strongly consistent orders/payments; read replicas serve catalog; PITR plus cross-region snapshots for backups.",
      "justification": "Aurora multi-AZ plus read replicas ensure strong consistency, high availability, and catalog throughput."
    },
    {
      "name": "Amazon ElastiCache Redis",
      "category": "Caching",
      "purpose": "Absorbs read-heavy catalog traffic with sub-200ms hot data access.",
      "justification": "In-memory cache keeps hot product data under 200ms for read-heavy traffic."
    },
    {
      "name": "Amazon S3",
      "category": "Storage",
      "purpose": "Object storage for product images, profiles, and encrypted logs.",
      "justification": "S3 with encryption at rest stores images, profiles, and transaction logs."
    },
    {
      "name": "Amazon SQS",
      "category": "Messaging",
      "purpose": "Durable queue with idempotency keys and dead-letter queues for bursty writes.",
      "justification": "SQS decouples bursty writes; idempotency keys and dead-letter queues prevent duplicates."
    },
    {
      "name": "Amazon DynamoDB + Aurora PITR",
      "category": "Database",
      "purpose": "DynamoDB serves high-throughput catalog reads; PITR plus cross-region snapshots back up Aurora.",
      "justification": "DynamoDB handles 500K concurrent catalog reads; PITR plus cross-region snapshots enable Aurora backups."
    },
    {
      "name": "AWS CloudTrail + KMS + Secrets Manager",
      "category": "Security",
      "purpose": "CloudTrail audits, KMS encrypts, Secrets Manager stores PCI-DSS credentials.",
      "justification": "CloudTrail, KMS, Secrets Manager satisfy PCI-DSS audit, encryption, and secret management."
    }
  ],
  "data_flow": [
    {
      "step": 1,
      "source": "User browser",
      "destination": "CloudFront + WAF",
      "description": "Edge cache and WAF filter user requests."
    },
    {
      "step": 2,
      "source": "CloudFront + WAF",
      "destination": "Route 53 + ALB",
      "description": "Anycast DNS routes to nearest healthy load balancer."
    },
    {
      "step": 3,
      "source": "ALB",
      "destination": "ECS Fargate",
      "description": "Auto scaling Fargate tasks in private subnet process API."
    },
    {
      "step": 4,
      "source": "ECS Fargate",
      "destination": "DynamoDB + ElastiCache",
      "description": "Hot catalog reads served from DynamoDB and Redis."
    },
    {
      "step": 5,
      "source": "ECS Fargate",
      "destination": "Aurora + SQS",
      "description": "Orders written to Aurora; bursty writes queued to SQS."
    }
  ],
  "version": 2,
  "change_log": [
    "Added DynamoDB for 500K concurrent catalog reads.",
    "Added Aurora PITR plus cross-region snapshot backups.",
    "Added CloudTrail, KMS, Secrets Manager for PCI-DSS.",
    "Added SQS idempotency keys and dead-letter queues.",
    "Restored Aurora read replicas for high-throughput catalog reads."
  ]
}

export const REAL_ARCHITECTURE_BACKWARD: Architecture = {
  "summary": "Multi-AZ, PCI-segregated e-commerce platform with CDN, auto scaling compute, split databases, and DR.",
  "services": [
    {
      "name": "Amazon CloudFront + AWS WAF",
      "category": "Networking",
      "purpose": "Global CDN and WAF for catalog, images, and TLS termination.",
      "justification": "Edge caching cuts origin load; WAF enforces TLS and PCI in-transit encryption."
    },
    {
      "name": "Application Load Balancer",
      "category": "Networking",
      "purpose": "Routes traffic to multi-AZ compute and PCI payment zone.",
      "justification": "Distributes spiky traffic across AZs and health-checks backends for high availability."
    },
    {
      "name": "Amazon ECS (Fargate) + Auto Scaling + AWS Lambda",
      "category": "Compute",
      "purpose": "Stateless web/API tier, isolated PCI payment tasks, and Lambda payment bursts in private subnet.",
      "justification": "Fargate removes server management; auto scaling and Lambda pre-warm ride flash-sale spikes."
    },
    {
      "name": "Amazon Aurora (PostgreSQL)",
      "category": "Database",
      "purpose": "Strongly consistent orders/payments with multi-AZ, read replicas, cross-region replica, RTO/RPO, retries, circuit breakers.",
      "justification": "Strong consistency, read replicas, cross-region replica, RTO 60s/RPO 0s, retries, circuit breakers."
    },
    {
      "name": "Amazon DynamoDB + Amazon ElastiCache (Redis)",
      "category": "Database",
      "purpose": "Strongly-consistent catalog reads with cache invalidation and session/cart state, multi-AZ.",
      "justification": "Strongly-consistent reads and fast key-value state meet sub-200ms latency at scale."
    },
    {
      "name": "Amazon S3",
      "category": "Storage",
      "purpose": "Product images/media with encryption and backups.",
      "justification": "Durable, encrypted media storage with backups; CDN distribution reduces origin egress."
    },
    {
      "name": "AWS CloudTrail + AWS Secrets Manager",
      "category": "Security",
      "purpose": "PCI-DSS audit logging and secure secrets management.",
      "justification": "CloudTrail logs API activity; Secrets Manager stores encrypted DB/payment credentials."
    }
  ],
  "data_flow": [
    {
      "step": 1,
      "source": "User",
      "destination": "CloudFront + WAF",
      "description": "User request hits CDN; WAF enforces TLS and PCI checks."
    },
    {
      "step": 2,
      "source": "CloudFront + WAF",
      "destination": "Application Load Balancer",
      "description": "ALB routes to nearest healthy AZ compute or PCI payment zone."
    },
    {
      "step": 3,
      "source": "Application Load Balancer",
      "destination": "ECS (Fargate) + Lambda",
      "description": "Auto-scaled ECS Fargate task or Lambda payment burst processes request."
    },
    {
      "step": 4,
      "source": "ECS (Fargate) + Lambda",
      "destination": "DynamoDB / ElastiCache",
      "description": "API reads strongly-consistent catalog from DynamoDB, cart from Redis."
    },
    {
      "step": 5,
      "source": "ECS (Fargate) + Lambda",
      "destination": "Amazon Aurora",
      "description": "Orders/payments written to Aurora in private subnet with retries and circuit breakers."
    },
    {
      "step": 6,
      "source": "ECS (Fargate) + Lambda",
      "destination": "User",
      "description": "Response returns via ALB and CDN to user."
    }
  ],
  "version": 3,
  "change_log": [
    "Added segregated PCI payment zone with isolated ECS tasks and network controls.",
    "Enabled DynamoDB strongly-consistent reads with cache invalidation for sales.",
    "Defined Aurora RTO 60s/RPO 0s plus retry and circuit-breaker policies.",
    "Consolidated catalog reads to DynamoDB, removing redundant Aurora catalog cost.",
    "Added Lambda for payment bursts to pre-warm capacity during spikes."
  ]
}
