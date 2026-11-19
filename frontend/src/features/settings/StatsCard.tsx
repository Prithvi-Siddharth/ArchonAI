import { Activity, CircleCheck, Clock, Layers, Star, TrendingUp } from 'lucide-react'
import { Link } from 'react-router'

import { ApiError } from '@/api/client'
import { buttonVariants, Card, CardHeader, EmptyState, ErrorState, StatCard } from '@/components/ui'
import type { Stats, StatsDay } from '@/types/api'
import { formatDateTime, formatDuration, formatNumber } from '@/utils/format'

import { useStats } from './useAccount'

const EMPTY = '—'
const percent = (fraction: number | null) => (fraction === null ? EMPTY : `${Math.round(fraction * 100)}%`)
const decimal = (value: number | null) => (value === null ? EMPTY : formatNumber(Math.round(value * 10) / 10))

/** "Nov 19" for a UTC calendar day ("2026-11-19"). */
function dayLabel(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

/** Jobs per day as bars. The numbers are also in a table for screen readers. */
function DailyBars({ daily }: { daily: StatsDay[] }) {
  const max = Math.max(1, ...daily.map((day) => day.jobs))
  const total = daily.reduce((sum, day) => sum + day.jobs, 0)
  return (
    <figure className="space-y-2">
      <div aria-hidden="true" className="flex h-24 items-end gap-1 border-b border-border">
        {daily.map((day) => (
          <div key={day.date} className="flex h-full min-w-0 flex-1 items-end" title={`${dayLabel(day.date)}: ${day.jobs} ${day.jobs === 1 ? 'job' : 'jobs'}`}>
            <div
              className={day.jobs > 0 ? 'w-full rounded-t-sm bg-primary' : 'w-full rounded-t-sm bg-border'}
              style={{ height: day.jobs > 0 ? `${Math.max(8, (day.jobs / max) * 100)}%` : '2px' }}
            />
          </div>
        ))}
      </div>
      <div aria-hidden="true" className="flex justify-between text-meta text-muted-foreground">
        <span>{dayLabel(daily[0].date)}</span>
        <span>{dayLabel(daily[daily.length - 1].date)}</span>
      </div>
      <table className="sr-only">
        <caption>Jobs submitted per day, last {daily.length} days (UTC)</caption>
        <tbody>
          {daily.map((day) => (
            <tr key={day.date}>
              <th scope="row">{dayLabel(day.date)}</th>
              <td>{day.jobs}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <figcaption className="text-meta text-muted-foreground">
        Jobs per day over the last {daily.length} days (UTC): {formatNumber(total)} in total.
      </figcaption>
    </figure>
  )
}

function Numbers({ stats }: { stats: Stats }) {
  const finished = stats.jobs.succeeded + stats.jobs.failed
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <StatCard
          label="Total jobs"
          value={formatNumber(stats.jobs.total)}
          detail={`${formatNumber(stats.jobs.succeeded)} succeeded · ${formatNumber(stats.jobs.failed)} failed`}
          icon={Layers}
        />
        <StatCard
          label="Success rate"
          value={percent(stats.success_rate)}
          detail={finished ? `of ${formatNumber(finished)} finished ${finished === 1 ? 'job' : 'jobs'}` : 'No finished jobs yet'}
          icon={CircleCheck}
          tone="success"
        />
        <StatCard
          label="Average time to finish"
          value={stats.average_total_seconds === null ? EMPTY : formatDuration(stats.average_total_seconds * 1000)}
          detail="From submit to done"
          icon={Clock}
        />
        <StatCard
          label="Average critic score"
          value={stats.average_critic_score === null ? EMPTY : `${decimal(stats.average_critic_score)}/100`}
          detail={stats.approval_rate === null ? 'No reviews yet' : `${percent(stats.approval_rate)} approved by the critic`}
          icon={Star}
          tone="warning"
        />
        <StatCard label="Average AWS services" value={decimal(stats.average_aws_services)} detail="Per succeeded design" icon={Activity} />
        <StatCard
          label="Last 7 days"
          value={formatNumber(stats.jobs_last_7_days)}
          detail={`${formatNumber(stats.jobs_last_30_days)} in the last 30 days`}
          icon={TrendingUp}
          tone="info"
        />
      </div>

      <DailyBars daily={stats.daily} />

      <dl className="grid gap-x-6 gap-y-2 text-meta text-muted-foreground sm:grid-cols-2">
        <div>
          <dt className="inline">First job: </dt>
          <dd className="inline font-medium text-foreground">{stats.first_job_at ? formatDateTime(stats.first_job_at) : EMPTY}</dd>
        </div>
        <div>
          <dt className="inline">Latest job: </dt>
          <dd className="inline font-medium text-foreground">{stats.last_job_at ? formatDateTime(stats.last_job_at) : EMPTY}</dd>
        </div>
      </dl>
      {stats.sample_size > 0 && (
        <p className="text-meta text-muted-foreground">
          Averages are based on your {stats.sample_capped ? `newest ${formatNumber(stats.sample_size)}` : formatNumber(stats.sample_size)} succeeded{' '}
          {stats.sample_size === 1 ? 'job' : 'jobs'}.
        </p>
      )}
    </div>
  )
}

/** The signed-in user's own numbers: counts, rates, averages and the last two weeks of activity. */
export function StatsCard() {
  const query = useStats()
  const stats = query.data

  let body
  if (stats && stats.jobs.total === 0) {
    body = (
      <EmptyState
        compact
        icon={Layers}
        title="No jobs yet"
        description="Your statistics appear here after you submit your first architecture request."
        action={
          <Link to="/architectures/new" className={buttonVariants()}>
            New Architecture
          </Link>
        }
      />
    )
  } else if (stats) {
    body = (
      <div className="px-5 py-5">
        <Numbers stats={stats} />
      </div>
    )
  } else if (query.isError) {
    body = (
      <ErrorState
        compact
        title="Couldn't load your statistics"
        description={query.error instanceof ApiError ? query.error.message : 'Please try again.'}
        onRetry={() => void query.refetch()}
        isRetrying={query.isFetching}
      />
    )
  } else {
    body = (
      <div className="grid gap-3 px-5 py-5 sm:grid-cols-2" aria-busy="true">
        <span className="sr-only">Loading your statistics</span>
        {Array.from({ length: 6 }, (_, index) => (
          <StatCard key={index} label="" value="" loading />
        ))}
      </div>
    )
  }

  return (
    <Card>
      <CardHeader title="Your statistics" description="Numbers about your own architecture jobs." />
      {body}
    </Card>
  )
}
