import { Activity, CircleCheck, CircleX, Plus } from 'lucide-react'
import { Link } from 'react-router'

import { ApiError } from '@/api/client'
import { buttonVariants, PageHeader, StatCard } from '@/components/ui'
import { formatNumber, formatPercent } from '@/utils/format'

import { NewArchitectureCta } from './NewArchitectureCta'
import { RecentArchitectures } from './RecentArchitectures'
import { useDashboardData } from './useDashboardData'

export function DashboardPage() {
  const { query, recent, stats } = useDashboardData()
  const loadError = !query.data && query.isError ? (query.error instanceof ApiError ? query.error.message : 'Your jobs could not be loaded.') : undefined
  const total = stats?.total ?? 0

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="An overview of your architecture jobs."
        actions={
          <Link to="/architectures/new" className={buttonVariants()}>
            <Plus className="size-4" aria-hidden="true" />
            New Architecture
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Total generations" value={formatNumber(total)} detail="All jobs in your account" icon={Activity} loading={!stats && !loadError} />
        <StatCard
          label="Successful jobs"
          value={formatNumber(stats?.succeeded ?? 0)}
          detail={`${formatPercent(stats?.succeeded ?? 0, total)} of your jobs`}
          icon={CircleCheck}
          tone="success"
          loading={!stats && !loadError}
        />
        <StatCard
          label="Failed jobs"
          value={formatNumber(stats?.failed ?? 0)}
          detail={`${formatPercent(stats?.failed ?? 0, total)} of your jobs`}
          icon={CircleX}
          tone="danger"
          loading={!stats && !loadError}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <RecentArchitectures
            items={recent}
            loading={query.isPending}
            error={loadError}
            onRefresh={() => void query.refetch()}
            refreshing={query.isFetching}
          />
        </div>
        <NewArchitectureCta />
      </div>
    </div>
  )
}
