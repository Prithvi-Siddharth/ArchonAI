// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest, shouldRetryQuery } from './client'

const UNREACHABLE = "Can't reach the ArchonAI API. Check that the backend is running, then try again."

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function mockFetch(impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  const fetchMock = vi.fn(impl)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function rejection(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise
  } catch (error) {
    return error
  }
  throw new Error('expected the request to fail')
}

/** A fetch that only settles when its signal aborts (to test timeouts and cancellation). */
function hangingFetch(_input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    const signal = init?.signal
    if (signal?.aborted) return reject(signal.reason)
    signal?.addEventListener('abort', () => reject(signal.reason))
  })
}

describe('apiRequest', () => {
  it('returns the parsed JSON of a successful reply', async () => {
    const fetchMock = mockFetch(async () => json(200, [{ label: 'A', prompt: 'B' }]))
    await expect(apiRequest('/api/v1/architectures/examples')).resolves.toEqual([{ label: 'A', prompt: 'B' }])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/architectures/examples')
    expect(init?.method).toBe('GET')
    expect(init?.body).toBeUndefined()
  })

  it('sends a POST body as JSON with a JSON content type', async () => {
    const fetchMock = mockFetch(async () => json(202, { job_id: 'j1', status: 'queued', status_url: '/x' }))
    await apiRequest('/api/v1/architectures/jobs', { method: 'POST', body: { user_request: 'Design a blog.' } })
    const init = fetchMock.mock.calls[0][1]
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe('{"user_request":"Design a blog."}')
    expect(init?.headers).toMatchObject({ 'Content-Type': 'application/json' })
  })

  it('turns a FastAPI 422 list into field errors', async () => {
    mockFetch(async () =>
      json(422, {
        detail: [{ type: 'string_too_short', loc: ['body', 'user_request'], msg: 'String should have at least 10 characters' }],
      }),
    )
    const error = await rejection(apiRequest('/api/v1/architectures/jobs', { method: 'POST', body: {} }))
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      kind: 'validation',
      status: 422,
      message: 'String should have at least 10 characters',
      fieldErrors: { user_request: 'String should have at least 10 characters' },
      retryable: false,
    })
  })

  it.each([
    [404, 'Job not found.', false],
    [503, 'Job queue is unavailable. Please retry later.', true],
    [429, 'LLM provider rate limit reached. Please retry later.', true],
  ])('uses the backend message of a %i reply: %s (retryable: %s)', async (status, detail, retryable) => {
    mockFetch(async () => json(status, { detail }))
    const error = await rejection(apiRequest('/api/v1/architectures/jobs/x'))
    expect(error).toMatchObject({ kind: 'http', status, message: detail, retryable })
  })

  it('treats a 5xx without an API body (proxy could not connect) as unreachable', async () => {
    mockFetch(async () => new Response(null, { status: 500 }))
    expect(await rejection(apiRequest('/api/x'))).toMatchObject({ kind: 'unreachable', status: 500, message: UNREACHABLE, retryable: true })
  })

  it('treats a non-JSON success (an HTML page) as unreachable', async () => {
    mockFetch(async () => new Response('<!doctype html><title>app</title>', { status: 200, headers: { 'Content-Type': 'text/html' } }))
    expect(await rejection(apiRequest('/api/x'))).toMatchObject({ kind: 'unreachable', status: 200 })
  })

  it('treats a network failure as unreachable', async () => {
    mockFetch(async () => {
      throw new TypeError('fetch failed')
    })
    expect(await rejection(apiRequest('/api/x'))).toMatchObject({ kind: 'unreachable', status: null, message: UNREACHABLE, retryable: true })
  })

  it('times out', async () => {
    mockFetch(hangingFetch)
    expect(await rejection(apiRequest('/api/x', { timeoutMs: 20 }))).toMatchObject({ kind: 'timeout', status: null, retryable: true })
  })

  it("passes the caller's own cancellation through unchanged", async () => {
    mockFetch(hangingFetch)
    const controller = new AbortController()
    controller.abort()
    const error = await rejection(apiRequest('/api/x', { signal: controller.signal }))
    expect(error).not.toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ name: 'AbortError' })
  })
})

describe('shouldRetryQuery', () => {
  it.each([
    ['first failure, unreachable', true, 0, new ApiError('unreachable', 'x')],
    ['second failure, unreachable', false, 1, new ApiError('unreachable', 'x')],
    ['timeout', true, 0, new ApiError('timeout', 'x')],
    ['503', true, 0, new ApiError('http', 'x', { status: 503 })],
    ['404', false, 0, new ApiError('http', 'x', { status: 404 })],
    ['422', false, 0, new ApiError('validation', 'x', { status: 422 })],
    ['a non-API error', false, 0, new Error('x')],
  ])('%s -> retry: %s', (_name, expected, failureCount, error) => {
    expect(shouldRetryQuery(failureCount, error)).toBe(expected)
  })
})
