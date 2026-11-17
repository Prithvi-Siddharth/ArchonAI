import { cn } from '@/utils/cn'

import { Badge } from './Badge'
import { TONE_FILL, TONE_TEXT, type Tone } from './tones'

/** Generic lifecycle statuses; features map their own states onto these. */
export type Status = 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

type Dot = 'solid' | 'hollow' | 'pulse'

export const STATUS_META: Record<Status, { label: string; tone: Tone; dot: Dot }> = {
  pending: { label: 'Pending', tone: 'warning', dot: 'solid' },
  queued: { label: 'Queued', tone: 'neutral', dot: 'solid' },
  running: { label: 'Running', tone: 'info', dot: 'pulse' },
  completed: { label: 'Completed', tone: 'success', dot: 'solid' },
  failed: { label: 'Failed', tone: 'danger', dot: 'solid' },
  cancelled: { label: 'Cancelled', tone: 'neutral', dot: 'hollow' },
}

function StatusDot({ tone, dot, className }: { tone: Tone; dot: Dot; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'shrink-0 rounded-full',
        dot === 'hollow' ? cn('border-[1.5px] border-current', TONE_TEXT[tone]) : TONE_FILL[tone],
        dot === 'pulse' && 'motion-safe:animate-pulse',
        className,
      )}
    />
  )
}

interface StatusProps {
  status: Status
  /** Overrides the default label, e.g. "Succeeded" for a completed job. */
  label?: string
  className?: string
}

/** Pill with a colored dot -- for tables and lists. */
export function StatusBadge({ status, label, className }: StatusProps) {
  const meta = STATUS_META[status]
  return (
    <Badge tone={meta.tone} className={className}>
      <StatusDot tone={meta.tone} dot={meta.dot} className="size-1.5" />
      {label ?? meta.label}
    </Badge>
  )
}

/** Dot and plain text -- for dense layouts and inline status. */
export function StatusIndicator({ status, label, className }: StatusProps) {
  const meta = STATUS_META[status]
  return (
    <span className={cn('inline-flex items-center gap-2 text-body', className)}>
      <StatusDot tone={meta.tone} dot={meta.dot} className="size-2" />
      {label ?? meta.label}
    </span>
  )
}
