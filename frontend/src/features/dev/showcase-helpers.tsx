import type { ReactNode } from 'react'

import { SectionHeader } from '@/components/ui'
import { cn } from '@/utils/cn'

export function ShowcaseSection({
  id,
  title,
  description,
  children,
}: {
  id: string
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section aria-labelledby={id} className="scroll-mt-6 space-y-4">
      <SectionHeader id={id} title={title} description={description} />
      {children}
    </section>
  )
}

/** A labelled group of examples. */
export function Example({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className="space-y-3">
      <p className="text-overline text-muted-foreground uppercase">{label}</p>
      <div className={cn('flex flex-wrap items-center gap-3', className)}>{children}</div>
    </div>
  )
}

/** Small toggle-button group for switching an example's state. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-md border border-border bg-surface p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'h-7 rounded-sm px-3 text-label transition-colors',
            value === option.value ? 'bg-surface-muted text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
