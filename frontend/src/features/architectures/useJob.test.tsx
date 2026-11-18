import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { JOBS, json } from '@/test/job-fixtures'

import { jobQueryKey, jobRefetchInterval, POLL_INTERVAL_MS, useJob } from './useJob'

/** fetch answers with the replies in order, then keeps repeating the last one. */
function stubReplies(...replies: Array<() => Response>) {
  let call = 0
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => replies[Math.min(call++, replies.length - 1)]())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/**
 * Mount useJob and return the state of the query observer it creates. Assertions
 * read the observer (the source the page renders from) rather than the hook's
 * return value: under fake timers in jsdom, React doesn't re-render the test hook
 * after a poll even though the observer has the new data. Re-rendering on each
 * poll is checked in a real browser instead.
 */
function renderUseJob() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  renderHook(() => useJob('job-1'), { wrapper })
  const observer = () => client.getQueryCache().find({ queryKey: jobQueryKey('job-1') })!.observers[0]
  return { result: { get current() { return observer().getCurrentResult() } } }
}

/**
 * Move the fake clock forward, then let any request it started finish (reading
 * the reply and updating the hook) without moving the clock any further.
 */
async function advance(ms: number) {
  await act(() => vi.advanceTimersByTimeAsync(ms))
  for (let i = 0; i < 10; i++) await act(() => vi.advanceTimersByTimeAsync(0))
}
const ok = (job: object) => () => json(200, job)

beforeEach(() => {
  vi.useFakeTimers()
  focusManager.setFocused(true)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  focusManager.setFocused(undefined)
})

describe('jobRefetchInterval', () => {
  const state = (data?: object, error: unknown = null) => ({ state: { data, error } }) as Parameters<typeof jobRefetchInterval>[0]

  it('polls every 5 seconds while queued or running (including retries)', () => {
    for (const job of [JOBS.queued, JOBS.running, JOBS.retryWaiting, JOBS.retryRunning]) {
      expect(jobRefetchInterval(state(job))).toBe(POLL_INTERVAL_MS)
    }
    expect(POLL_INTERVAL_MS).toBe(5000)
  })

  it('stops for finished jobs, a 404, or a failed first load', () => {
    expect(jobRefetchInterval(state(JOBS.succeeded))).toBe(false)
    expect(jobRefetchInterval(state(JOBS.failed))).toBe(false)
    expect(jobRefetchInterval(state(undefined, new ApiError('http', 'Job not found.', { status: 404 })))).toBe(false)
    expect(jobRefetchInterval(state(undefined, new ApiError('unreachable', 'down')))).toBe(false)
  })

  it('keeps polling after a temporary failure once a status is known', () => {
    expect(jobRefetchInterval(state(JOBS.running, new ApiError('http', 'busy', { status: 503 })))).toBe(POLL_INTERVAL_MS)
  })

  it('uses the shared cache key', () => {
    expect(jobQueryKey('abc')).toEqual(['architectures', 'job', 'abc'])
  })
})

describe('useJob polling', () => {
  it('reads the job every 5 seconds while it is queued or running', async () => {
    const fetchMock = stubReplies(ok(JOBS.queued), ok(JOBS.running), ok(JOBS.running))
    const { result } = renderUseJob()

    await advance(0)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result.current.data?.status).toBe('queued')
    await advance(POLL_INTERVAL_MS)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.current.data?.status).toBe('running')
    await advance(POLL_INTERVAL_MS)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/v1/architectures/jobs/job-1')
  })

  it.each([
    ['succeeds', JOBS.succeeded],
    ['fails', JOBS.failed],
  ])('stops polling once the job %s', async (_name, finalJob) => {
    const fetchMock = stubReplies(ok(JOBS.running), ok(finalJob))
    const { result } = renderUseJob()

    await advance(0)
    await advance(POLL_INTERVAL_MS)
    expect(result.current.data?.status).toBe(finalJob.status)
    const calls = fetchMock.mock.calls.length
    await advance(POLL_INTERVAL_MS * 4)
    expect(fetchMock).toHaveBeenCalledTimes(calls)
  })

  it('does not poll a job that does not exist (404)', async () => {
    const fetchMock = stubReplies(() => json(404, { detail: 'Job not found.' }))
    const { result } = renderUseJob()

    await advance(0)
    expect(result.current.error).toMatchObject({ status: 404 })
    await advance(POLL_INTERVAL_MS * 4)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('pauses while the tab is hidden and refreshes when it is visible again', async () => {
    const fetchMock = stubReplies(ok(JOBS.running))
    renderUseJob()
    await advance(0)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    act(() => focusManager.setFocused(false))
    await advance(POLL_INTERVAL_MS * 3)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    act(() => focusManager.setFocused(true))
    await advance(0)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await advance(POLL_INTERVAL_MS)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('keeps the last status and keeps polling after a temporary failure', async () => {
    const fetchMock = stubReplies(ok(JOBS.running), () => json(503, { detail: 'Job store is unavailable. Please retry later.' }), ok(JOBS.running))
    const { result } = renderUseJob()

    await advance(0)
    await advance(POLL_INTERVAL_MS)
    expect(result.current.isError).toBe(true)
    expect(result.current.data?.status).toBe('running')
    await advance(POLL_INTERVAL_MS)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(result.current.isError).toBe(false)
  })

  it('does not keep polling when the first load fails', async () => {
    const fetchMock = stubReplies(() => json(503, { detail: 'Job store is unavailable. Please retry later.' }))
    renderUseJob()

    await advance(0)
    await advance(POLL_INTERVAL_MS * 4)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
