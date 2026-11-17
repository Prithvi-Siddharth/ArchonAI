import { ArrowRight, Layers } from 'lucide-react'
import { Link } from 'react-router'

import { buttonVariants, Card, CardHeader, DataTable, EmptyState, type Column } from '@/components/ui'
import { JobStatusBadge } from '@/features/architectures/JobStatusBadge'
import type { ArchitectureSummary } from '@/types/architecture'
import { formatDateTime, formatRelativeTime, shortId } from '@/utils/format'

const EMPTY = '—'

const COLUMNS: Column<ArchitectureSummary>[] = [
  {
    key: 'request',
    header: 'Request',
    grow: true,
    cell: (item) => (
      <>
        <p className="truncate font-medium" title={item.request}>
          {item.request}
        </p>
        <p className="mt-0.5 text-meta text-muted-foreground">
          <span className="font-mono">{shortId(item.jobId)}</span>
          <span className="sm:hidden"> · {formatRelativeTime(item.createdAt)}</span>
        </p>
      </>
    ),
  },
  { key: 'status', header: 'Status', cell: (item) => <JobStatusBadge status={item.status} /> },
  {
    key: 'services',
    header: 'Services',
    align: 'right',
    hideBelow: 'md',
    className: 'tabular-nums',
    cell: (item) => item.serviceCount ?? EMPTY,
  },
  {
    key: 'score',
    header: 'Score',
    align: 'right',
    hideBelow: 'md',
    className: 'tabular-nums',
    cell: (item) => item.criticScore ?? EMPTY,
  },
  {
    key: 'created',
    header: 'Created',
    align: 'right',
    hideBelow: 'sm',
    className: 'whitespace-nowrap text-muted-foreground',
    cell: (item) => (
      <time dateTime={item.createdAt} title={formatDateTime(item.createdAt)}>
        {formatRelativeTime(item.createdAt)}
      </time>
    ),
  },
]

export function RecentArchitectures({ items }: { items: ArchitectureSummary[] }) {
  return (
    <Card>
      <CardHeader
        title="Recent architectures"
        description="The latest architecture generation jobs."
        action={
          <Link to="/architectures/history" className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
            View all
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        }
      />
      <DataTable
        caption="Recent architecture generation jobs"
        columns={COLUMNS}
        rows={items}
        getRowKey={(item) => item.jobId}
        empty={
          <EmptyState
            compact
            icon={Layers}
            title="No architectures yet"
            description="Architectures you generate will be listed here."
          />
        }
      />
    </Card>
  )
}
