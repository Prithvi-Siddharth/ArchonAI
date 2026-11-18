/**
 * Architecture History page and the dashboard preview, against a fake GET /jobs.
 * fetch is stubbed in every test: nothing reaches a real backend.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider, useParams } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { useToastStore } from '@/stores/toast.store'
import type { JobHistoryItem, JobHistoryResponse, JobResultSummary } from '@/types/api'

import { ArchitectureHistoryPage } from '../ArchitectureHistoryPage'
import { readHistoryFilters, toApiParams, writeHistoryFilters } from './history-params'

const SUMMARY: JobResultSummary = {
  approved: false,
  critic_score: 68,
  architecture_version: 2,
  aws_service_count: 9,
  estimated_monthly_range: '$4,120 - $34,800 per month (educational estimate)',
  max_revisions_reached: true,
}

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()

function item(n: number, overrides: Partial<JobHistoryItem> = {}): JobHistoryItem {
  const status = overrides.status ?? 'succeeded'
  return {
    job_id: `${String(n).padStart(8, '0')}-aaaa-bbbb-cccc-dddddddddddd`,
    user_request: `Design system number ${n} for 10,000 users`,
    status,
    attempts: status === 'queued' ? 0 : 1,
    created_at: minutesAgo(n * 10),
    started_at: status === 'queued' ? null : minutesAgo(n * 10 - 1),
    finished_at: status === 'succeeded' || status === 'failed' ? minutesAgo(n * 10 - 6) : null,
    updated_at: minutesAgo(n * 10 - 6),
    error: null,
    summary: status === 'succeeded' ? SUMMARY : null,
    ...overrides,
  }
}

/** A fake GET /jobs over `jobs` (already newest first), with the backend's filter rules. */
function fakeHistory(jobs: JobHistoryItem[], { fail = false } = {}) {
  const requests: URLSearchParams[] = []
  const state = { fail }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input, 'http://localhost')
      if (url.pathname !== '/api/v1/architectures/jobs') throw new Error(`unexpected request ${input}`)
      requests.push(url.searchParams)
      if (state.fail) return new Response(JSON.stringify({ detail: 'Job store is unavailable. Please retry later.' }), { status: 503 })
      const q = (url.searchParams.get('q') ?? '').toLowerCase()
      const status = url.searchParams.get('status')
      const limit = Number(url.searchParams.get('limit'))
      const offset = Number(url.searchParams.get('offset'))
      const searched = jobs.filter((j) => !q || j.user_request.toLowerCase().includes(q) || j.job_id.startsWith(q))
      const counts = { queued: 0, running: 0, succeeded: 0, failed: 0 }
      for (const j of searched) counts[j.status] += 1
      const filtered = searched.filter((j) => !status || j.status === status)
      const body: JobHistoryResponse = { items: filtered.slice(offset, offset + limit), total: filtered.length, limit, offset, counts }
      return new Response(JSON.stringify(body), { status: 200 })
    }),
  )
  return { requests, state, last: () => requests.at(-1) as URLSearchParams }
}

function Stub({ label }: { label: string }) {
  const { jobId } = useParams()
  return <p>{`${label} ${jobId ?? ''}`.trim()}</p>
}

function renderPage(path = '/architectures/history') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [
      { path: '/architectures/history', element: <ArchitectureHistoryPage /> },
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/architectures/new', element: <Stub label="New page" /> },
      { path: '/architectures/:jobId', element: <Stub label="Job page" /> },
      { path: '/architectures/:jobId/results', element: <Stub label="Results page" /> },
    ],
    { initialEntries: [path] },
  )
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { router, client, user: userEvent.setup() }
}

const rows = () => within(screen.getByRole('list', { name: 'Architecture jobs' })).getAllByRole('listitem').filter((li) => li.dataset.jobId)
const toggleOf = (li: HTMLElement) => within(li).getAllByRole('button')[0]
const search = (router: ReturnType<typeof createMemoryRouter>) => router.state.location.search

afterEach(() => {
  cleanup()
  useToastStore.setState({ toasts: [] })
})

describe('history URL filters', () => {
  it('reads valid values and falls back for anything else', () => {
    expect(readHistoryFilters(new URLSearchParams('page=3&status=failed&q=%20video%20'))).toEqual({ page: 3, status: 'failed', q: 'video' })
    expect(readHistoryFilters(new URLSearchParams('page=0&status=done'))).toEqual({ page: 1, status: null, q: '' })
    expect(readHistoryFilters(new URLSearchParams('page=2.5'))).toEqual({ page: 1, status: null, q: '' })
    expect(readHistoryFilters(new URLSearchParams(`q=${'x'.repeat(300)}`)).q).toHaveLength(200)
  })

  it('writes only non-default values, and maps pages to offsets', () => {
    expect(writeHistoryFilters({ page: 1, status: null, q: '' }).toString()).toBe('')
    expect(writeHistoryFilters({ page: 2, status: 'running', q: 'blog' }).toString()).toBe('q=blog&status=running&page=2')
    expect(toApiParams({ page: 3, status: 'failed', q: 'blog' })).toEqual({ limit: 10, offset: 20, status: 'failed', q: 'blog' })
    expect(toApiParams({ page: 1, status: null, q: '' })).toEqual({ limit: 10, offset: 0 })
  })
})

describe('Architecture History page', () => {
  it('loads the newest jobs first with status, short ID, attempts, version and the total', async () => {
    const jobs = [item(1, { status: 'running' }), item(2), item(3, { status: 'failed', error: { status_code: 429, message: 'LLM provider rate limit reached. Please retry later.' } })]
    fakeHistory(jobs)
    renderPage()
    expect(screen.getAllByRole('listitem', { hidden: true }).length).toBeGreaterThan(0) // skeleton while loading
    await screen.findByRole('list', { name: 'Architecture jobs' })
    expect(rows().map((li) => [li.dataset.jobId, li.dataset.status])).toEqual(jobs.map((j) => [j.job_id, j.status]))
    const second = rows()[1]
    expect(within(second).getByText('Design system number 2 for 10,000 users')).toBeTruthy()
    expect(within(second).getByText('00000002')).toBeTruthy()
    expect(within(second).getByText('Succeeded')).toBeTruthy()
    expect(within(second).getByText('1 attempt')).toBeTruthy()
    expect(within(second).getByText('Version 2')).toBeTruthy()
    expect(within(rows()[0]).getByText('Running')).toBeTruthy()
    expect(within(rows()[2]).getByText('Failed')).toBeTruthy()
    expect(screen.getByText('3 jobs')).toBeTruthy()
  })

  it('expands and collapses an entry, showing everything known about a succeeded job', async () => {
    const job = item(1, { user_request: 'Design a video platform.\n\nIt must stream 4K.' })
    fakeHistory([job])
    const { user } = renderPage()
    const row = (await screen.findAllByRole('listitem')).find((li) => li.dataset.jobId) as HTMLElement
    const toggle = toggleOf(row)
    expect(toggle.getAttribute('aria-expanded')).toBe('false')

    await user.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    const details = screen.getByRole('region', { name: 'Details of job 00000001' })
    expect(toggle.getAttribute('aria-controls')).toBe(details.id)
    const facts = Object.fromEntries(within(details).getAllByRole('term').map((dt) => [dt.textContent, dt.nextElementSibling?.textContent]))
    expect(facts).toMatchObject({
      Request: 'Design a video platform.\n\nIt must stream 4K.',
      Status: 'Succeeded',
      Attempts: '1',
      'Critic decision': 'Not approved',
      'Critic score': '68/100',
      'AWS services': '9',
      'Architecture version': '2',
      'Estimated monthly cost': SUMMARY.estimated_monthly_range,
    })
    expect(within(details).getByText(job.job_id)).toBeTruthy()
    expect(facts.Submitted).toBeTruthy()
    expect(facts.Completed).toBeTruthy()

    await user.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('region', { name: 'Details of job 00000001' })).toBeNull()
  })

  it('succeeded jobs offer View Job and View Results; both navigate', async () => {
    fakeHistory([item(1)])
    const { user, router } = renderPage()
    await user.click(toggleOf((await screen.findAllByRole('listitem')).find((li) => li.dataset.jobId) as HTMLElement))
    const jobId = item(1).job_id
    expect(screen.getByRole('link', { name: 'View Job' }).getAttribute('href')).toBe(`/architectures/${jobId}`)
    await user.click(screen.getByRole('link', { name: 'View Results' }))
    expect(await screen.findByText(`Results page ${jobId}`)).toBeTruthy()
    expect(router.state.location.pathname).toBe(`/architectures/${jobId}/results`)
  })

  it('View Job opens the tracking page', async () => {
    fakeHistory([item(1, { status: 'queued' })])
    const { user } = renderPage()
    await user.click(toggleOf((await screen.findAllByRole('listitem')).find((li) => li.dataset.jobId) as HTMLElement))
    expect(screen.queryByRole('link', { name: 'View Results' })).toBeNull()
    await user.click(screen.getByRole('link', { name: 'View Job' }))
    expect(await screen.findByText(`Job page ${item(1).job_id}`)).toBeTruthy()
  })

  it('failed jobs show a readable failure message and no View Results', async () => {
    fakeHistory([item(1, { status: 'failed', attempts: 2, error: { status_code: 502, message: 'The LLM provider returned an invalid response.' } })])
    const { user } = renderPage()
    await user.click(toggleOf((await screen.findAllByRole('listitem')).find((li) => li.dataset.jobId) as HTMLElement))
    const note = screen.getByRole('note')
    expect(note.textContent).toBe('This job failed: The LLM provider returned an invalid response. (HTTP 502)')
    expect(screen.getByRole('link', { name: 'View Job' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'View Results' })).toBeNull()
    expect(screen.queryByText('Critic score')).toBeNull()
  })

  it('a queued job waiting for a retry explains why', async () => {
    fakeHistory([item(1, { status: 'queued', attempts: 1, error: { status_code: 429, message: 'LLM provider rate limit reached. Please retry later.' } })])
    const { user } = renderPage()
    await user.click(toggleOf((await screen.findAllByRole('listitem')).find((li) => li.dataset.jobId) as HTMLElement))
    expect(screen.getByRole('note').textContent).toMatch(/^Will retry after an error: LLM provider rate limit reached/)
  })

  it('missing metadata is shown as missing, never invented', async () => {
    const empty: JobResultSummary = { approved: null, critic_score: null, architecture_version: null, aws_service_count: null, estimated_monthly_range: null, max_revisions_reached: null }
    fakeHistory([item(1, { user_request: '   ', summary: empty })])
    const { user } = renderPage()
    const row = (await screen.findAllByRole('listitem')).find((li) => li.dataset.jobId) as HTMLElement
    expect(within(row).getByText('No request text')).toBeTruthy()
    expect(within(row).queryByText(/^Version/)).toBeNull()
    await user.click(toggleOf(row))
    expect(screen.getByText('No request text was stored.')).toBeTruthy()
    expect(screen.getAllByText('Not available')).toHaveLength(5)
  })

  it('filters by status through the API and keeps it in the URL', async () => {
    const api = fakeHistory([item(1, { status: 'running' }), item(2), item(3, { status: 'failed' }), item(4)])
    const { user, router } = renderPage()
    await screen.findByRole('list', { name: 'Architecture jobs' })
    const group = screen.getByRole('group', { name: 'Filter by status' })
    expect(within(group).getAllByRole('button').map((b) => b.textContent)).toEqual(['All4', 'Queued0', 'Running1', 'Succeeded2', 'Failed1'])

    await user.click(within(group).getByRole('button', { name: /Succeeded/ }))
    await waitFor(() => expect(rows().map((li) => li.dataset.status)).toEqual(['succeeded', 'succeeded']))
    expect(api.last().get('status')).toBe('succeeded')
    expect(search(router)).toBe('?status=succeeded')
    expect(within(group).getByRole('button', { name: /Succeeded/ }).getAttribute('aria-pressed')).toBe('true')
  })

  it('searches request text after a short pause, then clears filters', async () => {
    const api = fakeHistory([item(1, { user_request: 'Design a VIDEO streaming platform' }), item(2), item(3)])
    const { user, router } = renderPage()
    await screen.findByRole('list', { name: 'Architecture jobs' })
    await user.type(screen.getByRole('searchbox', { name: 'Search history' }), 'video')
    await waitFor(() => expect(rows()).toHaveLength(1))
    expect(api.last().get('q')).toBe('video')
    expect(search(router)).toBe('?q=video')
    expect(api.requests.filter((r) => r.get('q')).length).toBeLessThanOrEqual(2) // debounced, not one request per key

    await user.click(screen.getAllByRole('button', { name: 'Clear filters' })[0])
    await waitFor(() => expect(rows()).toHaveLength(3))
    expect(search(router)).toBe('')
    expect((screen.getByRole('searchbox', { name: 'Search history' }) as HTMLInputElement).value).toBe('')
  })

  it('pages through the history with boundaries', async () => {
    const api = fakeHistory(Array.from({ length: 23 }, (_, n) => item(n + 1)))
    const { user, router } = renderPage()
    await screen.findByText('Showing 1–10 of 23 jobs')
    const previous = () => screen.getByRole('button', { name: 'Previous page' })
    const next = () => screen.getByRole('button', { name: 'Next page' })
    expect(screen.getByText('Page 1 of 3')).toBeTruthy()
    expect(previous()).toHaveProperty('disabled', true)

    await user.click(next())
    await screen.findByText('Showing 11–20 of 23 jobs')
    expect(api.last().get('offset')).toBe('10')
    expect(search(router)).toBe('?page=2')

    await user.click(next())
    await screen.findByText('Showing 21–23 of 23 jobs')
    expect(screen.getByText('Page 3 of 3')).toBeTruthy()
    expect(next()).toHaveProperty('disabled', true)
    expect(rows()).toHaveLength(3)

    await user.click(previous())
    await screen.findByText('Showing 11–20 of 23 jobs')
  })

  it('a page past the end offers the last page', async () => {
    fakeHistory(Array.from({ length: 23 }, (_, n) => item(n + 1)))
    const { user, router } = renderPage('/architectures/history?page=9')
    expect(await screen.findByText('This page is empty')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Go to page 3' }))
    await screen.findByText('Showing 21–23 of 23 jobs')
    expect(search(router)).toBe('?page=3')
  })

  it('empty states: no jobs yet, no search results, no jobs in a status', async () => {
    fakeHistory([])
    renderPage()
    expect(await screen.findByText('No architectures yet')).toBeTruthy()
    // One in the page header, one offered by the empty state itself.
    expect(screen.getAllByRole('link', { name: 'New Architecture' }).map((a) => a.getAttribute('href'))).toEqual(['/architectures/new', '/architectures/new'])
    cleanup()

    fakeHistory([item(1)])
    renderPage('/architectures/history?q=zzz')
    expect(await screen.findByText('No jobs match “zzz”')).toBeTruthy()
    cleanup()

    fakeHistory([item(1)])
    renderPage('/architectures/history?status=running')
    expect(await screen.findByText('No running jobs')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: 'Clear filters' }).length).toBeGreaterThan(0)
  })

  it('API unavailable: an error with a retry that recovers', async () => {
    const api = fakeHistory([item(1)], { fail: true })
    const { user } = renderPage()
    expect(await screen.findByText("Couldn't load your history")).toBeTruthy()
    expect(screen.getByText('Job store is unavailable. Please retry later.')).toBeTruthy()
    api.state.fail = false
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('list', { name: 'Architecture jobs' })).toBeTruthy()
  })

  it('Refresh re-reads the history', async () => {
    const api = fakeHistory([item(1)])
    const { user } = renderPage()
    await screen.findByRole('list', { name: 'Architecture jobs' })
    const before = api.requests.length
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(api.requests.length).toBe(before + 1))
  })

  it('copies a job ID from the list', async () => {
    fakeHistory([item(1)])
    const { user } = renderPage()
    // user-event installs its own clipboard; watch that one.
    const writeText = vi.spyOn(navigator.clipboard, 'writeText')
    await user.click(await screen.findByRole('button', { name: 'Copy job ID 00000001' }))
    expect(writeText).toHaveBeenCalledWith(item(1).job_id)
    expect(useToastStore.getState().toasts.map((t) => t.title)).toEqual(['Job ID copied'])
  })

  it('ignores invalid URL parameters', async () => {
    const api = fakeHistory([item(1)])
    renderPage('/architectures/history?page=abc&status=bogus')
    await screen.findByRole('list', { name: 'Architecture jobs' })
    expect([api.last().get('offset'), api.last().get('status')]).toEqual(['0', null])
  })
})

describe('dashboard preview of the history', () => {
  it('shows the newest jobs and account-wide counts from the history API', async () => {
    const api = fakeHistory([item(1, { status: 'running' }), item(2), item(3, { status: 'failed' }), ...Array.from({ length: 7 }, (_, n) => item(n + 4))])
    renderPage('/dashboard')
    await screen.findByText('Design system number 1 for 10,000 users')
    const table = screen.getByRole('table', { name: 'Your most recent architecture jobs' })
    expect(within(table).getAllByRole('row').slice(1)).toHaveLength(6)
    expect(api.last().get('limit')).toBe('6')
    const stats = Object.fromEntries(
      ['Total generations', 'Successful jobs', 'Failed jobs'].map((label) => [label, screen.getByText(label).parentElement?.parentElement?.textContent]),
    )
    expect(stats['Total generations']).toMatch(/10/)
    expect(stats['Successful jobs']).toMatch(/8.*80% of your jobs/)
    expect(stats['Failed jobs']).toMatch(/1.*10% of your jobs/)
    expect(screen.getByRole('link', { name: /View all/ }).getAttribute('href')).toBe('/architectures/history')
    expect(screen.queryByText(/this browser/i)).toBeNull()
  })

  it('shows an error when the history cannot be loaded', async () => {
    fakeHistory([], { fail: true })
    renderPage('/dashboard')
    expect(await screen.findByText("Couldn't load your jobs")).toBeTruthy()
  })
})
