import { create } from 'zustand'

import { readStorage, writeStorage } from '@/utils/storage'

/**
 * A job submitted from this browser. The backend has no job-list endpoint, so
 * this list (kept in localStorage) is what the dashboard shows.
 */
export interface SubmissionRecord {
  jobId: string
  /** The first ~140 characters of the request; the full text is not stored. */
  requestPreview: string
  /** ISO 8601. */
  submittedAt: string
}

export const SUBMISSIONS_STORAGE_KEY = 'archonai-submissions'
const MAX_RECORDS = 20
const PREVIEW_LENGTH = 140

/** Single-line preview of a request, cut at 140 characters. */
export function previewOf(request: string): string {
  const characters = Array.from(request.replace(/\s+/g, ' ').trim())
  return characters.length > PREVIEW_LENGTH
    ? `${characters.slice(0, PREVIEW_LENGTH).join('').trimEnd()}…`
    : characters.join('')
}

function isRecord(value: unknown): value is SubmissionRecord {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  return (
    typeof record.jobId === 'string' &&
    typeof record.requestPreview === 'string' &&
    typeof record.submittedAt === 'string'
  )
}

/** Saved records, ignoring anything malformed (storage is user-editable). */
function load(): SubmissionRecord[] {
  try {
    const parsed: unknown = JSON.parse(readStorage(SUBMISSIONS_STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter(isRecord).slice(0, MAX_RECORDS) : []
  } catch {
    return []
  }
}

function save(records: SubmissionRecord[]) {
  writeStorage(SUBMISSIONS_STORAGE_KEY, JSON.stringify(records))
}

interface SubmissionsState {
  /** Newest first, at most 20. */
  submissions: SubmissionRecord[]
  record: (jobId: string, request: string) => void
  clear: () => void
}

export const useSubmissionsStore = create<SubmissionsState>()((set, get) => ({
  submissions: load(),
  record: (jobId, request) => {
    const entry: SubmissionRecord = { jobId, requestPreview: previewOf(request), submittedAt: new Date().toISOString() }
    const next = [entry, ...get().submissions.filter((record) => record.jobId !== jobId)].slice(0, MAX_RECORDS)
    save(next)
    set({ submissions: next })
  },
  clear: () => {
    save([])
    set({ submissions: [] })
  },
}))

// Other tabs: a submission or "Clear" there updates this tab too.
window.addEventListener('storage', (event) => {
  if (event.key === SUBMISSIONS_STORAGE_KEY || event.key === null) {
    useSubmissionsStore.setState({ submissions: load() })
  }
})
