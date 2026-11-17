import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: ReactNode
  action?: ReactNode
  /** "danger" tints the icon for error states. */
  tone?: 'neutral' | 'danger'
  /** Less vertical padding, for use inside cards and tables. */
  compact?: boolean
  role?: 'alert' | 'status'
  className?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  tone = 'neutral',
  compact = false,
  role,
  className,
}: EmptyStateProps) {
  return (
    <div role={role} className={cn('flex flex-col items-center px-6 text-center', compact ? 'py-8' : 'py-14', className)}>
      <span
        className={cn(
          'flex size-10 items-center justify-center rounded-lg border',
          tone === 'danger'
            ? 'border-danger/25 bg-danger/10 text-danger'
            : 'border-border bg-surface-muted text-muted-foreground',
        )}
      >
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-card-title">{title}</h2>
      <p className="mt-1 max-w-sm text-muted-foreground">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
