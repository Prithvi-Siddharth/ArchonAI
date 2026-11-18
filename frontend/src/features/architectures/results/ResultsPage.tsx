import { ArrowLeft, CircleX, Clock, Download, FileQuestion, SearchX } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'

import { ApiError } from '@/api/client'
import {
  Badge,
  Button,
  buttonVariants,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  Tabs,
} from '@/components/ui'
import type { ArchitectureResult, JobStatusResponse } from '@/types/api'
import { downloadJson } from '@/utils/download'
import { shortId } from '@/utils/format'

import { useJob } from '../useJob'
import { ArchitectureTab } from './architecture/ArchitectureTab'
import { CostTab } from './cost/CostTab'
import { ReviewTab } from './review/ReviewTab'
import { OverviewTab } from './OverviewTab'
import { parseResultTab, RESULT_TABS, type ResultTab } from './results-tabs'
import { ResultsSummary } from './ResultsSummary'
import { TabPlaceholder } from './TabPlaceholder'

const jobPath = (jobId: string) => `/architectures/${encodeURIComponent(jobId)}`

function LoadingState() {
  return (
    <div className="space-y-6" aria-busy="true">
      <span className="sr-only">Loading results</span>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Card key={index}>
            <CardContent className="space-y-3 py-5">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

/** The job exists but has no result to show (still running, failed, or no result returned). */
function ResultsUnavailable({ job }: { job: JobStatusResponse }) {
  const trackLink = (label: string) => (
    <Link to={jobPath(job.job_id)} className={buttonVariants({ variant: 'outline' })}>
      {label}
    </Link>
  )

  if (job.status === 'queued' || job.status === 'running') {
    return (
      <Card>
        <EmptyState
          icon={Clock}
          title="Results aren't ready yet"
          description={`This job is still ${job.status}. This page updates automatically and shows the results once the job succeeds.`}
          action={trackLink('Track progress')}
        />
      </Card>
    )
  }
  if (job.status === 'failed') {
    return (
      <Card>
        <EmptyState
          icon={CircleX}
          tone="danger"
          title="No results: the job failed"
          description={job.error?.message ?? 'The job failed before producing an architecture.'}
          action={trackLink('View job')}
        />
      </Card>
    )
  }
  return (
    <Card>
      <EmptyState
        icon={FileQuestion}
        title="Results unavailable"
        description="The job succeeded, but the server returned no result for it."
        action={trackLink('View job')}
      />
    </Card>
  )
}

function ResultsView({ result, tab, onTabChange }: { result: ArchitectureResult; tab: ResultTab; onTabChange: (tab: ResultTab) => void }) {
  return (
    <div className="space-y-6">
      <ResultsSummary result={result} onOpenReview={() => onTabChange('review')} />
      <Tabs
        label="Result sections"
        items={RESULT_TABS}
        value={tab}
        onValueChange={(id) => onTabChange(parseResultTab(id))}
      >
        {tab === 'overview' ? (
          <OverviewTab result={result} />
        ) : tab === 'architecture' ? (
          <ArchitectureTab result={result} />
        ) : tab === 'cost' ? (
          <CostTab result={result} />
        ) : tab === 'review' ? (
          <ReviewTab result={result} />
        ) : (
          <TabPlaceholder tab={tab} />
        )}
      </Tabs>
    </div>
  )
}

/** A succeeded job's full result. Reads the same cached query as the tracking page. */
export function ResultsPage() {
  const { jobId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = parseResultTab(searchParams.get('tab'))
  const query = useJob(jobId)
  const job = query.data
  const result = job?.status === 'succeeded' ? job.result : null

  const setTab = (next: ResultTab) =>
    setSearchParams(
      (params) => {
        const updated = new URLSearchParams(params)
        updated.set('tab', next)
        return updated
      },
      { replace: true },
    )

  let content
  if (result) {
    content = <ResultsView result={result} tab={tab} onTabChange={setTab} />
  } else if (job) {
    content = <ResultsUnavailable job={job} />
  } else if (query.error instanceof ApiError && query.error.status === 404) {
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
          title="Couldn't load the results"
          description={query.error instanceof ApiError ? query.error.message : 'The results could not be loaded.'}
          onRetry={() => query.refetch()}
          isRetrying={query.isFetching}
        />
      </Card>
    )
  } else {
    content = <LoadingState />
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Architecture Results"
        description={`Generated architecture for job ${shortId(jobId)}.`}
        badge={
          result ? (
            <>
              <Badge tone={result.approved ? 'success' : 'warning'}>{result.approved ? 'Approved' : 'Not approved'}</Badge>
              <Badge>Version {result.architecture.version}</Badge>
              {result.max_revisions_reached && <Badge tone="warning">Revision limit reached</Badge>}
            </>
          ) : undefined
        }
        actions={
          <>
            <Link to={jobPath(jobId)} className={buttonVariants({ variant: 'outline' })}>
              <ArrowLeft className="size-4" aria-hidden="true" />
              Back to job
            </Link>
            {result && (
              <Button variant="outline" onClick={() => downloadJson(`archonai-result-${jobId}.json`, result)}>
                <Download className="size-4" aria-hidden="true" />
                Download JSON
              </Button>
            )}
          </>
        }
      />
      {content}
    </div>
  )
}
