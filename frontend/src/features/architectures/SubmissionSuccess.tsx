import { CircleCheck, Copy, Plus } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router'

import { Button, buttonVariants, Card, CardContent, CardFooter, Tooltip } from '@/components/ui'
import { toast } from '@/stores/toast.store'
import { formatDateTime } from '@/utils/format'

import type { SubmittedJob } from './ArchitectureRequestForm'
import { JobStatusBadge } from './JobStatusBadge'

async function copyJobId(jobId: string) {
  try {
    await navigator.clipboard.writeText(jobId)
    toast({ tone: 'success', title: 'Job ID copied' })
  } catch {
    toast({ tone: 'danger', title: "Couldn't copy the job ID", description: 'Select it and copy it manually.' })
  }
}

/** Shown after the API accepts a job (HTTP 202): its id, status and when it was submitted. */
export function SubmissionSuccess({ submitted, onNewRequest }: { submitted: SubmittedJob; onNewRequest: () => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const { job, request, submittedAt } = submitted

  // Move focus here so keyboard and screen-reader users land on the result.
  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  return (
    <Card>
      <CardContent className="space-y-5 py-5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-success/10 text-success">
            <CircleCheck className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 ref={headingRef} tabIndex={-1} className="text-section-title outline-none">
              Architecture job queued
            </h2>
            <p className="mt-0.5 text-muted-foreground">
              Generation runs in the background and can take several minutes. You can submit another request in the
              meantime.
            </p>
          </div>
        </div>

        <dl className="grid gap-x-6 gap-y-3 rounded-md border border-border bg-surface-muted/50 p-4 sm:grid-cols-[8rem_1fr]">
          <dt className="text-label text-muted-foreground">Job ID</dt>
          <dd className="flex min-w-0 items-center gap-2">
            <span className="truncate font-mono text-meta">{job.job_id}</span>
            <Tooltip content="Copy job ID" describeTrigger={false}>
              <Button variant="ghost" size="icon-sm" aria-label="Copy job ID" onClick={() => copyJobId(job.job_id)}>
                <Copy className="size-3.5" aria-hidden="true" />
              </Button>
            </Tooltip>
          </dd>
          <dt className="text-label text-muted-foreground">Status</dt>
          <dd>
            <JobStatusBadge status={job.status} />
          </dd>
          <dt className="text-label text-muted-foreground">Submitted</dt>
          <dd>
            <time dateTime={submittedAt}>{formatDateTime(submittedAt)}</time>
          </dd>
          <dt className="text-label text-muted-foreground">Request</dt>
          <dd className="line-clamp-3 text-muted-foreground" title={request}>
            {request}
          </dd>
        </dl>
      </CardContent>
      <CardFooter>
        <Link to="/dashboard" className={buttonVariants({ variant: 'outline' })}>
          Go to dashboard
        </Link>
        <Button onClick={onNewRequest}>
          <Plus className="size-4" aria-hidden="true" />
          Submit another
        </Button>
      </CardFooter>
    </Card>
  )
}
