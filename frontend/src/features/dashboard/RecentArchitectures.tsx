import { ArrowRight, Layers, RotateCw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import {
  Badge,
  Button,
  buttonVariants,
  Card,
  CardHeader,
  ConfirmDialog,
  DataTable,
  EmptyState,
  Skeleton,
  Tooltip,
  type Column,
} from '@/components/ui'
import { JobStatusBadge } from '@/features/architectures/JobStatusBadge'
import type { ArchitectureSummary, JobStatusView } from '@/types/architecture'
import { formatDateTime, formatRelativeTime, shortId } from '@/utils/format'

const EMPTY = '—'

function StatusCell({ status }: { status: JobStatusView }) {
  switch (status.state) {
    case 'loading':
      return (
        <>
          <Skeleton className="h-5 w-20 rounded-full" />
          <span className="sr-only">Loading status</span>
        </>
      )
    case 'known':
      return <JobStatusBadge status={status.status} />
    case 'not-found':
      return <Badge title="The server has no job with this ID.">Not found</Badge>
    case 'unavailable':
      return <Badge title="The status couldn't be loaded. Use Refresh to try again.">Unavailable</Badge>
  }
}

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
  { key: 'status', header: 'Status', cell: (item) => <StatusCell status={item.status} /> },
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

interface RecentArchitecturesProps {
  items: ArchitectureSummary[]
  /** Total saved submissions (the table shows only the most recent). */
  savedCount: number
  onRefresh: () => void
  refreshing: boolean
  onClear: () => void
}

export function RecentArchitectures({ items, savedCount, onRefresh, refreshing, onClear }: RecentArchitecturesProps) {
  const [confirmingClear, setConfirmingClear] = useState(false)
  const hasItems = items.length > 0

  return (
    <Card>
      <CardHeader
        title="Recent architectures"
        description="Jobs submitted from this browser, newest first."
        action={
          <div className="flex items-center gap-1">
            {hasItems && (
              <>
                <Tooltip content="Refresh statuses" describeTrigger={false}>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={onRefresh}
                    disabled={refreshing}
                    aria-label="Refresh statuses"
                  >
                    <RotateCw className={refreshing ? 'size-3.5 animate-spin' : 'size-3.5'} aria-hidden="true" />
                  </Button>
                </Tooltip>
                <Button variant="ghost" size="sm" onClick={() => setConfirmingClear(true)}>
                  Clear
                </Button>
              </>
            )}
            <Link to="/architectures/history" className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
              View all
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          </div>
        }
      />
      <DataTable
        caption="Architecture jobs submitted from this browser"
        columns={COLUMNS}
        rows={items}
        getRowKey={(item) => item.jobId}
        empty={
          <EmptyState
            compact
            icon={Layers}
            title="No architectures yet"
            description="Architectures you submit from this browser will be listed here."
          />
        }
      />

      <ConfirmDialog
        open={confirmingClear}
        title="Clear this browser's list?"
        description={`Removes ${savedCount === 1 ? 'the saved job' : `all ${savedCount} saved jobs`} from this browser's dashboard. The jobs themselves stay on the server.`}
        confirmLabel="Clear list"
        tone="destructive"
        onCancel={() => setConfirmingClear(false)}
        onConfirm={() => {
          onClear()
          setConfirmingClear(false)
        }}
      />
    </Card>
  )
}
