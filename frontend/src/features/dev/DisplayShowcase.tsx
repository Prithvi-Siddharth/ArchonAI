import { Activity, CircleCheck, CircleX, Inbox, Plus } from 'lucide-react'
import { useState } from 'react'

import {
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Progress,
  Skeleton,
  Spinner,
  StatCard,
  STATUS_META,
  StatusBadge,
  StatusIndicator,
  Tooltip,
  type Column,
  type Status,
} from '@/components/ui'
import { toast } from '@/stores/toast.store'

import { Example, Segmented, ShowcaseSection } from './showcase-helpers'

const STATUSES = Object.keys(STATUS_META) as Status[]

interface ServiceRow {
  id: string
  name: string
  category: string
  status: Status
  cost: string
}

const SERVICE_ROWS: ServiceRow[] = [
  { id: 'svc-0a91', name: 'Application Load Balancer', category: 'Networking', status: 'completed', cost: '$22' },
  { id: 'svc-1b47', name: 'Amazon ECS on Fargate', category: 'Compute', status: 'running', cost: '$310' },
  { id: 'svc-2c03', name: 'Amazon Aurora PostgreSQL', category: 'Database', status: 'queued', cost: '$480' },
  { id: 'svc-3d88', name: 'Amazon ElastiCache for Redis', category: 'Caching', status: 'failed', cost: '$95' },
  { id: 'svc-4e12', name: 'AWS WAF', category: 'Security', status: 'cancelled', cost: '$18' },
]

const SERVICE_COLUMNS: Column<ServiceRow>[] = [
  {
    key: 'name',
    header: 'Service',
    grow: true,
    cell: (row) => (
      <>
        <p className="truncate font-medium">{row.name}</p>
        <p className="font-mono text-meta text-muted-foreground">{row.id}</p>
      </>
    ),
  },
  { key: 'category', header: 'Category', hideBelow: 'md', className: 'text-muted-foreground', cell: (row) => row.category },
  { key: 'status', header: 'Status', cell: (row) => <StatusBadge status={row.status} /> },
  { key: 'cost', header: 'Monthly', align: 'right', hideBelow: 'sm', className: 'tabular-nums', cell: (row) => row.cost },
]

export function CardsShowcase() {
  const [statsLoading, setStatsLoading] = useState(false)

  return (
    <ShowcaseSection id="cards" title="Cards" description="Base card with header, content and footer, and statistic cards.">
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Cost estimate"
            description="Monthly range for the current design."
            action={
              <Button variant="ghost" size="sm" onClick={() => toast({ title: 'Header action clicked' })}>
                Details
              </Button>
            }
          />
          <CardContent>
            <p className="text-stat">$1,000 – $2,000</p>
            <p className="mt-1 text-muted-foreground">Compute and the database are the largest cost drivers.</p>
          </CardContent>
          <CardFooter>
            <Button variant="outline" size="sm" onClick={() => toast({ title: 'Cancelled' })}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => toast({ tone: 'success', title: 'Estimate saved' })}>
              Save estimate
            </Button>
          </CardFooter>
        </Card>
        <Card>
          <CardContent className="py-5">
            <p className="text-card-title">Card without header</p>
            <p className="mt-1 text-muted-foreground">
              Cards use a subtle border, an 8px radius and a near-invisible shadow. Content and footer padding match the header.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-overline text-muted-foreground uppercase">Statistic cards</p>
        <Segmented
          label="Statistic card state"
          value={statsLoading ? 'loading' : 'data'}
          onChange={(value) => setStatsLoading(value === 'loading')}
          options={[
            { value: 'data', label: 'Data' },
            { value: 'loading', label: 'Loading' },
          ]}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Total generations" value="128" detail="All jobs submitted" icon={Activity} loading={statsLoading} />
        <StatCard label="Successful jobs" value="114" detail="89% of all jobs" icon={CircleCheck} tone="success" loading={statsLoading} />
        <StatCard label="Failed jobs" value="9" detail="7% of all jobs" icon={CircleX} tone="danger" loading={statsLoading} />
      </div>
    </ShowcaseSection>
  )
}

export function StatusShowcase() {
  const [progress, setProgress] = useState(40)

  return (
    <ShowcaseSection id="status" title="Status" description="Badges, indicators, progress, spinners and skeleton loaders.">
      <Card>
        <CardContent className="space-y-6 py-5">
          <Example label="Status badge">
            {STATUSES.map((status) => (
              <StatusBadge key={status} status={status} />
            ))}
          </Example>
          <Example label="Status indicator" className="gap-x-6">
            {STATUSES.map((status) => (
              <StatusIndicator key={status} status={status} />
            ))}
          </Example>
          <div className="space-y-3">
            <p className="text-overline text-muted-foreground uppercase">Progress</p>
            <div className="grid gap-5 md:grid-cols-2">
              <div className="space-y-3">
                <Progress label="Designing architecture" value={progress} />
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setProgress((value) => Math.max(0, value - 10))}>
                    −10%
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setProgress((value) => Math.min(100, value + 10))}>
                    +10%
                  </Button>
                </div>
              </div>
              <Progress label="Waiting for a worker" />
              <Progress label="Validation passed" value={100} tone="success" />
              <Progress label="Daily token quota used" value={82} tone="warning" />
              <Progress label="Failed checks" value={30} tone="danger" size="sm" />
            </div>
          </div>
          <Example label="Spinner">
            <Spinner size="sm" />
            <Spinner size="md" />
            <Spinner size="lg" label="Loading architecture" />
          </Example>
          <div className="space-y-3">
            <p className="text-overline text-muted-foreground uppercase">Skeleton</p>
            <div className="flex items-start gap-4">
              <Skeleton className="size-10 shrink-0 rounded-lg" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-3 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </ShowcaseSection>
  )
}

type TableMode = 'data' | 'loading' | 'empty'

export function DataShowcase() {
  const [mode, setMode] = useState<TableMode>('data')
  const [retrying, setRetrying] = useState(false)

  const retry = () => {
    setRetrying(true)
    window.setTimeout(() => {
      setRetrying(false)
      toast({ tone: 'success', title: 'Loaded', description: 'The retry callback ran.' })
    }, 1200)
  }

  return (
    <ShowcaseSection
      id="data"
      title="Data display"
      description="Table (with loading and empty states), empty and error states, and tooltips. Section headers on this page are SectionHeader."
    >
      <Card>
        <CardHeader
          title="Services"
          description="Columns hide on small screens; long names truncate."
          action={
            <Segmented
              label="Table state"
              value={mode}
              onChange={setMode}
              options={[
                { value: 'data', label: 'Data' },
                { value: 'loading', label: 'Loading' },
                { value: 'empty', label: 'Empty' },
              ]}
            />
          }
        />
        <DataTable
          caption="Example services"
          columns={SERVICE_COLUMNS}
          rows={mode === 'empty' ? [] : SERVICE_ROWS}
          loading={mode === 'loading'}
          loadingRows={4}
          getRowKey={(row) => row.id}
          empty={<EmptyState compact icon={Inbox} title="No services" description="This design has no services yet." />}
        />
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <EmptyState
            icon={Inbox}
            title="No architectures yet"
            description="Generate your first architecture to see it here."
            action={
              <Button onClick={() => toast({ title: 'Empty-state action clicked' })}>
                <Plus className="size-4" aria-hidden="true" />
                New Architecture
              </Button>
            }
          />
        </Card>
        <Card>
          <ErrorState description="The job list could not be loaded." onRetry={retry} isRetrying={retrying} />
        </Card>
      </div>

      <Card>
        <CardContent className="py-5">
          <Example label="Tooltip (hover, or focus with Tab; Escape hides)">
            {(['top', 'right', 'bottom', 'left'] as const).map((side) => (
              <Tooltip key={side} content={`Tooltip on the ${side}`} side={side}>
                <Button variant="outline">{side[0].toUpperCase() + side.slice(1)}</Button>
              </Tooltip>
            ))}
          </Example>
        </CardContent>
      </Card>
    </ShowcaseSection>
  )
}
