/**
 * Activity page and the sidebar's in-progress badge, against a fake GET /jobs.
 * fetch is stubbed in every test: nothing reaches a real backend.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, MemoryRouter, RouterProvider, useParams } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { findPageMeta, NAV_SECTIONS } from '@/components/layout/navigation'
import { Sidebar } from '@/components/layout/Sidebar'
import type { JobHistoryItem, JobHistoryResponse } from '@/types/api'
import type { JobStatus } from '@/types/architecture'

import { ActivityPage } from './ActivityPage'

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()

function item(n: number, status: JobStatus, overrides: Partial<JobHistoryItem> = {}): JobHistoryItem {
  const finished = status === 'succeeded' || status === 'failed'
  return {
    job_id: `${String(n).padStart(8, '0')}-aaaa-bbbb-cccc-dddddddddddd`,
    user_request: `Design system number ${n} for 10,000 users`,
    status,
    attempts: status === 'queued' ? 0 : 1,
    created_at: minutesAgo(n * 10),
    started_at: status === 'queued' ? null : minutesAgo(n * 10 - 1),
    finished_at: finished ? minutesAgo(n * 10 - 6) : null,
    updated_at: minutesAgo(n * 10 - 6),
    error: status === 'failed' ? { status_code: 429, message: 'The AI provider is rate limiting requests.' } : null,
    summary:
      status === 'succeeded'
        ? { approved: true, critic_score: 82, architecture_version: 1, aws_service_count: 8, estimated_monthly_range: '$100 - $200', max_revisions_reached: false }
        : null,
    ...overrides,
  }
}

/** A fake GET /jobs over `state.jobs` (newest first); swap the jobs to simulate progress. */
function fakeJobs(initial: JobHistoryItem[], { fail = false } = {}) {
  const state = { jobs: initial, fail }
  const requests: URLSearchParams[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input, 'http://localhost')
      if (url.pathname !== '/api/v1/architectures/jobs' || (init?.method ?? 'GET') !== 'GET') throw new Error(`unexpected request ${input}`)
      requests.push(url.searchParams)
      if (state.fail) return new Response(JSON.stringify({ detail: 'Job store is unavailable. Please retry later.' }), { status: 503 })
      const limit = Number(url.searchParams.get('limit'))
      const offset = Number(url.searchParams.get('offset'))
      const counts = { queued: 0, running: 0, succeeded: 0, failed: 0 }
      for (const j of state.jobs) counts[j.status] += 1
      const body: JobHistoryResponse = { items: state.jobs.slice(offset, offset + limit), total: state.jobs.length, limit, offset, counts }
      return new Response(JSON.stringify(body), { status: 200 })
    }),
  )
  return { state, requests }
}

function Stub({ label }: { label: string }) {
  const { jobId } = useParams()
  return <p>{`${label} ${jobId ?? ''}`.trim()}</p>
}

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })

function renderPage() {
  const router = createMemoryRouter(
    [
      { path: '/activity', element: <ActivityPage /> },
      { path: '/architectures/new', element: <Stub label="New page" /> },
      { path: '/architectures/history', element: <Stub label="History page" /> },
      { path: '/architectures/:jobId', element: <Stub label="Job page" /> },
      { path: '/architectures/:jobId/results', element: <Stub label="Results page" /> },
    ],
    { initialEntries: ['/activity'] },
  )
  render(
    <QueryClientProvider client={newClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}

const inProgress = () => within(screen.getByRole('region', { name: /^In progress/ }))
const finished = () => within(screen.getByRole('region', { name: 'Recently finished' }))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Activity page', () => {
  it('shows running jobs first, then queued jobs in the order they will run, each with live progress', async () => {
    // Newest first, as the API returns them.
    fakeJobs([item(1, 'queued'), item(2, 'queued'), item(3, 'running'), item(4, 'succeeded'), item(5, 'failed')])
    renderPage()

    const cards = await screen.findAllByRole('article')
    expect(cards.map((card) => card.getAttribute('data-job-id')?.slice(0, 8))).toEqual(['00000003', '00000002', '00000001'])
    expect(within(cards[0]).getByRole('heading', { level: 3, name: 'Generating architecture' })).toBeTruthy()
    expect(within(cards[1]).getByRole('heading', { level: 3, name: 'Waiting for a worker' })).toBeTruthy()
    expect(within(cards[0]).getByText('Design system number 3 for 10,000 users')).toBeTruthy()
    expect(within(cards[0]).getByRole('list', { name: 'Job progress' })).toBeTruthy()
    expect(within(cards[0]).getByText(/Updates automatically every 5 seconds/)).toBeTruthy()
    expect(screen.getByText('3 in progress')).toBeTruthy()
    expect(inProgress().getByRole('heading', { level: 2, name: /In progress/ })).toBeTruthy()

    await userEvent.click(within(cards[0]).getByRole('link', { name: /Open job/ }))
    expect(await screen.findByText(`Job page ${item(3, 'running').job_id}`)).toBeTruthy()
  })

  it('lists recently finished jobs with their outcome and the right actions', async () => {
    fakeJobs([item(1, 'running'), item(2, 'succeeded'), item(3, 'failed')])
    renderPage()

    const list = await waitFor(() => finished().getByRole('list', { name: 'Recently finished jobs' }))
    const rows = within(list).getAllByRole('listitem').filter((li) => li.hasAttribute('data-job-id'))
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByRole('list', { name: 'Progress of job 00000002' })).toBeTruthy()
    expect(within(rows[0]).getByRole('link', { name: /View Results/ }).getAttribute('href')).toBe(`/architectures/${item(2, 'succeeded').job_id}/results`)
    expect(within(rows[1]).queryByRole('link', { name: /View Results/ })).toBeNull()
    expect(within(rows[1]).getByText(/The AI provider is rate limiting requests\./)).toBeTruthy()
    expect(within(rows[1]).getByText('(Error 429)')).toBeTruthy()
    expect(within(rows[1]).getByRole('link', { name: /View Job/ }).getAttribute('href')).toBe(`/architectures/${item(3, 'failed').job_id}`)
  })

  it('says nothing is running and keeps at most five finished jobs', async () => {
    fakeJobs(Array.from({ length: 7 }, (_, i) => item(i + 1, 'succeeded')))
    renderPage()

    expect(await screen.findByText('No jobs running right now')).toBeTruthy()
    expect(inProgress().getByRole('link', { name: /New Architecture/ }).getAttribute('href')).toBe('/architectures/new')
    expect(screen.queryByText(/in progress$/)).toBeNull()
    const list = finished().getByRole('list', { name: 'Recently finished jobs' })
    expect(within(list).getAllByRole('link', { name: /View Job/ })).toHaveLength(5)
    expect(finished().getByRole('link', { name: /All jobs in Architecture History/ }).getAttribute('href')).toBe('/architectures/history')
  })

  it('shows empty states for a brand-new account', async () => {
    fakeJobs([])
    renderPage()
    expect(await screen.findByText('No jobs running right now')).toBeTruthy()
    expect(screen.getByText('No finished jobs yet')).toBeTruthy()
  })

  it('moves a job to Recently finished once it completes, and refreshes the other history lists', async () => {
    const fake = fakeJobs([item(1, 'running'), item(2, 'succeeded')])
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Generating architecture' })).toBeTruthy()

    fake.state.jobs = [item(1, 'succeeded'), item(2, 'succeeded')]
    const before = fake.requests.length
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    expect(await screen.findByText('No jobs running right now')).toBeTruthy()
    expect(finished().getAllByRole('link', { name: /View Results/ })).toHaveLength(2)
    // The refresh itself, then the follow-up refresh of every history list after a job finished.
    await waitFor(() => expect(fake.requests.length).toBeGreaterThanOrEqual(before + 2))
  })

  it('points to History when an in-progress job is older than the jobs it read', async () => {
    // 20 newer finished jobs, then an old queued one the page doesn't receive.
    const fake = fakeJobs([...Array.from({ length: 20 }, (_, i) => item(i + 1, 'succeeded')), item(21, 'queued')])
    renderPage()

    expect(await screen.findByText(/1 older job is also in progress/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'See Architecture History' }).getAttribute('href')).toBe('/architectures/history')
    expect(screen.getByText('1 in progress')).toBeTruthy()
    expect(fake.requests[0].get('limit')).toBe('20')
    expect(fake.requests[0].get('offset')).toBe('0')
    expect(fake.requests[0].has('user_id')).toBe(false)
  })

  it('shows an error with retry when the jobs cannot be loaded', async () => {
    const fake = fakeJobs([item(1, 'running')], { fail: true })
    renderPage()

    expect(await screen.findByText("Couldn't load your activity")).toBeTruthy()
    expect(screen.getByText('Job store is unavailable. Please retry later.')).toBeTruthy()

    fake.state.fail = false
    await userEvent.click(screen.getByRole('button', { name: /Try again|Retry/ }))
    expect(await screen.findByRole('heading', { name: 'Generating architecture' })).toBeTruthy()
  })
})

describe('Activity in the sidebar', () => {
  it('is a Workspace link after Architecture History with its own breadcrumb', () => {
    const workspace = NAV_SECTIONS.find((section) => section.title === 'Workspace')
    expect(workspace?.items.map((i) => i.label)).toEqual(['Dashboard', 'New Architecture', 'Architecture History', 'Activity'])
    expect(findPageMeta('/activity')).toEqual({ section: 'Workspace', label: 'Activity' })
  })

  function renderSidebar() {
    render(
      <QueryClientProvider client={newClient()}>
        <MemoryRouter initialEntries={['/dashboard']}>
          <Sidebar />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('shows how many jobs are in progress next to Activity', async () => {
    const fake = fakeJobs([item(1, 'running'), item(2, 'queued'), item(3, 'succeeded')])
    renderSidebar()

    const link = await screen.findByRole('link', { name: /^Activity\s*, 2 jobs in progress$/ })
    expect(link.getAttribute('href')).toBe('/activity')
    expect(within(link).getByText('2')).toBeTruthy()
    // The badge only needs the counts, so it asks for a single row.
    expect(fake.requests[0].get('limit')).toBe('1')
  })

  it('shows no badge when nothing is in progress', async () => {
    const fake = fakeJobs([item(1, 'succeeded')])
    renderSidebar()

    await waitFor(() => expect(fake.requests.length).toBeGreaterThan(0))
    expect(screen.getByRole('link', { name: 'Activity' }).getAttribute('href')).toBe('/activity')
    expect(screen.queryByText(/in progress/)).toBeNull()
  })
})
