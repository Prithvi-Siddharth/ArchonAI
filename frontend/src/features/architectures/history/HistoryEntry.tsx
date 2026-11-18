import { ArrowRight, ChevronDown, CircleAlert, Copy, FileText, RotateCw } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { Link } from 'react-router'

import { Badge, buttonVariants, Tooltip } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import type { JobHistoryItem } from '@/types/api'
import { cn } from '@/utils/cn'
import { formatDateTime, formatRelativeTime, shortId } from '@/utils/format'

import { copyJobId } from '../copyJobId'
import { JobStatusBadge } from '../JobStatusBadge'

const jobPath = (jobId: string) => `/architectures/${encodeURIComponent(jobId)}`

/** The request as a one-line title (whitespace collapsed); CSS truncates it to fit. */
export const requestTitle = (request: string) => request.replace(/\s+/g, ' ').trim()

function Detail({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={cn('min-w-0', wide && 'col-span-2')}>
      <dt className="text-meta text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words">{children}</dd>
    </div>
  )
}

const Missing = ({ children = 'Not available' }: { children?: string }) => <span className="text-muted-foreground">{children}</span>

/** What went wrong, in words; a queued job with an error is waiting to be retried. */
function ErrorNote({ item }: { item: JobHistoryItem }) {
  if (!item.error) return null
  const retrying = item.status !== 'failed'
  return (
    <div role="note" className={cn('col-span-2 flex items-start gap-2 rounded-md border px-3 py-2.5', retrying ? TONE_SOFT.warning : TONE_SOFT.danger)}>
      {retrying ? <RotateCw className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> : <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
      <p className="min-w-0 break-words">
        <span className="font-medium">{retrying ? 'Will retry after an error: ' : 'This job failed: '}</span>
        {item.error.message || 'No message was recorded.'}{' '}
        <span className="text-meta opacity-80">(HTTP {item.error.status_code})</span>
      </p>
    </div>
  )
}

export function HistoryEntry({ item, expanded, onToggle }: { item: JobHistoryItem; expanded: boolean; onToggle: () => void }) {
  const panelId = useId()
  const title = requestTitle(item.user_request)
  const summary = item.summary
  const hasResults = item.status === 'succeeded' && summary !== null

  return (
    <li data-job-id={item.job_id} data-status={item.status}>
      <div className="flex items-start gap-1 px-2 py-2 sm:px-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-controls={expanded ? panelId : undefined}
          className="flex min-w-0 flex-1 items-start gap-3 rounded-md px-2 py-2 text-left hover:bg-surface-muted"
        >
          <ChevronDown
            className={cn('mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none', expanded && 'rotate-180')}
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1">
            <span className={cn('block truncate font-medium', !title && 'text-muted-foreground italic')} title={title || undefined}>
              {title || 'No request text'}
            </span>
            <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-muted-foreground">
              <span className="font-mono">{shortId(item.job_id)}</span>
              <span>
                Submitted{' '}
                <time dateTime={item.created_at} title={formatDateTime(item.created_at)}>
                  {formatRelativeTime(item.created_at)}
                </time>
              </span>
              {item.finished_at && (
                <span className="hidden sm:inline">
                  Finished <time dateTime={item.finished_at}>{formatDateTime(item.finished_at)}</time>
                </span>
              )}
              {item.attempts > 0 && <span className="tabular-nums">{item.attempts === 1 ? '1 attempt' : `${item.attempts} attempts`}</span>}
              {summary?.architecture_version != null && <span className="tabular-nums">Version {summary.architecture_version}</span>}
            </span>
          </span>
          <span className="shrink-0 pt-px">
            <JobStatusBadge status={item.status} />
          </span>
        </button>
        <Tooltip content="Copy job ID" describeTrigger={false}>
          <button
            type="button"
            onClick={() => void copyJobId(item.job_id)}
            aria-label={`Copy job ID ${shortId(item.job_id)}`}
            className={cn(buttonVariants({ variant: 'ghost', size: 'icon-sm' }), 'mt-1.5')}
          >
            <Copy className="size-3.5" aria-hidden="true" />
          </button>
        </Tooltip>
      </div>

      {expanded && (
        <div id={panelId} role="region" aria-label={`Details of job ${shortId(item.job_id)}`} className="space-y-4 px-5 pb-5 sm:pl-12">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:gap-x-6">
            <Detail label="Request" wide>
              {item.user_request.trim() ? <span className="leading-6 whitespace-pre-line">{item.user_request}</span> : <Missing>No request text was stored.</Missing>}
            </Detail>
            <Detail label="Job ID" wide>
              <span className="flex items-center gap-1">
                <code className="min-w-0 font-mono text-meta break-all">{item.job_id}</code>
                <button
                  type="button"
                  onClick={() => void copyJobId(item.job_id)}
                  aria-label="Copy full job ID"
                  className={buttonVariants({ variant: 'ghost', size: 'icon-sm' })}
                >
                  <Copy className="size-3.5" aria-hidden="true" />
                </button>
              </span>
            </Detail>
            <Detail label="Status">
              <JobStatusBadge status={item.status} />
            </Detail>
            <Detail label="Attempts">
              <span className="tabular-nums">{item.attempts}</span>
            </Detail>
            <Detail label="Submitted">{formatDateTime(item.created_at)}</Detail>
            <Detail label={item.finished_at ? 'Completed' : 'Last updated'}>
              {item.finished_at ? formatDateTime(item.finished_at) : formatDateTime(item.updated_at)}
            </Detail>
            <ErrorNote item={item} />
            {summary && (
              <>
                <Detail label="Critic decision">
                  {summary.approved === null ? <Missing /> : <Badge tone={summary.approved ? 'success' : 'warning'}>{summary.approved ? 'Approved' : 'Not approved'}</Badge>}
                </Detail>
                <Detail label="Critic score">{summary.critic_score === null ? <Missing /> : <span className="tabular-nums">{summary.critic_score}/100</span>}</Detail>
                <Detail label="AWS services">{summary.aws_service_count === null ? <Missing /> : <span className="tabular-nums">{summary.aws_service_count}</span>}</Detail>
                <Detail label="Architecture version">
                  {summary.architecture_version === null ? <Missing /> : <span className="tabular-nums">{summary.architecture_version}</span>}
                </Detail>
                <Detail label="Estimated monthly cost" wide>
                  {summary.estimated_monthly_range ? summary.estimated_monthly_range : <Missing />}
                </Detail>
              </>
            )}
          </dl>
          <div className="flex flex-wrap gap-2">
            <Link to={jobPath(item.job_id)} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
              View Job
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
            {hasResults && (
              <Link to={`${jobPath(item.job_id)}/results`} className={buttonVariants({ size: 'sm' })}>
                <FileText className="size-3.5" aria-hidden="true" />
                View Results
              </Link>
            )}
          </div>
        </div>
      )}
    </li>
  )
}
