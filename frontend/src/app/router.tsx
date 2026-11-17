import { createBrowserRouter, Navigate } from 'react-router'

import { AppLayout } from '@/components/layout/AppLayout'
import { ArchitectureHistoryPage } from '@/features/architectures/ArchitectureHistoryPage'
import { NewArchitecturePage } from '@/features/architectures/NewArchitecturePage'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { NotFoundPage } from '@/features/not-found/NotFoundPage'
import { SettingsPage } from '@/features/settings/SettingsPage'

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
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
