import { cn } from '@/utils/cn'

import { TONE_FILL, type Tone } from './tones'

interface ProgressProps {
  /** 0..max. Leave undefined (or null) for an indeterminate bar. */
  value?: number | null
  max?: number
  /** Always required for screen readers; shown above the bar unless hideLabel. */
  label: string
  hideLabel?: boolean
  /** Show the percentage next to the label (determinate only). */
  showValue?: boolean
  tone?: Exclude<Tone, 'neutral'> | 'primary'
  size?: 'sm' | 'md'
  className?: string
}

export function Progress({
  value,
  max = 100,
  label,
  hideLabel = false,
  showValue = true,
  tone = 'primary',
  size = 'md',
  className,
}: ProgressProps) {
  const indeterminate = value === undefined || value === null
  const percent = indeterminate ? 0 : Math.round((Math.min(Math.max(value, 0), max) / max) * 100)
  const fill = tone === 'primary' ? 'bg-primary' : TONE_FILL[tone]

  return (
    <div className={cn('w-full', className)}>
      {!hideLabel && (
        <div className="mb-1.5 flex items-center justify-between gap-3 text-meta">
          <span className="font-medium">{label}</span>
          {showValue && !indeterminate && <span className="text-muted-foreground tabular-nums">{percent}%</span>}
        </div>
      )}
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : percent}
        className={cn('relative w-full overflow-hidden rounded-full bg-surface-muted', size === 'sm' ? 'h-1' : 'h-2')}
      >
        <div
          className={cn(
            'h-full rounded-full',
            fill,
            indeterminate ? 'w-2/5 motion-safe:animate-progress-indeterminate' : 'transition-[width] duration-300',
          )}
          style={indeterminate ? undefined : { width: `${percent}%` }}
        />
      </div>
    </div>
  )
}
