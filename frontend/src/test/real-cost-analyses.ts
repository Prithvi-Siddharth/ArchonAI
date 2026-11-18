/**
 * Three real `cost_analysis` objects from GET /api/v1/architectures/jobs/{id}
 * (jobs 17e8c5b5, bab8871e, 21c17890), copied verbatim for tests: a seven-area
 * breakdown (incl. "networking/cdn"), an empty breakdown with one optimization
 * and one trade-off, and a differently worded disclaimer.
 */
import type { CostAnalysis } from '@/types/api'

export const REAL_COST_SEVEN_AREAS: CostAnalysis = {
  "estimated_monthly_range": "$4,120 - $34,800 per month (educational estimate)",
  "major_cost_drivers": [
    "Compute",
    "Database",
    "Networking"
  ],
  "relative_cost_breakdown": {
    "caching": "medium",
    "compute": "high",
    "storage": "low",
    "database": "high",
    "messaging": "low",
    "networking": "medium",
    "networking/cdn": "medium"
  },
  "optimizations": [
    "Apply Savings Plans / reserved capacity to Fargate vCPU and Aurora storage to cut baseline compute+DB cost",
    "Right-size Fargate task memory/CPU and use target-tracking scaling on request count to avoid over-provisioning at trough",
    "Use Aurora Serverless v2 for orders DB to scale IOPS/compute to demand during flash sales",
    "Enable CloudFront cache invalidation + long TTLs on images to reduce origin egress and Fargate load",
    "Use S3 Intelligent-Tiering / Glacier for cold order history and transaction logs",
    "Batch SQS messages and use short retention to minimize messaging cost",
    "Consolidate regions to single active + warm standby if 99.9% (not 99.99%) suffices, halving cross-region egress"
  ],
  "trade_offs": [
    "Active-active multi-region doubles compute/DB/network cost for higher availability than stated 99.9% needs",
    "Aurora PostgreSQL chosen for strong consistency at higher cost vs DynamoDB for catalog reads",
    "Fargate trades lower unit cost of EC2 for zero server ops and faster scale-out",
    "ElastiCache Redis adds cost but is required to hold sub-200ms hot catalog reads",
    "SQS decoupling adds latency for async order processing vs synchronous writes",
    "WAF + CloudFront add per-request cost but are mandatory for PCI-DSS and latency"
  ],
  "disclaimer": "This is an educational, order-of-magnitude estimate only. It is not an AWS quote and does not reflect real-time AWS pricing."
}

export const REAL_COST_EMPTY_BREAKDOWN: CostAnalysis = {
  "estimated_monthly_range": "$3,480 - $30,400 per month (educational estimate)",
  "major_cost_drivers": [
    "Compute",
    "Database",
    "Networking"
  ],
  "relative_cost_breakdown": {},
  "optimizations": [
    "Apply Savings Plans/Reserved Instances to steady-state Fargate and RDS baseline capacity, keeping on-demand headroom for spikes"
  ],
  "trade_offs": [
    "Fargate over EC2: higher per-vCPU cost, but removes server management and scales faster for flash-sale bursts"
  ],
  "disclaimer": "This is an educational, order-of-magnitude estimate only. It is not an AWS quote and does not reflect real-time AWS pricing."
}

export const REAL_COST_OTHER_DISCLAIMER: CostAnalysis = {
  "estimated_monthly_range": "$3,400 - $29,600 per month (educational estimate)",
  "major_cost_drivers": [
    "Compute",
    "Database",
    "Networking"
  ],
  "relative_cost_breakdown": {
    "compute": "high",
    "storage": "low",
    "database": "high",
    "networking": "high"
  },
  "optimizations": [
    "Use Savings Plans / reserved capacity for steady-state Fargate vCPU and Aurora storage",
    "Right-size Fargate task memory/CPU and set aggressive scale-down cooldowns to shed spike capacity fast",
    "Cache more catalog reads in CloudFront + Redis to cut DynamoDB read capacity and origin load",
    "Use DynamoDB on-demand or auto-scaling with lower baseline capacity for bursty reads",
    "Enable S3 Intelligent-Tiering / lifecycle rules for cold media and order history",
    "Scope WAF rules to reduce per-request WAF cost; cache at edge to lower WAF-processed requests",
    "Use Aurora Serverless v2 for variable order/payment write load instead of fixed instances"
  ],
  "trade_offs": [
    "Fargate over EC2: higher per-unit compute cost in exchange for zero server management and faster spike scaling",
    "Running Aurora + DynamoDB + Redis simultaneously: higher DB cost for strong consistency + high-throughput reads + low-latency sessions",
    "Multi-AZ redundancy across all tiers: higher cost for high availability and PCI-grade failover",
    "Global CDN + WAF: higher networking cost for low latency and PCI in-transit encryption at 500K scale",
    "No reserved capacity assumed: baseline reflects on-demand pricing, so steady-state cost is higher than a committed-use scenario"
  ],
  "disclaimer": "Educational, order-of-magnitude estimate only. Not an AWS quote; does not reflect real-time AWS pricing."
}
