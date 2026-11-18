import { Check, LoaderCircle, Minus, X } from 'lucide-react'

import { cn } from '@/utils/cn'
import { formatTime } from '@/utils/format'

import type { JobPhase, JobProgress } from './job-phase'

type StepState = 'complete' | 'current' | 'upcoming' | 'failed' | 'skipped'

interface Step {
  label: string
  state: StepState
  /** When the step happened (shown under complete/current steps). */
  time: string | null
  /** Replaces the time, e.g. "Retry pending". */
  note?: string
}

const SR_STATE: Record<StepState, string> = {
  complete: 'done',
  current: 'in progress',
  upcoming: 'not started',
  failed: 'failed',
  skipped: 'skipped',
}

/** Queued -> Running -> Completed (or Failed), from the job's phase and timestamps. */
export function timelineSteps(job: JobProgress, phase: JobPhase): Step[] {
  const queued = { label: 'Queued', time: job.created_at }
  const running = { label: 'Running', time: job.started_at }
  const done = { label: phase === 'failed' ? 'Failed' : 'Completed', time: job.finished_at }

  switch (phase) {
    case 'queued':
      return [{ ...queued, state: 'current' }, { ...running, state: 'upcoming' }, { ...done, state: 'upcoming' }]
    case 'retry-waiting':
      return [
        { ...queued, state: 'current', note: 'Retry pending' },
        { ...running, state: 'upcoming' },
        { ...done, state: 'upcoming' },
      ]
    case 'running':
      return [{ ...queued, state: 'complete' }, { ...running, state: 'current' }, { ...done, state: 'upcoming' }]
    case 'retry-running':
      return [
        { ...queued, state: 'complete' },
        { ...running, state: 'current', note: `Attempt ${job.attempts}` },
        { ...done, state: 'upcoming' },
      ]
    case 'succeeded':
      return [{ ...queued, state: 'complete' }, { ...running, state: 'complete' }, { ...done, state: 'complete' }]
    case 'failed':
      return [
        { ...queued, state: 'complete' },
        { ...running, state: job.started_at ? 'complete' : 'skipped' },
        { ...done, state: 'failed' },
      ]
  }
}

const CIRCLE: Record<StepState, string> = {
  complete: 'border-success/30 bg-success/10 text-success',
  current: 'border-info/40 bg-info/10 text-info',
  upcoming: 'border-border bg-surface text-muted-foreground',
  failed: 'border-danger/30 bg-danger/10 text-danger',
  skipped: 'border-dashed border-border-strong bg-surface text-muted-foreground',
}

function StepIcon({ state, index }: { state: StepState; index: number }) {
  if (state === 'complete') return <Check className="size-4" aria-hidden="true" />
  if (state === 'failed') return <X className="size-4" aria-hidden="true" />
  if (state === 'skipped') return <Minus className="size-4" aria-hidden="true" />
  if (state === 'current') return <LoaderCircle className="size-4 motion-safe:animate-spin" aria-hidden="true" />
  return <span className="font-mono text-meta" aria-hidden="true">{index + 1}</span>
}

export function JobTimeline({ job, phase, label = 'Job progress' }: { job: JobProgress; phase: JobPhase; label?: string }) {
  const steps = timelineSteps(job, phase)

  return (
    <ol aria-label={label} className="grid grid-cols-3">
      {steps.map((step, index) => (
        <li
          key={step.label}
          aria-current={step.state === 'current' ? 'step' : undefined}
          className="relative flex flex-col items-center text-center"
        >
          {index < steps.length - 1 && (
            <span
              aria-hidden="true"
              className={cn(
                'absolute top-4 right-[calc(-50%+1.25rem)] left-[calc(50%+1.25rem)] h-px',
                step.state === 'complete' ? 'bg-success/50' : 'bg-border',
              )}
            />
          )}
          <span className={cn('flex size-8 items-center justify-center rounded-full border', CIRCLE[step.state])}>
            <StepIcon state={step.state} index={index} />
          </span>
          <span className="mt-2 text-label">{step.label}</span>
          <span className="text-meta text-muted-foreground">
            {step.note ??
              (step.time && (step.state === 'complete' || step.state === 'current' || step.state === 'failed') ? (
                <time dateTime={step.time}>{formatTime(step.time)}</time>
              ) : (
                ' '
              ))}
          </span>
          <span className="sr-only">{SR_STATE[step.state]}</span>
        </li>
      ))}
    </ol>
  )
}
