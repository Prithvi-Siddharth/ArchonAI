import { Copy } from 'lucide-react'

import { Button, Card, CardContent, CardHeader, Tooltip } from '@/components/ui'
import type { JobStatusResponse } from '@/types/api'
import { formatDateTime, formatDuration } from '@/utils/format'

import { copyJobId } from './copyJobId'
import { JobStatusBadge } from './JobStatusBadge'

const NONE = '—'

function Timestamp({ iso }: { iso: string | null }) {
  return iso ? <time dateTime={iso}>{formatDateTime(iso)}</time> : <span className="text-muted-foreground">{NONE}</span>
}

interface JobDetailsProps {
  job: JobStatusResponse
  now: number
  /** The request preview saved in this browser, if this job was submitted here. */
  requestPreview?: string
}

/** Facts about the job: id, status, attempts, timestamps and how long it has taken. */
export function JobDetails({ job, now, requestPreview }: JobDetailsProps) {
  const finished = job.finished_at !== null
  const created = new Date(job.created_at).getTime()
  const end = finished ? new Date(job.finished_at as string).getTime() : now
  const attemptStart = job.started_at ? new Date(job.started_at).getTime() : null

  return (
    <Card className="self-start">
      <CardHeader title="Details" />
      <CardContent>
        <dl className="space-y-3">
          <div>
            <dt className="text-label text-muted-foreground">Job ID</dt>
            <dd className="flex min-w-0 items-center gap-1">
              <span className="truncate font-mono text-meta">{job.job_id}</span>
              <Tooltip content="Copy job ID" describeTrigger={false}>
                <Button variant="ghost" size="icon-sm" aria-label="Copy job ID" onClick={() => copyJobId(job.job_id)}>
                  <Copy className="size-3.5" aria-hidden="true" />
                </Button>
              </Tooltip>
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-label text-muted-foreground">Status</dt>
            <dd>
              <JobStatusBadge status={job.status} />
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-label text-muted-foreground">Attempts</dt>
            <dd className="tabular-nums">{job.attempts}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-label text-muted-foreground">{finished ? 'Total time' : 'Elapsed'}</dt>
            <dd className="tabular-nums">{formatDuration(end - created)}</dd>
          </div>
          {attemptStart !== null && (
            <div className="flex items-center justify-between gap-3">
              <dt className="text-label text-muted-foreground">{finished ? 'Last attempt ran' : 'This attempt'}</dt>
              <dd className="tabular-nums">{formatDuration(end - attemptStart)}</dd>
            </div>
          )}
          <div>
            <dt className="text-label text-muted-foreground">Created</dt>
            <dd>
              <Timestamp iso={job.created_at} />
            </dd>
          </div>
          <div>
            <dt className="text-label text-muted-foreground">Started</dt>
            <dd>
              <Timestamp iso={job.started_at} />
            </dd>
          </div>
          <div>
            <dt className="text-label text-muted-foreground">Finished</dt>
            <dd>
              <Timestamp iso={job.finished_at} />
            </dd>
          </div>
          {requestPreview && (
            <div>
              <dt className="text-label text-muted-foreground">Request</dt>
              <dd className="text-muted-foreground">{requestPreview}</dd>
            </div>
          )}
        </dl>
      </CardContent>
    </Card>
  )
}
