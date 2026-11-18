import { ArrowRight, CircleAlert, CircleCheck, CircleX, Clock, LoaderCircle, RotateCw, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { buttonVariants, Card, CardContent, Progress } from '@/components/ui'
import { TONE_SOFT, TONE_TEXT, type Tone } from '@/components/ui/tones'
import { cn } from '@/utils/cn'
import { formatDuration } from '@/utils/format'

import { isTakingLong, type JobPhase, type JobProgress } from './job-phase'
import { JobTimeline } from './JobTimeline'
import { POLL_INTERVAL_MS } from './useJob'

const PHASE: Record<JobPhase, { title: string; tone: Tone; icon: LucideIcon; spin?: boolean }> = {
  queued: { title: 'Waiting for a worker', tone: 'info', icon: Clock },
  running: { title: 'Generating architecture', tone: 'info', icon: LoaderCircle, spin: true },
  'retry-waiting': { title: 'Retrying after a temporary problem', tone: 'warning', icon: RotateCw },
  'retry-running': { title: 'Retrying', tone: 'warning', icon: LoaderCircle, spin: true },
  succeeded: { title: 'Architecture ready', tone: 'success', icon: CircleCheck },
  failed: { title: 'Generation failed', tone: 'danger', icon: CircleX },
}

function phaseMessage(job: JobProgress, phase: JobPhase): string {
  switch (phase) {
    case 'queued':
      return 'The job is in the queue and starts as soon as a worker is free.'
    case 'running':
      return "ArchonAI's agents are analyzing the requirements, designing the architecture, reviewing it and estimating its cost. This usually takes several minutes."
    case 'retry-waiting':
      return 'The last attempt stopped because of a temporary problem. The job will be retried automatically.'
    case 'retry-running':
      return `Attempt ${job.attempts} is running after a temporary problem.`
    case 'succeeded':
      return 'The architecture was generated successfully.'
    case 'failed':
      return 'The job stopped and will not be retried.'
  }
}

function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <div className={cn('flex items-start gap-2.5 rounded-md border px-3 py-2.5', TONE_SOFT[tone])}>
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">{children}</div>
    </div>
  )
}

interface JobStatusPanelProps {
  job: JobProgress
  phase: JobPhase
  now: number
  /** When the status was last read successfully (ms). */
  updatedAt: number
  /** Set when the latest refresh failed; the panel keeps showing the last known status. */
  refreshError?: string
  /** Shown above the status, e.g. which job this is when several panels share a page. */
  context?: ReactNode
  /** Heading level of the status title; 3 when the panel sits under another h2. */
  headingLevel?: 2 | 3
}

export function JobStatusPanel({ job, phase, now, updatedAt, refreshError, context, headingLevel = 2 }: JobStatusPanelProps) {
  const Heading = headingLevel === 3 ? 'h3' : 'h2'
  const { title, tone, icon: Icon, spin } = PHASE[phase]
  const active = phase !== 'succeeded' && phase !== 'failed'
  const retrying = phase === 'retry-waiting' || phase === 'retry-running'

  return (
    <Card>
      <CardContent className="space-y-5 py-5">
        {context && <div className="border-b border-border pb-4">{context}</div>}
        <div className="flex items-start gap-3">
          <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-md', TONE_SOFT[tone])}>
            <Icon className={cn('size-5', TONE_TEXT[tone], spin && 'motion-safe:animate-spin')} aria-hidden="true" />
          </span>
          {/* Announced when the phase changes. */}
          <div className="min-w-0" aria-live="polite" aria-atomic="true">
            <Heading className="text-section-title">{title}</Heading>
            <p className="mt-0.5 text-muted-foreground">{phaseMessage(job, phase)}</p>
          </div>
        </div>

        {active && (
          <Progress
            label={title}
            hideLabel
            tone={retrying ? 'warning' : 'primary'}
            size="sm"
          />
        )}

        {retrying && job.error && (
          <Notice tone="warning">
            <p>
              <span className="font-medium">Reason: </span>
              {job.error.message}
            </p>
          </Notice>
        )}

        {phase === 'failed' && (
          <div role="alert" className={cn('rounded-md border px-3 py-2.5', TONE_SOFT.danger)}>
            <p className="font-medium">{job.error?.message ?? 'The job failed.'}</p>
            {job.error && <p className="mt-0.5 font-mono text-meta">Error {job.error.status_code}</p>}
          </div>
        )}

        {isTakingLong(job, now) && (
          <Notice tone="warning">
            {phase === 'queued' ? (
              <p>
                Still waiting after 15 minutes, which is longer than expected. The worker may be busy with other jobs or
                not running.
              </p>
            ) : (
              <p>
                This attempt has been running for over 15 minutes, which is longer than expected. The backend stops
                attempts that pass its time limit, so the status should change soon. If it doesn&apos;t, the worker may
                have stopped.
              </p>
            )}
          </Notice>
        )}

        {phase === 'succeeded' && (
          <Link to={`/architectures/${encodeURIComponent(job.job_id)}/results`} className={buttonVariants()}>
            View results
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        )}

        {phase === 'failed' && (
          <Link to="/architectures/new" className={buttonVariants({ variant: 'outline' })}>
            Submit a new request
          </Link>
        )}

        <div className="border-t border-border pt-5">
          <JobTimeline job={job} phase={phase} />
        </div>

        <p className="flex items-center gap-2 text-meta text-muted-foreground">
          {active ? (
            <>
              <span className="size-1.5 rounded-full bg-success motion-safe:animate-pulse" aria-hidden="true" />
              Updates automatically every {POLL_INTERVAL_MS / 1000} seconds · last checked{' '}
              {formatDuration(now - updatedAt)} ago
            </>
          ) : (
            'Final status. This job will not change again.'
          )}
        </p>

        {refreshError && (
          <Notice tone="warning">
            <p>
              Couldn&apos;t refresh the status: {refreshError} Showing the last known status
              {active ? '; retrying automatically.' : '.'}
            </p>
          </Notice>
        )}
      </CardContent>
    </Card>
  )
}
