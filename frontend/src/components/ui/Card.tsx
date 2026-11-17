import type { ComponentProps, ReactNode } from 'react'

import { cn } from '@/utils/cn'

export function Card({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('rounded-lg border border-border bg-surface shadow-card', className)} {...props} />
}

interface CardHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Right-aligned controls, e.g. a "View all" link. */
  action?: ReactNode
  className?: string
}

export function CardHeader({ title, description, action, className }: CardHeaderProps) {
  return (
    <div className={cn('flex items-start justify-between gap-4 border-b border-border px-5 py-4', className)}>
      <div className="min-w-0">
        <h2 className="text-card-title">{title}</h2>
        {description && <p className="mt-0.5 text-muted-foreground">{description}</p>}
      </div>
      {action && <div className="-my-1 shrink-0">{action}</div>}
    </div>
  )
}

export function CardContent({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('px-5 py-4', className)} {...props} />
}

/** Actions row at the bottom of a card. */
export function CardFooter({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      className={cn('flex flex-wrap items-center justify-end gap-2 border-t border-border px-5 py-3', className)}
      {...props}
    />
  )
}
