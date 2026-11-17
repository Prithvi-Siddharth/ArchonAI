import { Badge, type BadgeTone } from '@/components/ui/Badge'
import type { JobStatus } from '@/types/architecture'

const STATUS: Record<JobStatus, { label: string; tone: BadgeTone }> = {
  queued: { label: 'Queued', tone: 'neutral' },
  running: { label: 'Running', tone: 'info' },
  succeeded: { label: 'Succeeded', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { label, tone } = STATUS[status]
  return (
    <Badge tone={tone}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
      {label}
    </Badge>
  )
}
