import { ArrowRight, X } from 'lucide-react'
import { useId, useMemo, useState, type KeyboardEvent } from 'react'

import { Badge, Button } from '@/components/ui'
import type { AWSService, DataFlowStep } from '@/types/api'
import { cn } from '@/utils/cn'

import { buildDiagram, connectionsOf, NODE_HEIGHT, NODE_WIDTH, type DiagramEdge } from './diagram-layout'
import { possibleServiceMatches } from './service-matching'

type EdgeState = 'default' | 'highlighted' | 'dimmed'

/** Dimmed edges keep the default stroke; their group is faded instead. */
const EDGE_STROKE: Record<EdgeState, string> = {
  default: 'stroke-muted-foreground/60',
  highlighted: 'stroke-primary',
  dimmed: 'stroke-muted-foreground/60',
}

function StepList({ title, steps, direction }: { title: string; steps: DataFlowStep[]; direction: 'from' | 'to' }) {
  return (
    <div className="min-w-0">
      <h4 className="text-label">{title}</h4>
      {steps.length === 0 ? (
        <p className="mt-1 text-meta text-muted-foreground">None.</p>
      ) : (
        <ul className="mt-1.5 space-y-2">
          {steps.map((step) => (
            <li key={step.step} className="flex gap-2.5">
              <Badge className="mt-px h-5 shrink-0 font-mono">{step.step}</Badge>
              <p className="min-w-0">
                <span className="font-medium">
                  {direction === 'from' ? `from ${step.source}` : `to ${step.destination}`}
                </span>
                <span className="block text-muted-foreground">{step.description}</span>
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SelectionDetails({
  label,
  steps,
  services,
  onClear,
}: {
  label: string
  steps: DataFlowStep[]
  services: AWSService[]
  onClear: () => void
}) {
  const { incoming, outgoing } = connectionsOf(label, steps)
  const matches = possibleServiceMatches(label, services)

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-meta text-muted-foreground">Selected endpoint</p>
          <h3 className="text-card-title break-words">{label}</h3>
        </div>
        <Button variant="ghost" size="sm" onClick={onClear}>
          <X className="size-3.5" aria-hidden="true" />
          Clear selection
        </Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <StepList title={`Incoming steps (${incoming.length})`} steps={incoming} direction="from" />
        <StepList title={`Outgoing steps (${outgoing.length})`} steps={outgoing} direction="to" />
      </div>
      <div>
        <h4 className="text-label">Possible service matches</h4>
        <p className="text-meta text-muted-foreground">
          Matched by name only. The data flow uses free-text labels and does not link to the services list.
        </p>
        {matches.length > 0 ? (
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {matches.map((service) => (
              <li key={service.name}>
                <Badge>Possible match: {service.name}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-meta text-muted-foreground">No service name resembles this label.</p>
        )}
      </div>
    </div>
  )
}

interface DataFlowDiagramProps {
  steps: DataFlowStep[]
  services: AWSService[]
}

/** Interactive diagram of the data-flow steps; endpoints are buttons, steps are numbered arrows. */
export function DataFlowDiagram({ steps, services }: DataFlowDiagramProps) {
  const layout = useMemo(() => buildDiagram(steps), [steps])
  const [selected, setSelected] = useState<string | null>(null)
  const markerBase = `arrow-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`

  const connected = useMemo(() => {
    if (selected === null) return null
    const labels = new Set([selected])
    for (const s of steps) {
      if (s.source === selected) labels.add(s.destination)
      if (s.destination === selected) labels.add(s.source)
    }
    return labels
  }, [selected, steps])

  const edgeState = (edge: DiagramEdge): EdgeState => {
    if (selected === null) return 'default'
    return edge.step.source === selected || edge.step.destination === selected ? 'highlighted' : 'dimmed'
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && selected !== null) {
      event.preventDefault()
      setSelected(null)
    }
  }

  return (
    <div className="space-y-4" onKeyDown={handleKeyDown}>
      {/* Wide diagrams scroll inside this box, never the page. */}
      <div className="overflow-x-auto rounded-md border border-border bg-background">
        <div
          className="relative mx-auto"
          style={{ width: layout.width, height: layout.height }}
          role="group"
          aria-label={`Data-flow diagram: ${layout.nodes.length} endpoints, ${steps.length} steps`}
        >
          <svg
            className="absolute inset-0"
            width={layout.width}
            height={layout.height}
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            aria-hidden="true"
          >
            <defs>
              {(['default', 'highlighted'] as const).map((state) => (
                <marker
                  key={state}
                  id={`${markerBase}-${state}`}
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" className={state === 'highlighted' ? 'fill-primary' : 'fill-muted-foreground'} />
                </marker>
              ))}
            </defs>
            {layout.edges.map((edge) => {
              const state = edgeState(edge)
              return (
                <g
                  key={edge.order}
                  data-edge=""
                  data-step={edge.step.step}
                  data-from={edge.step.source}
                  data-to={edge.step.destination}
                  data-kind={edge.kind}
                  data-state={state}
                  className={cn('transition-opacity motion-reduce:transition-none', state === 'dimmed' && 'opacity-25')}
                >
                  <path
                    d={edge.path}
                    fill="none"
                    strokeWidth={state === 'highlighted' ? 2 : 1.5}
                    className={EDGE_STROKE[state]}
                    markerEnd={`url(#${markerBase}-${state === 'highlighted' ? 'highlighted' : 'default'})`}
                  />
                  <circle
                    cx={edge.labelX}
                    cy={edge.labelY}
                    r={10}
                    strokeWidth={1}
                    className={state === 'highlighted' ? 'fill-primary stroke-primary' : 'fill-surface stroke-border-strong'}
                  />
                  <text
                    x={edge.labelX}
                    y={edge.labelY}
                    textAnchor="middle"
                    dominantBaseline="central"
                    className={cn('font-mono text-[10px] font-semibold', state === 'highlighted' ? 'fill-primary-foreground' : 'fill-foreground')}
                  >
                    {edge.step.step}
                  </text>
                </g>
              )
            })}
          </svg>

          {layout.nodes.map((node) => {
            const isSelected = node.label === selected
            const dimmed = connected !== null && !connected.has(node.label)
            return (
              <button
                key={node.label}
                type="button"
                aria-pressed={isSelected}
                title={node.label}
                onClick={() => setSelected(isSelected ? null : node.label)}
                className={cn(
                  'absolute flex items-center justify-center rounded-md border bg-surface px-2.5 text-center text-label shadow-card transition-[opacity,border-color,background-color] motion-reduce:transition-none',
                  'focus-visible:outline-offset-2',
                  isSelected
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/25'
                    : 'border-border-strong hover:border-primary/60',
                  dimmed && 'opacity-40',
                )}
                style={{ left: node.x, top: node.y, width: NODE_WIDTH, height: NODE_HEIGHT }}
              >
                <span className="line-clamp-2 break-words">{node.label}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div aria-live="polite" className="rounded-md border border-border bg-surface-muted/40 p-4">
        {selected === null ? (
          <p className="flex items-center gap-2 text-muted-foreground">
            <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
            Select an endpoint to see its incoming and outgoing steps. Press Escape to clear.
          </p>
        ) : (
          <SelectionDetails label={selected} steps={steps} services={services} onClear={() => setSelected(null)} />
        )}
      </div>
    </div>
  )
}
