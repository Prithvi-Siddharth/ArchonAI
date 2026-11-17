/**
 * PLACEHOLDER DATA -- Phase 1 only.
 *
 * Every number and row on the dashboard comes from this file, and only
 * DashboardPage imports it. To switch to real data, replace these two values
 * with API data in DashboardPage; the dashboard components already take plain
 * props. Note: the backend has no job-list or statistics endpoint yet.
 */
import type { ArchitectureSummary, JobStats } from '@/types/architecture'

function minutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString()
}

export const placeholderJobStats: JobStats = {
  total: 128,
  succeeded: 114,
  failed: 9,
}

export const placeholderRecentArchitectures: ArchitectureSummary[] = [
  {
    jobId: '7f3c9a21-5d4e-4b8a-9c1f-2e6d8b0a4f13',
    request: 'IoT telemetry ingestion for 20,000 devices with 90-day retention',
    status: 'queued',
    createdAt: minutesAgo(1),
    serviceCount: null,
    criticScore: null,
  },
  {
    jobId: 'b81e4d07-2a6c-4f39-8e5b-71c0d9a3e2f8',
    request: 'Real-time chat backend for a 50,000-user mobile app',
    status: 'running',
    createdAt: minutesAgo(4),
    serviceCount: null,
    criticScore: null,
  },
  {
    jobId: 'e4a2c6f9-8b1d-4e7a-a3c5-0f9b2d6e8c41',
    request: 'E-commerce platform for 2 million users with flash-sale traffic spikes',
    status: 'succeeded',
    createdAt: minutesAgo(26),
    serviceCount: 9,
    criticScore: 82,
  },
  {
    jobId: '3d9b0e58-6f2a-4c1d-b7e9-5a8c3f0d2b76',
    request: 'Blogging platform for 10,000 monthly readers',
    status: 'succeeded',
    createdAt: minutesAgo(3 * 60),
    serviceCount: 6,
    criticScore: 88,
  },
  {
    jobId: '9c17f2ab-4e8d-4a6b-9f0c-3b5e7d1a9c28',
    request: 'HIPAA-aligned patient records API with audit logging',
    status: 'failed',
    createdAt: minutesAgo(26 * 60),
    serviceCount: null,
    criticScore: null,
  },
  {
    jobId: 'a05d7e34-1c9b-4d2e-8a6f-e3b0c5d9f714',
    request: 'Video transcoding pipeline for user-uploaded content',
    status: 'succeeded',
    createdAt: minutesAgo(2 * 24 * 60 + 90),
    serviceCount: 8,
    criticScore: 71,
  },
]
