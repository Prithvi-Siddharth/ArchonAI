/**
 * The Monitoring page, against a fake API. fetch is stubbed in every test: nothing reaches a real
 * backend, and the test also checks that the page only ever sends GET requests (it is read-only).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { findPageMeta, NAV_SECTIONS } from '@/components/layout/navigation'
import type { JobHistoryItem, JobHistoryResponse, JobMonitoring, MonitoringState } from '@/types/api'

import { MonitoringPage } from './MonitoringPage'

const JOB_A = 'aaaaaaaa-1111-2222-3333-444444444444'
const JOB_B = 'bbbbbbbb-1111-2222-3333-444444444444'

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()

function historyItem(job_id: string, request: string, minutes: number): JobHistoryItem {
  return {
    job_id,
    user_request: request,
    status: 'succeeded',
    attempts: 1,
    created_at: minutesAgo(minutes),
    started_at: minutesAgo(minutes - 1),
    finished_at: minutesAgo(minutes - 6),
    updated_at: minutesAgo(minutes - 6),
    error: null,
    summary: null,
  }
}
const HISTORY = [historyItem(JOB_A, 'Design a video streaming platform for 2 million users', 10), historyItem(JOB_B, 'Design a blog', 90)]

const OK: JobMonitoring = {
  job_id: JOB_A,
  job_status: 'succeeded',
  attempts: 1,
  created_at: minutesAgo(10),
  finished_at: minutesAgo(4),
  state: 'ok',
  message: null,
  may_still_arrive: false,
  summary: {
    attempts: 1,
    job_duration_ms: 372_000,
    workflow_duration_ms: 370_000,
    revisions: 1,
    approved: true,
    llm_calls: 3,
    llm_failures: 1,
    input_tokens: 1200,
    output_tokens: 400,
    reasoning_tokens: 20,
    retries: 4,
    rate_limited_responses: 1,
  },
  agents: [
    { node: 'compute_agent', label: 'Compute Agent', runs: 1, total_ms: 6000, failures: 0, last_outcome: 'success', share: 0.6 },
    { node: 'architecture_critic', label: 'Architecture Critic', runs: 2, total_ms: 4000, failures: 1, last_outcome: 'failure', share: 0.4 },
  ],
  llm_calls: [
    { time: '2026-11-19T10:00:05Z', node: 'compute_agent', label: 'Compute Agent', call_type: 'structured', provider: 'groq', model: 'qwen/qwen3.8-27b', outcome: 'success', total_ms: 5900, input_tokens: 700, output_tokens: 300, reasoning_tokens: null, retries: 4, rate_limited_responses: 1, finish_reason: 'stop', provider_status: null, error_type: null },
    { time: '2026-11-19T10:00:13Z', node: 'database_agent', label: 'Database Agent', call_type: 'structured', provider: 'groq', model: 'qwen/qwen3.8-27b', outcome: 'failure', total_ms: 850, input_tokens: null, output_tokens: null, reasoning_tokens: null, retries: 0, rate_limited_responses: 0, finish_reason: null, provider_status: 429, error_type: 'RateLimitError' },
  ],
  timeline: [
    { time: '2026-11-19T10:00:00Z', service: 'worker', level: 'INFO', event: 'job_started', fields: { attempt: 1, redelivered: false } },
    { time: '2026-11-19T10:00:13Z', service: 'worker', level: 'WARNING', event: 'llm_call_summary', fields: { node: 'database_agent', outcome: 'failure', provider_status: 429 } },
    { time: '2026-11-19T10:06:12Z', service: 'worker', level: 'INFO', event: 'job_succeeded', fields: { attempt: 1, duration_ms: 372000 } },
  ],
  truncated: false,
  fetched_at: new Date().toISOString(),
}

const NOT_OK = (state: MonitoringState, message: string, extra: Partial<JobMonitoring> = {}): JobMonitoring => ({
  ...OK,
  state,
  message,
  summary: null,
  agents: [],
  llm_calls: [],
  timeline: [],
  ...extra,
})

type Reply = { status: number; body?: unknown }
interface Fake {
  methods: string[]
  monitoring: Map<string, Reply[]>
  paths: string[]
}

/** Monitoring replies are taken in order per job; the last one repeats. */
function fakeApi({ history = { status: 200, body: toHistory(HISTORY) } as Reply, monitoring = {} as Record<string, Reply[]> } = {}): Fake {
  const state: Fake = { methods: [], monitoring: new Map(Object.entries(monitoring)), paths: [] }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      state.methods.push(init?.method ?? 'GET')
      state.paths.push(path)
      const url = new URL(path, 'http://localhost')
      let reply: Reply
      const match = /^\/api\/v1\/architectures\/jobs\/([^/]+)\/monitoring$/.exec(url.pathname)
      if (url.pathname === '/api/v1/architectures/jobs') reply = history
      else if (match) {
        const queue = state.monitoring.get(match[1]) ?? [{ status: 404, body: { detail: 'Job not found.' } }]
        reply = queue.length > 1 ? queue.shift()! : queue[0]
      } else throw new Error(`unexpected request ${path}`)
      return new Response(JSON.stringify(reply.body), { status: reply.status })
    }),
  )
  return state
}

function toHistory(items: JobHistoryItem[]): JobHistoryResponse {
  const counts = { queued: 0, running: 0, succeeded: items.length, failed: 0 }
  return { items, total: items.length, limit: 20, offset: 0, counts }
}

function Where() {
  const location = useLocation()
  return <p data-testid="where">{location.pathname}</p>
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [
      {
        path: '/monitoring',
        element: (
          <>
            <MonitoringPage />
            <Where />
          </>
        ),
      },
      {
        path: '/monitoring/:jobId',
        element: (
          <>
            <MonitoringPage />
            <Where />
          </>
        ),
      },
      { path: '/architectures/new', element: <p>New page</p> },
      { path: '/architectures/:jobId', element: <p>Job page</p> },
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

const ok = (job = OK, status = 200): Reply => ({ status, body: job })

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('Monitoring page', () => {
  it('opens your newest job when none is named', async () => {
    fakeApi({ monitoring: { [JOB_A]: [ok()] } })
    renderAt('/monitoring')
    await screen.findByText('Total time')
    expect(screen.getByTestId('where').textContent).toBe(`/monitoring/${JOB_A}`)
  })

  it('says so when there is nothing to monitor yet', async () => {
    fakeApi({ history: { status: 200, body: toHistory([]) } })
    renderAt('/monitoring')
    expect(await screen.findByText('No jobs to monitor yet')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'New Architecture' }).getAttribute('href')).toBe('/architectures/new')
  })

  it('shows the headline numbers, marked read-only', async () => {
    fakeApi({ monitoring: { [JOB_A]: [ok()] } })
    renderAt(`/monitoring/${JOB_A}`)
    await screen.findByText('Total time')
    const value = (label: string) => screen.getByText(label, { selector: 'dt' }).closest('dl')?.textContent ?? ''
    expect(value('Total time')).toContain('6m 12s')
    expect(value('Total time')).toContain('1 attempt')
    expect(value('LLM calls')).toContain('3')
    expect(value('LLM calls')).toContain('1 failed')
    expect(value('Tokens')).toContain('1,600')
    expect(value('Tokens')).toContain('1,200 in · 400 out · 20 reasoning')
    expect(value('Retries')).toContain('4')
    expect(value('Retries')).toContain('1 rate-limited responses')
    expect(value('Revision rounds')).toContain('1')
    expect(value('Revision rounds')).toContain('Approved by the critic')
    expect(screen.getByText('Read-only')).toBeTruthy()
    expect(screen.getByText(/only reads this job’s logs from AWS CloudWatch\. It can’t change anything/)).toBeTruthy()
  })

  it('lists each agent with its runs, time and share', async () => {
    fakeApi({ monitoring: { [JOB_A]: [ok()] } })
    renderAt(`/monitoring/${JOB_A}`)
    const table = await screen.findByRole('table', { name: 'Agent timings for this job' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(rows[0].textContent).toContain('Compute Agent')
    expect(rows[0].textContent).toContain('6s')
    expect(rows[0].textContent).toContain('60%')
    expect(rows[1].textContent).toContain('Architecture Critic')
    expect(rows[1].textContent).toContain('2')
    expect(rows[1].textContent).toContain('1 failed')
  })

  it('lists each LLM call with its model, time, tokens and retries', async () => {
    fakeApi({ monitoring: { [JOB_A]: [ok()] } })
    renderAt(`/monitoring/${JOB_A}`)
    const table = await screen.findByRole('table', { name: 'LLM calls for this job' })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows[0].textContent).toContain('Compute Agent')
    expect(rows[0].textContent).toContain('groq/qwen/qwen3.8-27b')
    expect(rows[0].textContent).toContain('700 / 300')
    expect(rows[0].textContent).toContain('4 (rate limited 1)')
    expect(rows[0].textContent).toContain('Succeeded')
    expect(rows[1].textContent).toContain('850 ms')
    expect(rows[1].textContent).toContain('Failed 429')
    expect(rows[1].textContent).toContain('—') // no tokens for a failed call
  })

  it('shows the timeline with the logged fields, and can show only warnings and errors', async () => {
    const { user } = (fakeApi({ monitoring: { [JOB_A]: [ok()] } }), renderAt(`/monitoring/${JOB_A}`))
    const list = await screen.findByRole('list', { name: 'Log events' })
    const items = within(list).getAllByRole('listitem')
    expect(items.map((li) => li.querySelector('span.font-medium')?.textContent)).toEqual(['job_started', 'llm_call_summary', 'job_succeeded'])
    expect(items[0].textContent).toContain('attempt=1')
    expect(items[1].textContent).toContain('provider_status=429')
    expect(items[1].getAttribute('data-level')).toBe('WARNING')

    await user.click(screen.getByRole('button', { name: 'Warnings and errors' }))
    expect(within(screen.getByRole('list', { name: 'Log events' })).getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Warnings and errors' }).getAttribute('aria-pressed')).toBe('true')
  })

  it('says when the tables were cut short', async () => {
    fakeApi({ monitoring: { [JOB_A]: [ok({ ...OK, truncated: true })] } })
    renderAt(`/monitoring/${JOB_A}`)
    expect(await screen.findByText(/Only the first 500 events are listed/)).toBeTruthy()
  })

  it('only ever sends GET requests: it is read-only', async () => {
    const api = fakeApi({ monitoring: { [JOB_A]: [ok()] } })
    const { user } = renderAt(`/monitoring/${JOB_A}`)
    await screen.findByText('Total time')
    await user.click(screen.getByRole('button', { name: /Refresh/ }))
    await user.click(screen.getByRole('button', { name: 'Warnings and errors' }))
    expect(new Set(api.methods)).toEqual(new Set(['GET']))
    expect(screen.queryByRole('button', { name: /delete|retry job|re-run|cancel|save/i })).toBeNull()
  })

  it('switches to another job from the picker', async () => {
    const api = fakeApi({ monitoring: { [JOB_A]: [ok()], [JOB_B]: [ok({ ...OK, job_id: JOB_B, summary: { ...OK.summary!, llm_calls: 9 } })] } })
    const { user } = renderAt(`/monitoring/${JOB_A}`)
    await screen.findByText('Total time')
    const picker = screen.getByLabelText('Job') as HTMLSelectElement
    expect(within(picker).getAllByRole('option').map((o) => o.textContent)).toEqual([
      expect.stringContaining('aaaaaaaa · Design a video streaming platform'),
      expect.stringContaining('bbbbbbbb · Design a blog'),
    ])
    await user.selectOptions(picker, JOB_B)
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe(`/monitoring/${JOB_B}`))
    await waitFor(() => expect(screen.getByText('LLM calls', { selector: 'dt' }).closest('dl')?.textContent).toContain('9'))
    expect(api.paths).toContain(`/api/v1/architectures/jobs/${JOB_B}/monitoring`)
  })

  it('offers a job that is not among the newest 20 as "this job"', async () => {
    fakeApi({ monitoring: { 'cccccccc-1111-2222-3333-444444444444': [ok({ ...OK, job_id: 'cccccccc-1111-2222-3333-444444444444' })] } })
    renderAt('/monitoring/cccccccc-1111-2222-3333-444444444444')
    await screen.findByText('Total time')
    const options = within(screen.getByLabelText('Job') as HTMLSelectElement).getAllByRole('option')
    expect(options[0].textContent).toBe('cccccccc · this job')
    expect(options).toHaveLength(3)
  })

  it('links to the job itself', async () => {
    fakeApi({ monitoring: { [JOB_A]: [ok()] } })
    renderAt(`/monitoring/${JOB_A}`)
    await screen.findByText('Total time')
    expect(screen.getByRole('link', { name: 'Open job' }).getAttribute('href')).toBe(`/architectures/${JOB_A}`)
  })
})

describe('Monitoring page: when there is nothing to show', () => {
  it.each([
    ['disabled', 'CloudWatch logging is switched off', 'CloudWatch logging is switched off on this server, so there is nothing to show.', false],
    ['forbidden', 'The server can’t read CloudWatch Logs', 'This server isn’t allowed to read CloudWatch Logs. Attach the logs-read policy in monitoring/iam/ to its AWS identity.', false],
    ['no_credentials', 'No AWS credentials on the server', 'This server has no AWS credentials, so it can’t read CloudWatch.', false],
    ['throttled', 'CloudWatch is busy', 'CloudWatch is busy right now. Please try again in a moment.', true],
    ['unreachable', 'CloudWatch couldn’t be reached', 'CloudWatch couldn’t be reached. Please try again later.', true],
    ['empty', 'No log lines found for this job', 'No log lines were found for this job. Logs arrive a few seconds late.', true],
  ] as const)('%s: a clear reason, and a retry only where it could help', async (state, title, message, retry) => {
    fakeApi({ monitoring: { [JOB_A]: [ok(NOT_OK(state, message))] } })
    renderAt(`/monitoring/${JOB_A}`)
    expect(await screen.findByText(title)).toBeTruthy()
    expect(screen.getByText(message)).toBeTruthy()
    expect(Boolean(screen.queryByRole('button', { name: 'Check again' }))).toBe(retry)
    expect(screen.queryByText('Total time')).toBeNull()
  })

  it('Check again asks the backend again', async () => {
    const api = fakeApi({ monitoring: { [JOB_A]: [ok(NOT_OK('throttled', 'CloudWatch is busy right now.')), ok()] } })
    const { user } = renderAt(`/monitoring/${JOB_A}`)
    await user.click(await screen.findByRole('button', { name: 'Check again' }))
    expect(await screen.findByText('Total time')).toBeTruthy()
    expect(api.paths.filter((p) => p.endsWith('/monitoring'))).toHaveLength(2)
  })

  it('a running job with no lines yet says more may arrive, and shows its status', async () => {
    fakeApi({ monitoring: { [JOB_A]: [ok(NOT_OK('empty', 'No log lines were found for this job.', { job_status: 'running', may_still_arrive: true, finished_at: null }))] } })
    renderAt(`/monitoring/${JOB_A}`)
    expect(await screen.findByText(/lines may still arrive\. This page checks again every 10 seconds/)).toBeTruthy()
    expect(screen.getByText('Updates automatically every 10 seconds')).toBeTruthy()
  })

  it('a job that is not yours is "Job not found"', async () => {
    fakeApi()
    renderAt(`/monitoring/${JOB_A}`)
    expect(await screen.findByText('Job not found')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Choose another job' }).getAttribute('href')).toBe('/monitoring')
  })

  it('an outage shows an error with retry', async () => {
    const api = fakeApi({ monitoring: { [JOB_A]: [{ status: 503, body: { detail: 'Job store is unavailable. Please retry later.' } }] } })
    const { user } = renderAt(`/monitoring/${JOB_A}`)
    expect(await screen.findByText("Couldn't load monitoring data", {}, { timeout: 4000 })).toBeTruthy()
    expect(screen.getByText('Job store is unavailable. Please retry later.')).toBeTruthy()
    const before = api.paths.length
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(api.paths.length).toBeGreaterThan(before))
  })
})

describe('Monitoring page: live jobs', () => {
  it('reads again every 10 seconds while more lines may arrive, and stops when the job is over', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const live = ok({ ...OK, job_status: 'running', may_still_arrive: true, finished_at: null })
    const api = fakeApi({ monitoring: { [JOB_A]: [live, live, ok()] } })
    renderAt(`/monitoring/${JOB_A}`)
    await screen.findByText('Total time')
    const asks = () => api.paths.filter((p) => p.endsWith('/monitoring')).length
    expect(asks()).toBe(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_500)
    })
    expect(asks()).toBe(2)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_500)
    })
    expect(asks()).toBe(3) // this answer says the job is over...
    await act(async () => {
      await vi.advanceTimersByTimeAsync(35_000)
    })
    expect(asks()).toBe(3) // ...so it stopped asking
  })
})

describe('Monitoring in the sidebar', () => {
  it('is in Workspace after Activity, with its own breadcrumb', () => {
    const workspace = NAV_SECTIONS.find((section) => section.title === 'Workspace')
    expect(workspace?.items.map((i) => i.label)).toEqual(['Dashboard', 'New Architecture', 'Architecture History', 'Activity', 'Monitoring'])
    expect(findPageMeta('/monitoring')).toEqual({ section: 'Workspace', label: 'Monitoring' })
    expect(findPageMeta(`/monitoring/${JOB_A}`)).toEqual({ section: 'Workspace', label: 'Monitoring' })
  })
})
