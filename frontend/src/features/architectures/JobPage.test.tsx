import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { JOBS, json, makeJob, minutesAgo } from '@/test/job-fixtures'
import type { JobStatusResponse } from '@/types/api'

import { JobPage } from './JobPage'

let reply: () => Response | Promise<Response>

function renderJobPage(jobId = 'job-1') {
  vi.stubGlobal('fetch', vi.fn(async () => reply()))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [
      { path: '/architectures/:jobId', element: <JobPage /> },
      { path: '/architectures/new', element: <p>New architecture page</p> },
      { path: '/dashboard', element: <p>Dashboard page</p> },
    ],
    { initialEntries: [`/architectures/${jobId}`] },
  )
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { client, router, user: userEvent.setup() }
}

const currentStep = () =>
  within(screen.getByRole('list', { name: 'Job progress' }))
    .getAllByRole('listitem')
    .find((item) => item.getAttribute('aria-current') === 'step')

afterEach(() => cleanup())

describe('JobPage', () => {
  it('shows a loading state until the status arrives', () => {
    reply = () => new Promise(() => {})
    renderJobPage()
    expect(screen.getByText('Loading job')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Architecture job' })).toBeTruthy()
  })

  it.each<[string, JobStatusResponse, string, string | null, string]>([
    ['queued', JOBS.queued, 'Waiting for a worker', 'Queued', 'starts as soon as a worker is free'],
    ['running', JOBS.running, 'Generating architecture', 'Running', 'usually takes several minutes'],
    ['retrying (queued + error)', JOBS.retryWaiting, 'Retrying after a temporary problem', 'Queued', 'retried automatically'],
    ['retrying (running + error)', JOBS.retryRunning, 'Retrying', 'Running', 'Attempt 2 is running after a temporary problem.'],
    ['succeeded', JOBS.succeeded, 'Architecture ready', null, 'generated successfully'],
    ['failed', JOBS.failed, 'Generation failed', null, 'will not be retried'],
  ])('%s', async (_name, job, title, step, message) => {
    reply = () => json(200, job)
    renderJobPage()

    expect(await screen.findByRole('heading', { name: title })).toBeTruthy()
    expect(screen.getByText(new RegExp(message.replace('.', '\\.')))).toBeTruthy()
    if (step) expect(currentStep()?.textContent).toContain(step)
    else expect(currentStep()).toBeUndefined()

    const active = step !== null
    expect(screen.queryByRole('progressbar') !== null).toBe(active)
    expect(screen.queryByText(/Updates automatically every 5 seconds/) !== null).toBe(active)
    expect(screen.queryByText('Final status. This job will not change again.') !== null).toBe(!active)
    expect(screen.getAllByText(job.job_id).length).toBeGreaterThan(0)
  })

  it('shows the retry reason while retrying', async () => {
    reply = () => json(200, JOBS.retryRunning)
    renderJobPage()
    expect(await screen.findByText('LLM provider rate limit reached. Please retry later.')).toBeTruthy()
    expect(screen.getByText('Attempt 2')).toBeTruthy()
  })

  it("shows a failed job's safe error, its code, and a way to start again", async () => {
    reply = () => json(200, JOBS.failed)
    renderJobPage()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('LLM provider rate limit reached. Please retry later.')
    expect(alert.textContent).toContain('Error 429')
    expect(screen.getByRole('link', { name: 'Submit a new request' }).getAttribute('href')).toBe('/architectures/new')
  })

  it('links a succeeded job to its results page', async () => {
    reply = () => json(200, JOBS.succeeded)
    renderJobPage()
    const link = await screen.findByRole('link', { name: 'View results' })
    expect(link.getAttribute('href')).toBe('/architectures/job-1/results')
  })

  it('says when an attempt is taking longer than expected (over 15 minutes)', async () => {
    reply = () => json(200, makeJob({ status: 'running', attempts: 1, created_at: minutesAgo(17), started_at: minutesAgo(16) }))
    renderJobPage()
    expect(await screen.findByText(/has been running for over 15 minutes/)).toBeTruthy()
  })

  it('shows "Job not found" for a 404', async () => {
    reply = () => json(404, { detail: 'Job not found.' })
    renderJobPage('missing-job')
    expect(await screen.findByText('Job not found')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Go to dashboard' })).toBeTruthy()
  })

  it('offers Try again when the first load fails, and recovers', async () => {
    reply = () => json(503, { detail: 'Job store is unavailable. Please retry later.' })
    const { user } = renderJobPage()

    expect(await screen.findByText("Couldn't load this job")).toBeTruthy()
    expect(screen.getByText('Job store is unavailable. Please retry later.')).toBeTruthy()

    reply = () => json(200, JOBS.running)
    await user.click(screen.getByRole('button', { name: /Try again/ }))
    expect(await screen.findByRole('heading', { name: 'Generating architecture' })).toBeTruthy()
  })

  it('keeps the last known status when a refresh fails', async () => {
    reply = () => json(200, JOBS.running)
    const { client } = renderJobPage()
    expect(await screen.findByRole('heading', { name: 'Generating architecture' })).toBeTruthy()

    reply = () => json(503, { detail: 'Job store is unavailable. Please retry later.' })
    await act(() => client.refetchQueries())

    expect(await screen.findByText(/Couldn't refresh the status: Job store is unavailable/)).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Generating architecture' })).toBeTruthy()
  })
})
