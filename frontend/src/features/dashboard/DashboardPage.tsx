import { Activity, CircleCheck, CircleX, Plus } from 'lucide-react'
import { Link } from 'react-router'

import { Badge, buttonVariants, PageHeader, StatCard } from '@/components/ui'
import { formatNumber, formatPercent } from '@/utils/format'

import { NewArchitectureCta } from './NewArchitectureCta'
import { placeholderJobStats, placeholderRecentArchitectures } from './placeholder-data'
import { RecentArchitectures } from './RecentArchitectures'

export function DashboardPage() {
  // Placeholder data until the API is connected -- see placeholder-data.ts.
  const stats = placeholderJobStats
  const recent = placeholderRecentArchitectures

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="An overview of your architecture generation jobs."
        badge={<Badge title="Placeholder values until the dashboard is connected to the API">Sample data</Badge>}
        actions={
          <Link to="/architectures/new" className={buttonVariants()}>
            <Plus className="size-4" aria-hidden="true" />
            New Architecture
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Total generations" value={formatNumber(stats.total)} detail="All jobs submitted" icon={Activity} />
        <StatCard
          label="Successful jobs"
          value={formatNumber(stats.succeeded)}
          detail={`${formatPercent(stats.succeeded, stats.total)} of all jobs`}
          icon={CircleCheck}
          tone="success"
        />
        <StatCard
          label="Failed jobs"
          value={formatNumber(stats.failed)}
          detail={`${formatPercent(stats.failed, stats.total)} of all jobs`}
          icon={CircleX}
          tone="danger"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <RecentArchitectures items={recent} />
        </div>
        <NewArchitectureCta />
      </div>
    </div>
  )
}
