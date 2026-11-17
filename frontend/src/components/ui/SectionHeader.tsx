import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

interface SectionHeaderProps {
  title: string
  description?: ReactNode
  actions?: ReactNode
  /** id for the heading, e.g. for aria-labelledby on the section. */
  id?: string
  className?: string
}

/** Heading for a section within a page (h2). Pages use PageHeader (h1). */
export function SectionHeader({ title, description, actions, id, className }: SectionHeaderProps) {
  return (
    <div className={cn('flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="min-w-0">
        <h2 id={id} className="text-section-title">
          {title}
        </h2>
        {description && <p className="mt-0.5 text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
