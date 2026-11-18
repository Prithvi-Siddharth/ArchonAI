import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { createMemoryRouter, RouterProvider, useParams } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { findPageMeta } from '@/components/layout/navigation'
import { RecentArchitectures } from '@/features/dashboard/RecentArchitectures'

import { SubmissionSuccess } from './SubmissionSuccess'

function TrackingPageStub() {
  const { jobId } = useParams()
  return <p>Tracking {jobId}</p>
}

function renderAt(path: string, element: ReactNode) {
  const router = createMemoryRouter(
    [
      { path, element },
      { path: '/architectures/:jobId', element: <TrackingPageStub /> },
    ],
    { initialEntries: [path] },
  )
  render(<RouterProvider router={router} />)
  return userEvent.setup()
}

afterEach(() => cleanup())

describe('navigation to the tracking page', () => {
  it('"Track progress" on the submission success panel opens the job', async () => {
    const user = renderAt(
      '/architectures/new',
      <SubmissionSuccess
        submitted={{
          job: { job_id: 'job-123', status: 'queued', status_url: '/api/v1/architectures/jobs/job-123' },
          request: 'Design a blog.',
          submittedAt: new Date().toISOString(),
        }}
        onNewRequest={() => {}}
      />,
    )

    await user.click(screen.getByRole('link', { name: 'Track progress' }))
    expect(await screen.findByText('Tracking job-123')).toBeTruthy()
  })

  it('a dashboard entry opens its job', async () => {
    const user = renderAt(
      '/dashboard',
      <RecentArchitectures
        items={[
          {
            job_id: 'job-9',
            user_request: 'Design a payments API.',
            status: 'running',
            attempts: 1,
            created_at: new Date().toISOString(),
            started_at: new Date().toISOString(),
            finished_at: null,
            updated_at: new Date().toISOString(),
            error: null,
            summary: null,
          },
        ]}
        loading={false}
        onRefresh={() => {}}
        refreshing={false}
      />,
    )

    await user.click(screen.getByRole('link', { name: 'Design a payments API.' }))
    expect(await screen.findByText('Tracking job-9')).toBeTruthy()
  })
})

describe('page title and breadcrumb for job pages', () => {
  it('names a job page by its short id', () => {
    expect(findPageMeta('/architectures/7f3c9a21-5d4e-4b8a-9c1f-2e6d8b0a4f13')).toEqual({ section: 'Workspace', label: 'Job 7f3c9a21' })
  })

  it('names a results page by its short id', () => {
    expect(findPageMeta('/architectures/7f3c9a21-5d4e-4b8a-9c1f-2e6d8b0a4f13/results')).toEqual({ section: 'Workspace', label: 'Results 7f3c9a21' })
  })

  it('leaves the existing architecture pages alone', () => {
    expect(findPageMeta('/architectures/new')).toEqual({ section: 'Workspace', label: 'New Architecture' })
    expect(findPageMeta('/architectures/history')).toEqual({ section: 'Workspace', label: 'Architecture History' })
  })
})
