import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { Toaster } from '@/components/ui'

// Library defaults for now; tune them when API integration starts.
const queryClient = new QueryClient()

/** App-wide context providers and the global toast outlet. Theme and UI state live in Zustand stores. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster />
    </QueryClientProvider>
  )
}
