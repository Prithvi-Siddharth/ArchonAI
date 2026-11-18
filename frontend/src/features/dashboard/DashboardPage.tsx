import { Activity, CircleCheck, CircleX, Plus } from 'lucide-react'
import { Link } from 'react-router'

import { Badge, buttonVariants, PageHeader, StatCard } from '@/components/ui'
import { useSubmissionsStore } from '@/stores/submissions.store'
import { toast } from '@/stores/toast.store'
import { formatNumber, formatPercent } from '@/utils/format'

import { NewArchitectureCta } from './NewArchitectureCta'
import { RecentArchitectures } from './RecentArchitectures'
import { useDashboardData } from './useDashboardData'

export function DashboardPage() {
  const { recent, stats, statsLoading, refresh, refreshing } = useDashboardData()
  const clearSubmissions = useSubmissionsStore((state) => state.clear)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="An overview of the architecture jobs submitted from this browser."
        badge={
          <Badge title="The backend has no job list yet, so the dashboard shows jobs submitted from this browser.">
            This browser
          </Badge>
        }
        actions={
          <Link to="/architectures/new" className={buttonVariants()}>
            <Plus className="size-4" aria-hidden="true" />
            New Architecture
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Total generations"
          value={formatNumber(stats.total)}
          detail="Submitted from this browser"
          icon={Activity}
        />
        <StatCard
          label="Successful jobs"
          value={formatNumber(stats.succeeded)}
          detail={`${formatPercent(stats.succeeded, stats.total)} of submissions`}
          icon={CircleCheck}
          tone="success"
          loading={statsLoading}
        />
        <StatCard
          label="Failed jobs"
          value={formatNumber(stats.failed)}
          detail={`${formatPercent(stats.failed, stats.total)} of submissions`}
          icon={CircleX}
          tone="danger"
          loading={statsLoading}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <RecentArchitectures
            items={recent}
            savedCount={stats.total}
            onRefresh={refresh}
            refreshing={refreshing}
            onClear={() => {
              clearSubmissions()
              toast({ title: 'List cleared', description: 'The jobs are still on the server.' })
            }}
          />
        </div>
        <NewArchitectureCta />
      </div>
    </div>
  )
}
