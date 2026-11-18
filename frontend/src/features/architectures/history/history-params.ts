import type { JobHistoryParams } from '@/api/architectures'
import type { JobStatus } from '@/types/architecture'

/** Jobs per page on the History page (the API allows up to 50). */
export const HISTORY_PAGE_SIZE = 10
/** Same limit as the backend's `q` parameter. */
export const SEARCH_MAX_LENGTH = 200

export const STATUS_FILTERS: ReadonlyArray<{ value: JobStatus | null; label: string }> = [
  { value: null, label: 'All' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
]

const STATUSES: readonly string[] = ['queued', 'running', 'succeeded', 'failed']
const isJobStatus = (value: string | null): value is JobStatus => value !== null && STATUSES.includes(value)

/** The History page's state, kept in the URL so Back, reload and shared links keep it. */
export interface HistoryFilters {
  /** 1-based. */
  page: number
  status: JobStatus | null
  q: string
}

/** Read filters from the URL; anything invalid falls back to the default. */
export function readHistoryFilters(params: URLSearchParams): HistoryFilters {
  const page = Number(params.get('page'))
  const status = params.get('status')
  return {
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    status: isJobStatus(status) ? status : null,
    q: (params.get('q') ?? '').trim().slice(0, SEARCH_MAX_LENGTH),
  }
}

/** Filters as URL parameters, leaving out defaults so the plain page has a clean URL. */
export function writeHistoryFilters({ page, status, q }: HistoryFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (status) params.set('status', status)
  if (page > 1) params.set('page', String(page))
  return params
}

export function toApiParams({ page, status, q }: HistoryFilters, pageSize = HISTORY_PAGE_SIZE): JobHistoryParams {
  return { limit: pageSize, offset: (page - 1) * pageSize, ...(status ? { status } : {}), ...(q ? { q } : {}) }
}
