import { Sparkles } from 'lucide-react'

import { Badge, Card, CardHeader, DataTable, EmptyState, type Column } from '@/components/ui'
import type { MonitoringLLMCall } from '@/types/api'
import { formatNumber } from '@/utils/format'

import { clock, EMPTY, shortDuration } from './format'

const tokens = (call: MonitoringLLMCall) =>
  call.input_tokens === null && call.output_tokens === null ? EMPTY : `${formatNumber(call.input_tokens ?? 0)} / ${formatNumber(call.output_tokens ?? 0)}`

const COLUMNS: Column<MonitoringLLMCall>[] = [
  { key: 'time', header: 'Time', className: 'whitespace-nowrap font-mono text-meta text-muted-foreground', cell: (c) => <time dateTime={c.time}>{clock(c.time)}</time> },
  { key: 'agent', header: 'Agent', grow: true, cell: (c) => <span className="font-medium">{c.label ?? c.node ?? EMPTY}</span> },
  {
    key: 'model',
    header: 'Model',
    hideBelow: 'md',
    className: 'font-mono text-meta',
    cell: (c) => (c.model ? `${c.provider ? `${c.provider}/` : ''}${c.model}` : EMPTY),
  },
  { key: 'time_taken', header: 'Took', align: 'right', className: 'whitespace-nowrap tabular-nums', cell: (c) => shortDuration(c.total_ms) },
  { key: 'tokens', header: 'Tokens in / out', align: 'right', hideBelow: 'sm', className: 'whitespace-nowrap tabular-nums', cell: tokens },
  {
    key: 'retries',
    header: 'Retries',
    align: 'right',
    hideBelow: 'md',
    className: 'tabular-nums',
    cell: (c) => (c.rate_limited_responses ? `${c.retries} (rate limited ${c.rate_limited_responses})` : c.retries),
  },
  {
    key: 'outcome',
    header: 'Outcome',
    align: 'right',
    cell: (c) =>
      c.outcome === 'failure' ? (
        <Badge tone="danger">{c.provider_status ? `Failed ${c.provider_status}` : 'Failed'}</Badge>
      ) : (
        <Badge tone="success">Succeeded</Badge>
      ),
  },
]

/** One row per call to the AI provider, with its time, tokens and retries. */
export function LLMCallsTable({ calls }: { calls: MonitoringLLMCall[] }) {
  return (
    <Card>
      <CardHeader title="LLM calls" description="Every call to the AI provider for this job." />
      <DataTable
        caption="LLM calls for this job"
        columns={COLUMNS}
        rows={calls}
        getRowKey={(c) => `${c.time}-${c.node}-${c.total_ms}-${c.input_tokens}`}
        empty={<EmptyState compact icon={Sparkles} title="No LLM calls logged yet" description="They appear here as the agents work." />}
      />
    </Card>
  )
}
