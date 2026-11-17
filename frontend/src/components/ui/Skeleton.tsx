import { cn } from '@/utils/cn'

/** A placeholder block for loading content; size it with className (e.g. "h-4 w-32"). */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('rounded-md bg-surface-muted motion-safe:animate-pulse', className)} />
}
