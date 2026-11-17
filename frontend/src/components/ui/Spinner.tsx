import { LoaderCircle } from 'lucide-react'

import { cn } from '@/utils/cn'

const SIZES = { sm: 'size-4', md: 'size-5', lg: 'size-8' } as const

interface SpinnerProps {
  size?: keyof typeof SIZES
  /** Announced to screen readers. */
  label?: string
  className?: string
}

export function Spinner({ size = 'md', label = 'Loading', className }: SpinnerProps) {
  return (
    <span role="status" className={cn('inline-flex text-muted-foreground', className)}>
      <LoaderCircle className={cn('animate-spin', SIZES[size])} aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  )
}
