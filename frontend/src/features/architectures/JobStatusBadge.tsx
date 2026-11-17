import { StatusBadge, type Status } from '@/components/ui'
import type { JobStatus } from '@/types/architecture'

/** Backend job states mapped onto the design system's statuses, keeping the backend's wording. */
const JOB_STATUS: Record<JobStatus, { status: Status; label: string }> = {
  queued: { status: 'queued', label: 'Queued' },
  running: { status: 'running', label: 'Running' },
  succeeded: { status: 'completed', label: 'Succeeded' },
  failed: { status: 'failed', label: 'Failed' },
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { status: mapped, label } = JOB_STATUS[status]
  return <StatusBadge status={mapped} label={label} />
}
