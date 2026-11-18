import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { JOBS, json, makeJob, makeResult, minutesAgo } from '@/test/job-fixtures'
import type { JobStatusResponse } from '@/types/api'

import { ResultsPage } from './ResultsPage'

let reply: () => Response | Promise<Response>

function renderResults(path = '/architectures/job-1/results') {
  vi.stubGlobal('fetch', vi.fn(async () => reply()))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [
      { path: '/architectures/:jobId/results', element: <ResultsPage /> },
      { path: '/architectures/:jobId', element: <p>Job page</p> },
      { path: '/dashboard', element: <p>Dashboard page</p> },
    ],
    { initialEntries: [path] },
  )
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { router, user: userEvent.setup() }
}

const succeeded = (result = makeResult()): JobStatusResponse =>
  makeJob({ status: 'succeeded', attempts: 1, started_at: minutesAgo(9), finished_at: minutesAgo(1), result })

afterEach(() => cleanup())

describe('ResultsPage states', () => {
  it('shows a loading state', () => {
    reply = () => new Promise(() => {})
    renderResults()
    expect(screen.getByText('Loading results')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Architecture Results' })).toBeTruthy()
  })

  it('shows "Job not found" for a 404', async () => {
    reply = () => json(404, { detail: 'Job not found.' })
    renderResults()
    expect(await screen.findByText('Job not found')).toBeTruthy()
  })

  it('offers Try again when loading fails', async () => {
    reply = () => json(503, { detail: 'Job store is unavailable. Please retry later.' })
    const { user } = renderResults()
    expect(await screen.findByText("Couldn't load the results")).toBeTruthy()
    reply = () => json(200, succeeded())
    await user.click(screen.getByRole('button', { name: /Try again/ }))
    expect(await screen.findByRole('tab', { name: 'Overview' })).toBeTruthy()
  })

  it.each([
    ['queued', JOBS.queued, "Results aren't ready yet", 'Track progress'],
    ['running', JOBS.running, "Results aren't ready yet", 'Track progress'],
    ['failed', JOBS.failed, 'No results: the job failed', 'View job'],
  ])('a %s job has no results to show', async (_name, job, title, action) => {
    reply = () => json(200, job)
    renderResults()
    expect(await screen.findByText(title)).toBeTruthy()
    expect(screen.getByRole('link', { name: action }).getAttribute('href')).toBe('/architectures/job-1')
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.queryByRole('button', { name: /Download JSON/ })).toBeNull()
  })

  it('shows the safe error of a failed job', async () => {
    reply = () => json(200, JOBS.failed)
    renderResults()
    expect(await screen.findByText('LLM provider rate limit reached. Please retry later.')).toBeTruthy()
  })
})

describe('ResultsPage with a result', () => {
  it('shows the header badges, actions and summary cards', async () => {
    reply = () => json(200, succeeded())
    renderResults()

    await screen.findByRole('tablist', { name: 'Result sections' })
    expect(screen.getByText('Approved')).toBeTruthy()
    expect(screen.getByText('Version 2')).toBeTruthy()
    expect(screen.queryByText('Revision limit reached')).toBeNull()
    expect(screen.getByRole('link', { name: /Back to job/ }).getAttribute('href')).toBe('/architectures/job-1')
    expect(screen.getByRole('button', { name: /Download JSON/ })).toBeTruthy()

    const cards = Object.fromEntries(
      screen.getAllByRole('term').map((dt) => [dt.textContent, [...dt.parentElement!.querySelectorAll('dd')].map((d) => d.textContent)]),
    )
    expect(cards['Critic score']).toEqual(['82/100', 'Approved by the critic'])
    expect(cards['AWS services']).toEqual(['3', '3 categories'])
    expect(cards['Estimated monthly cost']).toEqual(['$4,120 - $34,800', 'per month · educational estimate'])
    expect(cards['Revision rounds']).toEqual(['1', 'Architecture version 2'])
    expect(screen.queryByText(/did not approve/)).toBeNull()
  })

  it('warns when the design is not approved and links to the Review tab', async () => {
    const result = makeResult({ approved: false, max_revisions_reached: true, revision_count: 2 })
    reply = () => json(200, succeeded(result))
    const { router, user } = renderResults()

    expect(await screen.findByText('Not approved')).toBeTruthy()
    expect(screen.getByText('Revision limit reached')).toBeTruthy()
    expect(screen.getByText(/after 2 revision rounds, the limit\./)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Open the Review tab' }))
    expect(screen.getByRole('tab', { name: 'Review' }).getAttribute('aria-selected')).toBe('true')
    expect(router.state.location.search).toBe('?tab=review')
    expect(screen.getByRole('heading', { name: 'Review summary' })).toBeTruthy() // Stage 4B-4 replaced the placeholder
  })

  it('opens the tab named in ?tab= and falls back to Overview for unknown values', async () => {
    reply = () => json(200, succeeded())
    renderResults('/architectures/job-1/results?tab=cost')
    expect(await screen.findByRole('heading', { name: 'Relative cost breakdown' })).toBeTruthy() // Stage 4B-3 replaced the placeholder
    expect(screen.getByRole('tab', { name: 'Cost' }).getAttribute('aria-selected')).toBe('true')
    cleanup()

    renderResults('/architectures/job-1/results?tab=analyses')
    expect(await screen.findByRole('heading', { name: 'Specialist analyses' })).toBeTruthy() // Stage 4B-5 replaced the placeholder
    expect(screen.getByRole('tab', { name: 'Analyses' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.queryByText(/coming soon/)).toBeNull()
    cleanup()

    renderResults('/architectures/job-1/results?tab=nonsense')
    expect(await screen.findByRole('heading', { name: 'Executive summary' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Overview' }).getAttribute('aria-selected')).toBe('true')
  })

  it('changes tabs with the keyboard and keeps the choice in the URL', async () => {
    reply = () => json(200, succeeded())
    const { router, user } = renderResults()
    const overview = await screen.findByRole('tab', { name: 'Overview' })
    overview.focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Architecture' }).getAttribute('aria-selected')).toBe('true')
    expect(router.state.location.search).toBe('?tab=architecture')
    expect(screen.getByRole('heading', { name: 'Data-flow diagram' })).toBeTruthy() // Stage 4B-2 replaced the placeholder
  })

  it('shows the Overview content', async () => {
    reply = () => json(200, succeeded())
    const { user } = renderResults()

    expect(await screen.findByText('Test executive summary.')).toBeTruthy()
    expect(screen.getByText('A load-balanced, auto-scaling, multi-AZ test architecture.')).toBeTruthy()

    const table = screen.getByRole('table', { name: 'Key requirements' })
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(14)
    expect(rows[0].textContent).toBe('Traffic patternSpiky')
    expect(within(table).getByRole('rowheader', { name: 'Compliance' }).nextElementSibling?.textContent).toBe('PCI-DSS')

    expect(screen.getByText('Support 500,000 concurrent users')).toBeTruthy()
    expect(screen.getByText('Multi-AZ deployment is acceptable')).toBeTruthy()

    const plan = screen.getByText('Architecture plan').closest('details')!
    expect(plan.open).toBe(false)
    await user.click(screen.getByText('Architecture plan'))
    expect(plan.open).toBe(true)
    expect(within(plan).getAllByRole('term').map((t) => t.textContent)).toHaveLength(12)
    expect(within(plan).getByText('Least-privilege IAM.')).toBeTruthy()
  })

  it('downloads the result as JSON built in the browser', async () => {
    const result = makeResult()
    reply = () => json(200, succeeded(result))
    const blobs: Blob[] = []
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: (blob: Blob) => (blobs.push(blob), 'blob:test'), revokeObjectURL: () => {} }))
    const clicked: Array<{ href: string; download: string }> = []
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ href: this.getAttribute('href') ?? '', download: this.download })
    })
    const { user } = renderResults()

    await user.click(await screen.findByRole('button', { name: /Download JSON/ }))

    expect(clicked).toEqual([{ href: 'blob:test', download: 'archonai-result-job-1.json' }])
    // jsdom's Blob has no .text(); FileReader reads it the same way.
    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.readAsText(blobs[0])
    })
    expect(JSON.parse(text)).toEqual(result)
    expect(blobs[0].type).toBe('application/json')
    click.mockRestore()
  })
})
