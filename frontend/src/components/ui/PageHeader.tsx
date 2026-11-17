import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  description?: string
  /** Shown next to the title, e.g. a status badge. */
  badge?: ReactNode
  /** Page-level actions, aligned right on wider screens. */
  actions?: ReactNode
}

/** The page's h1, description and primary actions. */
export function PageHeader({ title, description, badge, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-page-title">{title}</h1>
          {badge}
        </div>
        {description && <p className="mt-1 max-w-readable text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
