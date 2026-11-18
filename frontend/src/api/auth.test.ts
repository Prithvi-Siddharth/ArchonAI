import { describe, expect, it, vi } from 'vitest'

import { fetchMe, login, logout, register } from './auth'
import { ApiError } from './client'

const reply = (status: number, body?: unknown) =>
  vi.stubGlobal('fetch', vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status })))

describe('auth API', () => {
  it('fetchMe: the user, null when signed out, and an error otherwise', async () => {
    reply(200, { id: 'u', email: 'a@b.co', created_at: '2026-11-18T10:00:00Z' })
    expect(await fetchMe()).toEqual({ id: 'u', email: 'a@b.co', created_at: '2026-11-18T10:00:00Z' })
    reply(401, { detail: 'Not signed in, or the session has expired.' })
    expect(await fetchMe()).toBeNull()
    reply(503, { detail: 'Authentication is not configured.' })
    await expect(fetchMe()).rejects.toMatchObject({ status: 503, message: 'Authentication is not configured.' })
  })

  it('login and register POST JSON to the right paths; the browser handles the cookie', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 'u', email: 'a@b.co', created_at: 'x' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await login({ email: 'a@b.co', password: 'pw' })
    await register({ email: 'a@b.co', password: 'password' })
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>
    expect(calls.map(([path, init]) => [path, init.method, JSON.parse(String(init.body))])).toEqual([
      ['/api/v1/auth/login', 'POST', { email: 'a@b.co', password: 'pw' }],
      ['/api/v1/auth/register', 'POST', { email: 'a@b.co', password: 'password' }],
    ])
    // Same-origin by default, so the HttpOnly cookie is sent and stored without any extra option.
    expect(calls.every(([, init]) => init.credentials === undefined)).toBe(true)
  })

  it('logout accepts 204 No Content', async () => {
    reply(204)
    await expect(logout()).resolves.toBeUndefined()
  })

  it('a wrong password is an ApiError with the backend message', async () => {
    reply(401, { detail: 'Invalid email or password.' })
    const error = await login({ email: 'a@b.co', password: 'nope' }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 401, message: 'Invalid email or password.', retryable: false })
  })
})
