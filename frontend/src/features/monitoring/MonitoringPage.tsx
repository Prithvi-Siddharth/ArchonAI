import { Eye, Gauge, RotateCw, SearchX } from 'lucide-react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'

import { ApiError } from '@/api/client'
import { Badge, Button, buttonVariants, Card, EmptyState, ErrorState, Field, PageHeader, Select, Skeleton } from '@/components/ui'
import { requestTitle } from '@/features/architectures/history/HistoryEntry'
import { useJobHistory } from '@/features/architectures/history/useJobHistory'
import { JobStatusBadge } from '@/features/architectures/JobStatusBadge'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import type { JobHistoryItem } from '@/types/api'
import { formatRelativeTime, shortId } from '@/utils/format'

import { AgentsTable } from './AgentsTable'
import { LLMCallsTable } from './LLMCallsTable'
import { MonitoringNotice } from './MonitoringNotice'
import { SummaryCards } from './SummaryCards'
import { Timeline } from './Timeline'
import { MONITORING_POLL_MS, useJobMonitoring } from './useJobMonitoring'

const PICKER_JOBS = 20

const optionLabel = (job: JobHistoryItem) => {
  const title = requestTitle(job.user_request)
  return `${shortId(job.job_id)} · ${title.length > 56 ? `${title.slice(0, 55)}…` : title || 'No request text'} · ${job.status} · ${formatRelativeTime(job.created_at)}`
}

function LoadingBody() {
  return (
    <div className="space-y-6" aria-busy="true">
      <span className="sr-only">Loading monitoring data</span>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-28 w-full" />
        ))}
      </div>
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

/** Opens the newest job when no job is named in the address. */
function PickNewest() {
  const history = useJobHistory({ limit: PICKER_JOBS, offset: 0 })
  const newest = history.data?.items[0]
  if (newest) return <Navigate to={`/monitoring/${encodeURIComponent(newest.job_id)}`} replace />
  return (
    <div className="space-y-6">
      <PageHeader title="Monitoring" description="Metrics and logs for one of your jobs. Read-only." />
      <Card>
        {history.isError ? (
          <ErrorState compact title="Couldn't load your jobs" description="Please try again." onRetry={() => void history.refetch()} isRetrying={history.isFetching} />
        ) : history.data ? (
          <EmptyState
            icon={Gauge}
            title="No jobs to monitor yet"
            description="Submit an architecture request and its metrics and logs will show here."
            action={
              <Link to="/architectures/new" className={buttonVariants()}>
                New Architecture
              </Link>
            }
          />
        ) : (
          <div className="p-5" aria-busy="true">
            <span className="sr-only">Loading your jobs</span>
            <Skeleton className="h-10 w-full" />
          </div>
        )}
      </Card>
    </div>
  )
}

/** Metrics and logs of one job, read from AWS CloudWatch. Nothing on this page changes anything. */
function JobMonitoring({ jobId }: { jobId: string }) {
  useDocumentTitle('Monitoring')
  const navigate = useNavigate()
  const history = useJobHistory({ limit: PICKER_JOBS, offset: 0 })
  const query = useJobMonitoring(jobId)
  const data = query.data

  const jobs = history.data?.items ?? []
  const options = jobs.some((job) => job.job_id === jobId)
    ? jobs.map((job) => ({ value: job.job_id, label: optionLabel(job) }))
    : [{ value: jobId, label: `${shortId(jobId)} · this job` }, ...jobs.map((job) => ({ value: job.job_id, label: optionLabel(job) }))]

  const notFound = query.error instanceof ApiError && query.error.status === 404

  let body
  if (data?.state === 'ok' && data.summary) {
    body = (
      <div className="space-y-6">
        <SummaryCards summary={data.summary} />
        <AgentsTable agents={data.agents} />
        <LLMCallsTable calls={data.llm_calls} />
        <Timeline events={data.timeline} truncated={data.truncated} />
      </div>
    )
  } else if (data) {
    body = <MonitoringNotice data={data} onRetry={() => void query.refetch()} retrying={query.isFetching} />
  } else if (notFound) {
    body = (
      <Card>
        <EmptyState
          icon={SearchX}
          title="Job not found"
          description={`No job with ID ${shortId(jobId)} was found in your account. Check the link, or sign in with the account that submitted it.`}
          action={
            <Link to="/monitoring" className={buttonVariants({ variant: 'outline' })}>
              Choose another job
            </Link>
          }
        />
      </Card>
    )
  } else if (query.isError) {
    body = (
      <Card>
        <ErrorState
          title="Couldn't load monitoring data"
          description={query.error instanceof ApiError ? query.error.message : 'Please try again.'}
          onRetry={() => void query.refetch()}
          isRetrying={query.isFetching}
        />
      </Card>
    )
  } else {
    body = <LoadingBody />
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Monitoring"
        description="Metrics and logs for one of your jobs, read from AWS CloudWatch."
        badge={
          <Badge tone="info">
            <Eye className="size-3.5" aria-hidden="true" />
            Read-only
          </Badge>
        }
        actions={
          <>
            <Button variant="outline" onClick={() => void query.refetch()} disabled={query.isFetching}>
              <RotateCw className={query.isFetching ? 'size-4 animate-spin motion-reduce:animate-none' : 'size-4'} aria-hidden="true" />
              Refresh
            </Button>
            <Link to={`/architectures/${encodeURIComponent(jobId)}`} className={buttonVariants({ variant: 'outline' })}>
              Open job
            </Link>
          </>
        }
      />

      <Card>
        <div className="flex flex-col gap-4 px-5 py-4 lg:flex-row lg:items-end">
          <div className="min-w-0 flex-1">
            <Field label="Job">
              <Select value={jobId} onChange={(event) => navigate(`/monitoring/${encodeURIComponent(event.target.value)}`)} options={options} />
            </Field>
          </div>
          {data && (
            <div className="flex flex-wrap items-center gap-3 pb-2 text-meta text-muted-foreground">
              <JobStatusBadge status={data.job_status} />
              {data.may_still_arrive && <span>Updates automatically every {MONITORING_POLL_MS / 1000} seconds</span>}
            </div>
          )}
        </div>
        <p className="border-t border-border px-5 py-3 text-meta text-muted-foreground">
          This page only reads this job’s logs from AWS CloudWatch. It can’t change anything, and only you can see your jobs’ logs.
        </p>
      </Card>

      {body}
    </div>
  )
}

export function MonitoringPage() {
  const { jobId } = useParams()
  return jobId ? <JobMonitoring key={jobId} jobId={jobId} /> : <PickNewest />
}
