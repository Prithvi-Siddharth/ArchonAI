// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { JOBS, makeJob, minutesAgo } from '@/test/job-fixtures'

import { isFinalJob, isTakingLong, jobPhase } from './job-phase'
import { timelineSteps } from './JobTimeline'

describe('jobPhase: the six situations from status + error', () => {
  it.each([
    ['queued, no error', JOBS.queued, 'queued'],
    ['running, no error', JOBS.running, 'running'],
    ['queued with an error', JOBS.retryWaiting, 'retry-waiting'],
    ['running with an error', JOBS.retryRunning, 'retry-running'],
    ['succeeded', JOBS.succeeded, 'succeeded'],
    ['failed', JOBS.failed, 'failed'],
  ] as const)('%s -> %s', (_name, job, phase) => {
    expect(jobPhase(job)).toBe(phase)
  })

  it('treats only succeeded and failed as final', () => {
    expect([JOBS.queued, JOBS.running, JOBS.retryWaiting, JOBS.retryRunning].map(isFinalJob)).toEqual([false, false, false, false])
    expect([JOBS.succeeded, JOBS.failed].map(isFinalJob)).toEqual([true, true])
    expect(isFinalJob(undefined)).toBe(false)
  })
})

describe('isTakingLong: past ~15 minutes per attempt', () => {
  const now = Date.now()

  it('flags an attempt running for over 15 minutes, by its start time', () => {
    expect(isTakingLong(makeJob({ status: 'running', started_at: minutesAgo(16) }), now)).toBe(true)
    expect(isTakingLong(makeJob({ status: 'running', started_at: minutesAgo(14) }), now)).toBe(false)
    expect(isTakingLong(makeJob({ status: 'running', started_at: minutesAgo(16), error: JOBS.retryRunning.error }), now)).toBe(true)
  })

  it('flags a first wait for a worker over 15 minutes, by its creation time', () => {
    expect(isTakingLong(makeJob({ created_at: minutesAgo(16) }), now)).toBe(true)
    expect(isTakingLong(makeJob({ created_at: minutesAgo(5) }), now)).toBe(false)
  })

  it('never flags finished jobs or a retry wait (the backend gives no time for it)', () => {
    expect(isTakingLong(makeJob({ ...JOBS.succeeded, started_at: minutesAgo(60) }), now)).toBe(false)
    expect(isTakingLong(makeJob({ ...JOBS.failed, started_at: minutesAgo(60) }), now)).toBe(false)
    expect(isTakingLong(makeJob({ ...JOBS.retryWaiting, created_at: minutesAgo(60) }), now)).toBe(false)
  })
})

describe('timelineSteps: Queued -> Running -> Completed', () => {
  const states = (job: Parameters<typeof jobPhase>[0]) => timelineSteps(job, jobPhase(job)).map((s) => `${s.label}:${s.state}`)

  it.each([
    ['queued', JOBS.queued, ['Queued:current', 'Running:upcoming', 'Completed:upcoming']],
    ['running', JOBS.running, ['Queued:complete', 'Running:current', 'Completed:upcoming']],
    ['retry waiting', JOBS.retryWaiting, ['Queued:current', 'Running:upcoming', 'Completed:upcoming']],
    ['retry running', JOBS.retryRunning, ['Queued:complete', 'Running:current', 'Completed:upcoming']],
    ['succeeded', JOBS.succeeded, ['Queued:complete', 'Running:complete', 'Completed:complete']],
    ['failed after running', JOBS.failed, ['Queued:complete', 'Running:complete', 'Failed:failed']],
    ['failed before starting', makeJob({ status: 'failed', error: { status_code: 503, message: 'x' } }), ['Queued:complete', 'Running:skipped', 'Failed:failed']],
  ])('%s', (_name, job, expected) => {
    expect(states(job)).toEqual(expected)
  })

  it('labels the retry steps', () => {
    expect(timelineSteps(JOBS.retryWaiting, 'retry-waiting')[0].note).toBe('Retry pending')
    expect(timelineSteps(JOBS.retryRunning, 'retry-running')[1].note).toBe('Attempt 2')
  })
})
