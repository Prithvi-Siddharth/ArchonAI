import { RotateCw, TriangleAlert } from 'lucide-react'

import { Button } from './Button'
import { EmptyState } from './EmptyState'

interface ErrorStateProps {
  title?: string
  /** A user-safe explanation -- never raw error text or stack traces. */
  description?: string
  onRetry?: () => void
  retryLabel?: string
  isRetrying?: boolean
  compact?: boolean
  className?: string
}

/** Something failed to load: announced to screen readers, with an optional retry. */
export function ErrorState({
  title = 'Something went wrong',
  description = 'This content could not be loaded. Please try again.',
  onRetry,
  retryLabel = 'Try again',
  isRetrying = false,
  compact,
  className,
}: ErrorStateProps) {
  return (
    <EmptyState
      role="alert"
      tone="danger"
      icon={TriangleAlert}
      title={title}
      description={description}
      compact={compact}
      className={className}
      action={
        onRetry && (
          <Button variant="outline" onClick={onRetry} loading={isRetrying}>
            {!isRetrying && <RotateCw className="size-4" aria-hidden="true" />}
            {retryLabel}
          </Button>
        )
      }
    />
  )
}
