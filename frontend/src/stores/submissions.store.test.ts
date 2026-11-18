import { beforeEach, describe, expect, it, vi } from 'vitest'

const KEY = 'archonai-submissions'

/** A fresh copy of the store module, so it loads whatever localStorage holds now. */
const loadStore = async () => {
  vi.resetModules()
  return import('./submissions.store')
}

beforeEach(() => localStorage.clear())

describe('previewOf', () => {
  it('flattens whitespace and keeps short requests whole', async () => {
    const { previewOf } = await loadStore()
    expect(previewOf('  Design a blog\n\nfor   10k readers.  ')).toBe('Design a blog for 10k readers.')
  })

  it('cuts long requests at 140 characters and adds an ellipsis', async () => {
    const { previewOf } = await loadStore()
    const preview = previewOf('a'.repeat(300))
    expect(preview).toBe(`${'a'.repeat(140)}…`)
  })

  it('counts emoji as single characters when cutting', async () => {
    const { previewOf } = await loadStore()
    expect(Array.from(previewOf('😀'.repeat(200)))).toHaveLength(141)
  })
})

describe('useSubmissionsStore', () => {
  it('records newest first and saves to localStorage without the full text', async () => {
    const { useSubmissionsStore } = await loadStore()
    useSubmissionsStore.getState().record('job-1', 'First request')
    useSubmissionsStore.getState().record('job-2', `Second request ${'x'.repeat(200)} SECRET-TAIL`)

    const ids = useSubmissionsStore.getState().submissions.map((s) => s.jobId)
    expect(ids).toEqual(['job-2', 'job-1'])
    const saved = localStorage.getItem(KEY) ?? ''
    expect(JSON.parse(saved).map((s: { jobId: string }) => s.jobId)).toEqual(['job-2', 'job-1'])
    expect(saved).not.toContain('SECRET-TAIL')
  })

  it('keeps one entry per job and at most 20 entries', async () => {
    const { useSubmissionsStore } = await loadStore()
    for (let i = 1; i <= 25; i++) useSubmissionsStore.getState().record(`job-${i}`, `Request ${i}`)
    useSubmissionsStore.getState().record('job-25', 'Request 25 again')

    const ids = useSubmissionsStore.getState().submissions.map((s) => s.jobId)
    expect(ids).toHaveLength(20)
    expect(ids[0]).toBe('job-25')
    expect(new Set(ids).size).toBe(20)
    expect(ids).not.toContain('job-5')
  })

  it('clear empties the list and storage', async () => {
    const { useSubmissionsStore } = await loadStore()
    useSubmissionsStore.getState().record('job-1', 'A request')
    useSubmissionsStore.getState().clear()
    expect(useSubmissionsStore.getState().submissions).toEqual([])
    expect(localStorage.getItem(KEY)).toBe('[]')
  })

  it.each([
    ['not JSON', 'not json', []],
    ['an object', '{"a":1}', []],
    ['mixed entries', JSON.stringify([{ jobId: 1 }, null, 'x', { jobId: 'ok', requestPreview: 'Valid', submittedAt: '2026-01-01T00:00:00Z' }]), ['ok']],
  ])('ignores malformed saved data (%s)', async (_name, raw, expectedIds) => {
    localStorage.setItem(KEY, raw)
    const { useSubmissionsStore } = await loadStore()
    expect(useSubmissionsStore.getState().submissions.map((s) => s.jobId)).toEqual(expectedIds)
  })

  it("picks up another tab's changes", async () => {
    const { useSubmissionsStore } = await loadStore()
    localStorage.setItem(KEY, JSON.stringify([{ jobId: 'from-other-tab', requestPreview: 'X', submittedAt: '2026-01-01T00:00:00Z' }]))
    window.dispatchEvent(new StorageEvent('storage', { key: KEY }))
    expect(useSubmissionsStore.getState().submissions.map((s) => s.jobId)).toEqual(['from-other-tab'])
  })
})
