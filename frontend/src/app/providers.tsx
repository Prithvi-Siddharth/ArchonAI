import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

// Library defaults for now; tune them when API integration starts.
const queryClient = new QueryClient()

/** App-wide context providers. Theme and UI state live in the Zustand store and need none. */
export function AppProviders({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
