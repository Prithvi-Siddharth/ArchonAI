import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { ApiError, shouldRetryQuery } from '@/api/client'
import { Toaster } from '@/components/ui'
import { ME_QUERY_KEY } from '@/features/auth/useAuth'
import type { User } from '@/types/api'

/** The app's query client. Exported as a factory so tests get the same rules. */
export function createAppQueryClient(): QueryClient {
  // Any 401 means the session cookie is missing or expired: mark the user signed out, and
  // RequireAuth sends them to the sign-in page (and back afterwards).
  const onError = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) client.setQueryData<User | null>(ME_QUERY_KEY, null)
  }
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      // Reads: one retry for temporary failures only; no refetch just because the tab regained focus.
      queries: { retry: shouldRetryQuery, refetchOnWindowFocus: false },
      // Writes are never retried automatically (a repeated job submission would create a second job).
      mutations: { retry: false },
    },
  })
  return client
}

const queryClient = createAppQueryClient()

/** App-wide context providers and the global toast outlet. Theme and UI state live in Zustand stores. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster />
    </QueryClientProvider>
  )
}
