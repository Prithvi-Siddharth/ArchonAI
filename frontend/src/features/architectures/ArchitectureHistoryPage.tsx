import { ChevronLeft, ChevronRight, History, Plus, RotateCw, SearchX } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { ApiError } from '@/api/client'
import { Badge, Button, buttonVariants, Card, EmptyState, ErrorState, PageHeader, SearchInput, Skeleton } from '@/components/ui'
import type { JobStatus } from '@/types/architecture'
import { cn } from '@/utils/cn'
import { formatNumber } from '@/utils/format'

import { HistoryEntry } from './history/HistoryEntry'
import { HISTORY_PAGE_SIZE, readHistoryFilters, SEARCH_MAX_LENGTH, STATUS_FILTERS, toApiParams, writeHistoryFilters, type HistoryFilters } from './history/history-params'
import { useJobHistory } from './history/useJobHistory'

const SEARCH_DELAY_MS = 300

const plural = (n: number, word: string) => `${formatNumber(n)} ${word}${n === 1 ? '' : 's'}`

function LoadingList() {
  return (
    <ul aria-hidden="true" className="divide-y divide-border">
      {Array.from({ length: 5 }, (_, index) => (
        <li key={index} className="flex items-start gap-3 px-5 py-4">
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-5 w-20 rounded-full" />
        </li>
      ))}
    </ul>
  )
}

export function ArchitectureHistoryPage() {
  const [params, setParams] = useSearchParams()
  const filters = readHistoryFilters(params)
  const query = useJobHistory(toApiParams(filters))
  const data = query.data
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set())

  // The search box updates the URL after a short pause, so each keystroke isn't a request.
  const [searchText, setSearchText] = useState(filters.q)
  useEffect(() => {
    const next = searchText.trim().slice(0, SEARCH_MAX_LENGTH)
    if (next === filters.q) return
    const timer = window.setTimeout(
      () => setParams((current) => writeHistoryFilters({ ...readHistoryFilters(current), q: next, page: 1 }), { replace: true }),
      SEARCH_DELAY_MS,
    )
    return () => window.clearTimeout(timer)
  }, [searchText, filters.q, setParams])
  // Keep the box in step when the URL changes another way (Back button, Clear filters).
  const [lastUrlQ, setLastUrlQ] = useState(filters.q)
  if (lastUrlQ !== filters.q) {
    setLastUrlQ(filters.q)
    setSearchText(filters.q)
  }

  // Filter and page changes are new history entries, so Back returns to the previous view.
  function update(change: Partial<HistoryFilters>) {
    setParams((current) => writeHistoryFilters({ ...readHistoryFilters(current), ...change }))
  }

  const filtered = Boolean(filters.q || filters.status)
  const allCount = data ? Object.values(data.counts).reduce((sum, n) => sum + n, 0) : null
  const totalPages = data ? Math.max(1, Math.ceil(data.total / HISTORY_PAGE_SIZE)) : 1
  const first = data && data.items.length > 0 ? data.offset + 1 : 0
  const last = data ? data.offset + data.items.length : 0
  const statusLabel = (status: JobStatus | null) => STATUS_FILTERS.find((f) => f.value === status)?.label.toLowerCase() ?? ''

  const toggle = (jobId: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(jobId)) next.delete(jobId)
      else next.add(jobId)
      return next
    })

  let list
  if (!data && query.isError) {
    list = (
      <ErrorState
        title="Couldn't load your history"
        description={query.error instanceof ApiError ? query.error.message : 'Your architecture history could not be loaded. Please try again.'}
        onRetry={() => void query.refetch()}
        isRetrying={query.isFetching}
      />
    )
  } else if (!data) {
    list = <LoadingList />
  } else if (data.items.length === 0) {
    if (data.total > 0) {
      // A page number past the end (an old link, or jobs removed since).
      list = (
        <EmptyState
          compact
          icon={SearchX}
          title="This page is empty"
          description={`There ${data.total === 1 ? 'is' : 'are'} only ${totalPages === 1 ? '1 page' : `${totalPages} pages`} of results.`}
          action={
            <Button variant="outline" onClick={() => update({ page: totalPages })}>
              Go to page {totalPages}
            </Button>
          }
        />
      )
    } else if (!filtered) {
      list = (
        <EmptyState
          icon={History}
          title="No architectures yet"
          description="Jobs you submit are saved to your account and listed here, newest first."
          action={
            <Link to="/architectures/new" className={buttonVariants()}>
              <Plus className="size-4" aria-hidden="true" />
              New Architecture
            </Link>
          }
        />
      )
    } else {
      const what = filters.status ? `No ${statusLabel(filters.status)} jobs` : 'No jobs'
      list = (
        <EmptyState
          compact
          icon={SearchX}
          title={filters.q ? `${what} match “${filters.q}”` : what}
          description={filters.q ? 'Search looks in the request text and at the start of job IDs.' : 'Try another status, or show all jobs.'}
          action={
            <Button variant="outline" onClick={() => update({ q: '', status: null, page: 1 })}>
              Clear filters
            </Button>
          }
        />
      )
    }
  } else {
    list = (
      <ul aria-label="Architecture jobs" aria-busy={query.isPlaceholderData || undefined} className={cn('divide-y divide-border', query.isPlaceholderData && 'opacity-60')}>
        {data.items.map((item) => (
          <HistoryEntry key={item.job_id} item={item} expanded={expanded.has(item.job_id)} onToggle={() => toggle(item.job_id)} />
        ))}
      </ul>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Architecture History"
        description="Every architecture job you have submitted, newest first. Open one to see its details and results."
        badge={allCount !== null && !filters.q ? <Badge>{plural(allCount, 'job')}</Badge> : undefined}
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

      <Card>
        <div className="flex flex-col gap-3 border-b border-border px-4 py-3 sm:px-5 lg:flex-row lg:items-center">
          <div className="w-full lg:max-w-xs">
            <label className="sr-only" htmlFor="history-search">
              Search history
            </label>
            <SearchInput id="history-search" value={searchText} onValueChange={setSearchText} placeholder="Search requests or job ID…" maxLength={SEARCH_MAX_LENGTH} />
          </div>
          <div role="group" aria-label="Filter by status" className="flex flex-wrap items-center gap-1.5">
            {STATUS_FILTERS.map(({ value, label }) => {
              const active = filters.status === value
              const count = data ? (value ? data.counts[value] : allCount) : null
              return (
                <button
                  key={label}
                  type="button"
                  aria-pressed={active}
                  onClick={() => update({ status: value, page: 1 })}
                  className={cn(
                    'inline-flex h-control-sm items-center gap-1.5 rounded-md border px-2.5 text-meta font-medium transition-colors',
                    active ? 'border-foreground bg-foreground text-background' : 'border-border text-muted-foreground hover:bg-surface-muted hover:text-foreground',
                  )}
                >
                  {label}
                  {count !== null && <span className={cn('tabular-nums', !active && 'text-muted-foreground')}>{formatNumber(count)}</span>}
                </button>
              )
            })}
          </div>
          {filtered && (
            <Button variant="ghost" size="sm" className="lg:ml-auto" onClick={() => update({ q: '', status: null, page: 1 })}>
              Clear filters
            </Button>
          )}
        </div>

        {data && query.isError && (
          <p role="alert" className="border-b border-border px-5 py-2 text-meta text-danger">
            Couldn't refresh the list; showing what was loaded before.{' '}
            <button type="button" className="font-medium underline" onClick={() => void query.refetch()}>
              Try again
            </button>
          </p>
        )}

        {list}

        {data && data.total > 0 && (
          <div className="flex flex-col gap-3 border-t border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <p className="text-meta text-muted-foreground" aria-live="polite">
              {data.items.length > 0 ? `Showing ${formatNumber(first)}–${formatNumber(last)} of ${plural(data.total, 'job')}` : `${plural(data.total, 'job')} in total`}
            </p>
            <nav aria-label="Pagination" className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => update({ page: filters.page - 1 })} disabled={filters.page <= 1} aria-label="Previous page">
                <ChevronLeft className="size-4" aria-hidden="true" />
                Previous
              </Button>
              <span className="px-1 text-meta tabular-nums">
                Page {formatNumber(filters.page)} of {formatNumber(totalPages)}
              </span>
              <Button variant="outline" size="sm" onClick={() => update({ page: filters.page + 1 })} disabled={filters.page >= totalPages} aria-label="Next page">
                Next
                <ChevronRight className="size-4" aria-hidden="true" />
              </Button>
            </nav>
          </div>
        )}
      </Card>
    </div>
  )
}
