import { ArrowRight, FileText, Plus, RotateCw, Zap } from 'lucide-react'
import { Link } from 'react-router'

import { ApiError } from '@/api/client'
import { Badge, Button, buttonVariants, Card, CardContent, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import { requestTitle } from '@/features/architectures/history/HistoryEntry'
import { jobPhase } from '@/features/architectures/job-phase'
import { JobStatusBadge } from '@/features/architectures/JobStatusBadge'
import { JobStatusPanel } from '@/features/architectures/JobStatusPanel'
import { JobTimeline } from '@/features/architectures/JobTimeline'
import { useNow } from '@/hooks/useNow'
import type { JobHistoryItem } from '@/types/api'
import { cn } from '@/utils/cn'
import { formatDateTime, formatNumber, formatRelativeTime, shortId } from '@/utils/format'

import { useActivity } from './useActivity'

const jobPath = (jobId: string) => `/architectures/${encodeURIComponent(jobId)}`

function RequestLine({ item }: { item: JobHistoryItem }) {
  const title = requestTitle(item.user_request)
  return (
    <div className="min-w-0">
      <p className={cn('truncate font-medium', !title && 'text-muted-foreground italic')} title={title || undefined}>
        {title || 'No request text'}
      </p>
      <p className="mt-0.5 flex flex-wrap gap-x-3 text-meta text-muted-foreground">
        <span className="font-mono">{shortId(item.job_id)}</span>
        <span>
          Submitted{' '}
          <time dateTime={item.created_at} title={formatDateTime(item.created_at)}>
            {formatRelativeTime(item.created_at)}
          </time>
        </span>
      </p>
    </div>
  )
}

/** Which job a progress card belongs to, with a link to its full page. */
function ActiveJobHeader({ item }: { item: JobHistoryItem }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <RequestLine item={item} />
      <Link to={jobPath(item.job_id)} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'shrink-0')}>
        Open job
        <ArrowRight className="size-3.5" aria-hidden="true" />
      </Link>
    </div>
  )
}

function FinishedJob({ item }: { item: JobHistoryItem }) {
  const phase = jobPhase(item)
  return (
    <li className="space-y-4 px-5 py-4" data-job-id={item.job_id}>
      <div className="flex items-start justify-between gap-3">
        <RequestLine item={item} />
        <JobStatusBadge status={item.status} />
      </div>
      <JobTimeline job={item} phase={phase} label={`Progress of job ${shortId(item.job_id)}`} />
      {item.status === 'failed' && (
        <p className={cn('rounded-md border px-3 py-2 break-words', TONE_SOFT.danger)}>
          {item.error?.message || 'The job failed.'}
          {item.error && <span className="ml-1 font-mono text-meta opacity-80">(Error {item.error.status_code})</span>}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Link to={jobPath(item.job_id)} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
          View Job
          <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
        {item.status === 'succeeded' && item.summary && (
          <Link to={`${jobPath(item.job_id)}/results`} className={buttonVariants({ size: 'sm' })}>
            <FileText className="size-3.5" aria-hidden="true" />
            View Results
          </Link>
        )}
      </div>
    </li>
  )
}

function LoadingCard() {
  return (
    <Card aria-busy="true">
      <CardContent className="space-y-4 py-5">
        <span className="sr-only">Loading activity</span>
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-3 w-1/3" />
        <div className="grid grid-cols-3 gap-4 pt-2">
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="mx-auto h-12 w-20" />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function SectionTitle({ id, children, count }: { id: string; children: string; count?: number }) {
  return (
    <h2 id={id} className="flex items-center gap-2 text-section-title">
      {children}
      {count !== undefined && count > 0 && <Badge>{formatNumber(count)}</Badge>}
    </h2>
  )
}

/** Live progress of the user's jobs: the ones in progress, then the last few that finished. */
export function ActivityPage() {
  const { query, active, finished, hiddenActive } = useActivity()
  const data = query.data
  // Tick every second for the elapsed times while something is in progress.
  const now = useNow(active.length > 0 ? 1000 : null)
  const errorMessage = query.error instanceof ApiError ? query.error.message : 'Your jobs could not be loaded. Please try again.'
  const inProgress = active.length + hiddenActive

  let activeContent
  if (!data && query.isError) {
    activeContent = (
      <Card>
        <ErrorState title="Couldn't load your activity" description={errorMessage} onRetry={() => void query.refetch()} isRetrying={query.isFetching} />
      </Card>
    )
  } else if (!data) {
    activeContent = <LoadingCard />
  } else if (active.length === 0 && hiddenActive === 0) {
    activeContent = (
      <Card>
        <EmptyState
          compact
          icon={Zap}
          title="No jobs running right now"
          description="When you submit an architecture request, its progress shows here while it runs."
          action={
            <Link to="/architectures/new" className={buttonVariants()}>
              <Plus className="size-4" aria-hidden="true" />
              New Architecture
            </Link>
          }
        />
      </Card>
    )
  } else {
    activeContent = (
      <div className="space-y-4">
        {active.map((item) => (
          <article key={item.job_id} aria-label={`Job ${shortId(item.job_id)}`} data-job-id={item.job_id}>
            <JobStatusPanel
              job={item}
              phase={jobPhase(item)}
              now={now}
              updatedAt={query.dataUpdatedAt}
              refreshError={query.isError ? errorMessage : undefined}
              context={<ActiveJobHeader item={item} />}
              headingLevel={3}
            />
          </article>
        ))}
        {hiddenActive > 0 && (
          <p className="text-meta text-muted-foreground">
            {hiddenActive === 1 ? '1 older job is' : `${formatNumber(hiddenActive)} older jobs are`} also in progress.{' '}
            <Link to="/architectures/history" className="font-medium text-foreground underline underline-offset-2">
              See Architecture History
            </Link>
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Activity"
        description="Live progress of your architecture jobs. This page updates by itself while a job is running."
        badge={inProgress > 0 ? <Badge tone="info">{formatNumber(inProgress)} in progress</Badge> : undefined}
        actions={
          <>
            <Button variant="outline" onClick={() => void query.refetch()} disabled={query.isFetching}>
              <RotateCw className={cn('size-4', query.isFetching && 'animate-spin motion-reduce:animate-none')} aria-hidden="true" />
              Refresh
            </Button>
            <Link to="/architectures/new" className={buttonVariants()}>
              <Plus className="size-4" aria-hidden="true" />
              New Architecture
            </Link>
          </>
        }
      />

      {data && query.isError && active.length === 0 && (
        <p role="alert" className="text-meta text-danger">
          Couldn't refresh; showing what was loaded before.{' '}
          <button type="button" className="font-medium underline" onClick={() => void query.refetch()}>
            Try again
          </button>
        </p>
      )}

      <section aria-labelledby="activity-in-progress" className="space-y-3">
        <SectionTitle id="activity-in-progress" count={inProgress}>
          In progress
        </SectionTitle>
        {activeContent}
      </section>

      {data && (
        <section aria-labelledby="activity-finished" className="space-y-3">
          <SectionTitle id="activity-finished">Recently finished</SectionTitle>
          <Card>
            {finished.length === 0 ? (
              <EmptyState compact icon={FileText} title="No finished jobs yet" description="Jobs appear here once they succeed or fail." />
            ) : (
              <>
                <ul aria-label="Recently finished jobs" className="divide-y divide-border">
                  {finished.map((item) => (
                    <FinishedJob key={item.job_id} item={item} />
                  ))}
                </ul>
                <div className="border-t border-border px-5 py-3">
                  <Link to="/architectures/history" className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
                    All jobs in Architecture History
                    <ArrowRight className="size-3.5" aria-hidden="true" />
                  </Link>
                </div>
              </>
            )}
          </Card>
        </section>
      )}
    </div>
  )
}
