import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { ApiError } from '@/api/client'
import { Card, ErrorState, Spinner } from '@/components/ui'

import { useMe } from './useAuth'

function describe(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return "This API has no sign-in endpoints. Update and restart the ArchonAI backend, then try again."
  }
  return error instanceof ApiError ? error.message : 'Your sign-in could not be checked. Please try again.'
}

/** Renders the app only for a signed-in user; otherwise sends them to /login and back afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe()
  const location = useLocation()

  if (me.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background">
        <Spinner label="Checking your sign-in" />
      </div>
    )
  }
  // A signed-in user keeps the app even if a later background check fails.
  if (me.data) return children
  if (me.isError) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background px-4">
        <Card className="w-full max-w-md">
          <ErrorState title="Can't check your sign-in" description={describe(me.error)} onRetry={() => void me.refetch()} isRetrying={me.isFetching} />
        </Card>
      </div>
    )
  }
  const next = `${location.pathname}${location.search}${location.hash}`
  return <Navigate to={next === '/' || next === '/dashboard' ? '/login' : `/login?next=${encodeURIComponent(next)}`} replace />
}
