import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'

import { AppLayout } from '@/components/layout/AppLayout'
import { Spinner } from '@/components/ui'
import { ArchitectureHistoryPage } from '@/features/architectures/ArchitectureHistoryPage'
import { NewArchitecturePage } from '@/features/architectures/NewArchitecturePage'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { NotFoundPage } from '@/features/not-found/NotFoundPage'
import { SettingsPage } from '@/features/settings/SettingsPage'

/**
 * Development-only routes, not linked from the navigation. `import.meta.env.DEV`
 * is false in production builds, so these routes and their lazily loaded code
 * are left out of the build entirely.
 */
const devRoutes: RouteObject[] = import.meta.env.DEV
  ? [
      {
        path: 'dev/components',
        // Shown inside the layout while the page's code loads on a direct visit.
        HydrateFallback: () => (
          <div className="flex justify-center py-16">
            <Spinner label="Loading page" />
          </div>
        ),
        lazy: async () => ({
          Component: (await import('@/features/dev/ComponentShowcasePage')).ComponentShowcasePage,
        }),
      },
    ]
  : []

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'architectures/new', element: <NewArchitecturePage /> },
      { path: 'architectures/history', element: <ArchitectureHistoryPage /> },
      { path: 'settings', element: <SettingsPage /> },
      ...devRoutes,
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
