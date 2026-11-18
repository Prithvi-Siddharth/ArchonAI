import { ArrowRight, Layers, RotateCw } from 'lucide-react'
import { Link } from 'react-router'

import { Button, buttonVariants, Card, CardHeader, DataTable, EmptyState, ErrorState, Tooltip, type Column } from '@/components/ui'
import { requestTitle } from '@/features/architectures/history/HistoryEntry'
import { JobStatusBadge } from '@/features/architectures/JobStatusBadge'
import type { JobHistoryItem } from '@/types/api'
import { formatDateTime, formatRelativeTime, shortId } from '@/utils/format'

const EMPTY = '—'

const COLUMNS: Column<JobHistoryItem>[] = [
  {
    key: 'request',
    header: 'Request',
    grow: true,
    cell: (item) => {
      const title = requestTitle(item.user_request)
      return (
        <>
          <p className="truncate font-medium" title={title || undefined}>
            <Link to={`/architectures/${encodeURIComponent(item.job_id)}`} className="rounded-sm underline-offset-2 hover:underline">
              {title || <span className="text-muted-foreground italic">No request text</span>}
            </Link>
          </p>
          <p className="mt-0.5 text-meta text-muted-foreground">
            <span className="font-mono">{shortId(item.job_id)}</span>
            <span className="sm:hidden"> · {formatRelativeTime(item.created_at)}</span>
          </p>
        </>
      )
    },
  },
  { key: 'status', header: 'Status', cell: (item) => <JobStatusBadge status={item.status} /> },
  {
    key: 'services',
    header: 'Services',
    align: 'right',
    hideBelow: 'md',
    className: 'tabular-nums',
    cell: (item) => item.summary?.aws_service_count ?? EMPTY,
  },
  {
    key: 'score',
    header: 'Score',
    align: 'right',
    hideBelow: 'md',
    className: 'tabular-nums',
    cell: (item) => item.summary?.critic_score ?? EMPTY,
  },
  {
    key: 'created',
    header: 'Created',
    align: 'right',
    hideBelow: 'sm',
    className: 'whitespace-nowrap text-muted-foreground',
    cell: (item) => (
      <time dateTime={item.created_at} title={formatDateTime(item.created_at)}>
        {formatRelativeTime(item.created_at)}
      </time>
    ),
  },
]

interface RecentArchitecturesProps {
  items: JobHistoryItem[]
  loading: boolean
  /** Set when the list couldn't be loaded and there is nothing to show. */
  error?: string
  onRefresh: () => void
  refreshing: boolean
}

/** A preview of the newest jobs from the user's history; "View all" opens the History page. */
export function RecentArchitectures({ items, loading, error, onRefresh, refreshing }: RecentArchitecturesProps) {
  return (
    <Card>
      <CardHeader
        title="Recent architectures"
        description="Your newest jobs. The full list is in Architecture History."
        action={
          <div className="flex items-center gap-1">
            <Tooltip content="Refresh" describeTrigger={false}>
              <Button variant="ghost" size="icon-sm" onClick={onRefresh} disabled={refreshing} aria-label="Refresh recent architectures">
                <RotateCw className={refreshing ? 'size-3.5 animate-spin motion-reduce:animate-none' : 'size-3.5'} aria-hidden="true" />
              </Button>
            </Tooltip>
            <Link to="/architectures/history" className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
              View all
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          </div>
        }
      />
      {error ? (
        <ErrorState compact title="Couldn't load your jobs" description={error} onRetry={onRefresh} isRetrying={refreshing} />
      ) : (
        <DataTable
          caption="Your most recent architecture jobs"
          columns={COLUMNS}
          rows={items}
          loading={loading}
          getRowKey={(item) => item.job_id}
          empty={
            <EmptyState
              compact
              icon={Layers}
              title="No architectures yet"
              description="Jobs you submit are saved to your account and listed here."
            />
          }
        />
      )}
    </Card>
  )
}
