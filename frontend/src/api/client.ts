/**
 * Minimal HTTP client for the ArchonAI API.
 *
 * Calls are same-origin (paths start with /api); in development and preview the
 * Vite server proxies them to FastAPI (see vite.config.ts). Every failure is
 * turned into an ApiError with a message that is safe to show to users: either
 * the backend's own client-safe `detail`, or a fixed message written here.
 */
import type { ValidationErrorItem } from '@/types/api'

const DEFAULT_TIMEOUT_MS = 15_000

const UNREACHABLE_MESSAGE = "Can't reach the ArchonAI API. Check that the backend is running, then try again."
const TIMEOUT_MESSAGE = 'The ArchonAI API took too long to respond. Please try again.'

/** Statuses where repeating the same request later may succeed. */
const RETRYABLE_STATUSES = new Set([408, 429, 502, 503, 504])

/**
 * - unreachable: no usable reply (network failure, proxy can't connect, server crashed)
 * - timeout:     no reply within the time limit
 * - validation:  422, the request body was rejected
 * - http:        any other error reply from the API
 */
export type ApiErrorKind = 'unreachable' | 'timeout' | 'validation' | 'http'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  /** HTTP status, or null when no reply arrived. */
  readonly status: number | null
  /** 422 messages keyed by field name (e.g. `user_request`). */
  readonly fieldErrors: Readonly<Record<string, string>>
  /** Whether repeating the same request later could succeed. */
  readonly retryable: boolean

  constructor(
    kind: ApiErrorKind,
    message: string,
    { status = null, fieldErrors = {} }: { status?: number | null; fieldErrors?: Record<string, string> } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.fieldErrors = fieldErrors
    this.retryable = kind === 'unreachable' || kind === 'timeout' || (status !== null && RETRYABLE_STATUSES.has(status))
  }
}

/** TanStack Query retry rule: at most one retry, and only for temporary failures (never 404 or 422). */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  return failureCount < 1 && error instanceof ApiError && error.retryable
}

function isValidationList(detail: unknown): detail is ValidationErrorItem[] {
  return (
    Array.isArray(detail) &&
    detail.length > 0 &&
    detail.every((item) => typeof item?.msg === 'string' && Array.isArray(item?.loc))
  )
}

function errorFromReply(status: number, body: unknown): ApiError {
  const detail = typeof body === 'object' && body !== null && 'detail' in body ? body.detail : undefined

  if (status === 422 && isValidationList(detail)) {
    const fieldErrors: Record<string, string> = {}
    for (const item of detail) {
      const field = String(item.loc.at(-1) ?? '')
      if (field && !(field in fieldErrors)) fieldErrors[field] = item.msg
    }
    return new ApiError('validation', detail[0].msg, { status, fieldErrors })
  }
  if (typeof detail === 'string' && detail) return new ApiError('http', detail, { status })
  // No API error body: a proxy couldn't reach the backend, or the backend crashed.
  if (status >= 500) return new ApiError('unreachable', UNREACHABLE_MESSAGE, { status })
  return new ApiError('http', `The request failed (HTTP ${status}).`, { status })
}

/** A fetch or body-read failure: the caller's own cancellation passes through untouched. */
function transportError(error: unknown, callerSignal: AbortSignal | undefined, timeout: AbortSignal): unknown {
  if (callerSignal?.aborted) return error
  if (timeout.aborted) return new ApiError('timeout', TIMEOUT_MESSAGE)
  return new ApiError('unreachable', UNREACHABLE_MESSAGE)
}

/** Parsed JSON, or undefined for an empty or non-JSON body. */
async function readJson(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  /** Sent as JSON. */
  body?: unknown
  /** Cancels the request (e.g. TanStack Query's signal); rejects with the original AbortError. */
  signal?: AbortSignal
  timeoutMs?: number
}

/** Send a request to the API and return its parsed JSON reply, or throw an ApiError. */
export async function apiRequest<T>(
  path: string,
  { method = 'GET', body, signal, timeoutMs = DEFAULT_TIMEOUT_MS }: RequestOptions = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const combinedSignal = signal ? AbortSignal.any([signal, timeout]) : timeout

  let response: Response
  let data: unknown
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: combinedSignal,
    })
    data = await readJson(response)
  } catch (error) {
    throw transportError(error, signal, timeout)
  }

  if (!response.ok) throw errorFromReply(response.status, data)
  // 204 No Content (e.g. POST /auth/logout): success with no body by design.
  if (response.status === 204) return undefined as T
  // A success without JSON (e.g. index.html from a static host) means the API isn't behind this address.
  if (data === undefined) throw new ApiError('unreachable', UNREACHABLE_MESSAGE, { status: response.status })
  return data as T
}
