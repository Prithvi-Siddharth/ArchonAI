import { SearchX } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { ApiError } from '@/api/client'
import { buttonVariants, Card, CardContent, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui'
import { useNow } from '@/hooks/useNow'
import { useSubmissionsStore } from '@/stores/submissions.store'
import { shortId } from '@/utils/format'

import { isFinalJob, jobPhase } from './job-phase'
import { JobDetails } from './JobDetails'
import { JobStatusBadge } from './JobStatusBadge'
import { JobStatusPanel } from './JobStatusPanel'
import { useJob } from './useJob'

function LoadingCard() {
  return (
    <Card aria-busy="true">
      <CardContent className="space-y-4 py-5">
        <span className="sr-only">Loading job</span>
        <div className="flex items-center gap-3">
          <Skeleton className="size-9" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        </div>
        <Skeleton className="h-1 w-full" />
        <div className="grid grid-cols-3 gap-4 pt-4">
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="mx-auto h-12 w-20" />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/** Live status of one job: polls GET /jobs/{id} until it succeeds or fails. */
export function JobPage() {
  const { jobId = '' } = useParams()
  const query = useJob(jobId)
  const job = query.data
  const phase = job ? jobPhase(job) : null
  // Tick every second for the elapsed time while the job is unfinished.
  const now = useNow(job && !isFinalJob(job) ? 1000 : null)
  const requestPreview = useSubmissionsStore((state) => state.submissions.find((s) => s.jobId === jobId)?.requestPreview)

  const notFound = query.error instanceof ApiError && query.error.status === 404
  const errorMessage = query.error instanceof ApiError ? query.error.message : 'The job status could not be loaded.'

  let content
  if (job && phase) {
    content = (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        {/* Wrapper keeps the card at its own height instead of stretching to the details card. */}
        <div className="min-w-0">
          <JobStatusPanel
            job={job}
            phase={phase}
            now={now}
            updatedAt={query.dataUpdatedAt}
            refreshError={query.isError ? errorMessage : undefined}
          />
        </div>
        <JobDetails job={job} now={now} requestPreview={requestPreview} />
      </div>
    )
  } else if (notFound) {
    content = (
      <Card>
        <EmptyState
          icon={SearchX}
          title="Job not found"
          description={`No job with ID ${shortId(jobId)} exists on the server. Check the link, or the job may have been removed.`}
          action={
            <Link to="/dashboard" className={buttonVariants({ variant: 'outline' })}>
              Go to dashboard
            </Link>
          }
        />
      </Card>
    )
  } else if (query.isError) {
    content = (
      <Card>
        <ErrorState
          title="Couldn't load this job"
          description={errorMessage}
          onRetry={() => query.refetch()}
          isRetrying={query.isFetching}
        />
      </Card>
    )
  } else {
    content = <LoadingCard />
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Architecture job"
        description="Live status of one architecture generation job."
        badge={job ? <JobStatusBadge status={job.status} /> : undefined}
        actions={
          <Link to="/dashboard" className={buttonVariants({ variant: 'outline' })}>
            Dashboard
          </Link>
        }
      />
      {content}
    </div>
  )
}
