import { ScrollText } from 'lucide-react'
import { useState } from 'react'

import { Badge, Card, CardHeader, EmptyState } from '@/components/ui'
import type { Tone } from '@/components/ui'
import type { MonitoringEvent } from '@/types/api'
import { cn } from '@/utils/cn'

import { clock } from './format'

type LevelFilter = 'all' | 'problems'

const LEVEL_TONE: Record<string, Tone> = { DEBUG: 'neutral', INFO: 'neutral', WARNING: 'warning', ERROR: 'danger', CRITICAL: 'danger' }
const isProblem = (event: MonitoringEvent) => event.level === 'WARNING' || event.level === 'ERROR' || event.level === 'CRITICAL'

const FILTERS: ReadonlyArray<{ id: LevelFilter; label: string }> = [
  { id: 'all', label: 'All events' },
  { id: 'problems', label: 'Warnings and errors' },
]

function Fields({ fields }: { fields: MonitoringEvent['fields'] }) {
  const entries = Object.entries(fields)
  if (entries.length === 0) return null
  return (
    <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-meta text-muted-foreground">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-1">
          <dt>{key}=</dt>
          <dd className="text-foreground">{String(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

/** The job's log events in time order. Only the fields the backend allows are ever shown. */
export function Timeline({ events, truncated }: { events: MonitoringEvent[]; truncated: boolean }) {
  const [filter, setFilter] = useState<LevelFilter>('all')
  const shown = filter === 'problems' ? events.filter(isProblem) : events
  return (
    <Card>
      <CardHeader
        title="Timeline"
        description="Log events for this job from CloudWatch, oldest first."
        action={
          <div role="group" aria-label="Filter events" className="flex gap-1.5">
            {FILTERS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                aria-pressed={filter === id}
                onClick={() => setFilter(id)}
                className={cn(
                  'inline-flex h-control-sm items-center rounded-md border px-2.5 text-meta font-medium transition-colors',
                  filter === id ? 'border-foreground bg-foreground text-background' : 'border-border text-muted-foreground hover:bg-surface-muted hover:text-foreground',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        }
      />
      {shown.length === 0 ? (
        <EmptyState compact icon={ScrollText} title={filter === 'problems' ? 'No warnings or errors' : 'No events'} description={filter === 'problems' ? 'Nothing went wrong in the lines that were read.' : undefined} />
      ) : (
        <ol aria-label="Log events" className="divide-y divide-border">
          {shown.map((event, index) => (
            <li key={`${event.time}-${index}`} className="flex gap-3 px-5 py-3" data-level={event.level}>
              <time dateTime={event.time} className="w-20 shrink-0 pt-0.5 font-mono text-meta text-muted-foreground">
                {clock(event.time)}
              </time>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{event.event}</span>
                  <Badge tone={LEVEL_TONE[event.level] ?? 'neutral'}>{event.level}</Badge>
                  <span className="text-meta text-muted-foreground">{event.service}</span>
                </div>
                <Fields fields={event.fields} />
              </div>
            </li>
          ))}
        </ol>
      )}
      {truncated && <p className="border-t border-border px-5 py-3 text-meta text-muted-foreground">Only the first 500 events are listed. The figures above still count every event.</p>}
    </Card>
  )
}
