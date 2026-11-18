/** Account endpoints (backend: api/routes/auth.py). The session JWT lives in an HttpOnly cookie the browser sends itself. */
import type { Credentials, User } from '@/types/api'

import { ApiError, apiRequest } from './client'

export const AUTH_PATH = '/api/v1/auth'

/** GET /me -- the signed-in account, or null when not signed in (401). Other failures throw. */
export async function fetchMe(signal?: AbortSignal): Promise<User | null> {
  try {
    return await apiRequest<User>(`${AUTH_PATH}/me`, { signal })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

/** POST /login -- sets the session cookie. 401 for a wrong email or password. */
export function login(credentials: Credentials): Promise<User> {
  return apiRequest<User>(`${AUTH_PATH}/login`, { method: 'POST', body: credentials })
}

/** POST /register -- creates the account and signs in to it. 409 if the email is taken. */
export function register(credentials: Credentials): Promise<User> {
  return apiRequest<User>(`${AUTH_PATH}/register`, { method: 'POST', body: credentials })
}

/** POST /logout -- deletes the session cookie (204). */
export function logout(): Promise<void> {
  return apiRequest<void>(`${AUTH_PATH}/logout`, { method: 'POST' })
}
