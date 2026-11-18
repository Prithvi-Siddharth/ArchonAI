import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { shouldRetryQuery } from '@/api/client'
import { Toaster } from '@/components/ui'

const queryClient = new QueryClient({
  defaultOptions: {
    // Reads: one retry for temporary failures only; no refetch just because the tab regained focus.
    queries: { retry: shouldRetryQuery, refetchOnWindowFocus: false },
    // Writes are never retried automatically (a repeated job submission would create a second job).
    mutations: { retry: false },
  },
})

/** App-wide context providers and the global toast outlet. Theme and UI state live in Zustand stores. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster />
    </QueryClientProvider>
  )
}
