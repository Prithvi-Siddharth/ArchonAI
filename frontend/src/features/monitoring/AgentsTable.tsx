import { Badge, Card, CardHeader, DataTable, type Column } from '@/components/ui'
import type { MonitoringAgent } from '@/types/api'

import { duration } from './format'

const COLUMNS: Column<MonitoringAgent>[] = [
  { key: 'agent', header: 'Agent', grow: true, cell: (a) => <span className="font-medium">{a.label}</span> },
  { key: 'runs', header: 'Runs', align: 'right', className: 'tabular-nums', cell: (a) => a.runs },
  { key: 'time', header: 'Time', align: 'right', className: 'whitespace-nowrap tabular-nums', cell: (a) => duration(a.total_ms) },
  {
    key: 'share',
    header: 'Share of agent time',
    hideBelow: 'sm',
    className: 'min-w-36',
    cell: (a) => (
      <div className="flex items-center gap-2">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(a.share > 0 ? 2 : 0, Math.round(a.share * 100))}%` }} />
        </div>
        <span className="w-10 text-right text-meta text-muted-foreground tabular-nums">{Math.round(a.share * 100)}%</span>
      </div>
    ),
  },
  {
    key: 'outcome',
    header: 'Outcome',
    align: 'right',
    cell: (a) =>
      a.failures > 0 ? <Badge tone="danger">{a.failures} failed</Badge> : <Badge tone="success">{a.last_outcome === 'success' ? 'Succeeded' : (a.last_outcome ?? 'Done')}</Badge>,
  },
]

/** How long each agent ran. A revised design runs some agents more than once. */
export function AgentsTable({ agents }: { agents: MonitoringAgent[] }) {
  return (
    <Card>
      <CardHeader title="Agents" description="Each agent’s runs and total time. Revisions run the critic and reviser again." />
      <DataTable caption="Agent timings for this job" columns={COLUMNS} rows={agents} getRowKey={(a) => a.node} />
    </Card>
  )
}
