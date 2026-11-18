import { ListOrdered, Repeat } from 'lucide-react'

import { Badge, Card, CardContent, CardHeader, EmptyState } from '@/components/ui'
import type { Tone } from '@/components/ui/tones'
import type { ArchitectureResult } from '@/types/api'
import { cn } from '@/utils/cn'

import { iterationLabel, iterationMeaning, readTrace, type TraceGroup, type TraceStep } from './trace-model'

/** Iteration 0 is neutral, revision rounds are blue, missing or unexpected values amber. */
const toneOf = (iteration: number | null): Tone => (iteration === null ? 'warning' : iteration === 0 ? 'neutral' : 'info')

const MARKER: Record<Tone, string> = {
  neutral: 'border-border bg-surface-muted text-foreground',
  info: 'border-info/40 bg-info/10 text-info',
  warning: 'border-warning/40 bg-warning/10 text-warning',
  success: 'border-success/40 bg-success/10 text-success',
  danger: 'border-danger/40 bg-danger/10 text-danger',
}

const ACCENT: Record<Tone, string> = {
  neutral: '',
  info: 'border-l-4 border-l-info/60',
  warning: 'border-l-4 border-l-warning/60',
  success: 'border-l-4 border-l-success/60',
  danger: 'border-l-4 border-l-danger/60',
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

function Step({ step, last }: { step: TraceStep; last: boolean }) {
  const tone = toneOf(step.iteration)
  return (
    <li className={cn('relative pl-11', !last && 'pb-6')} data-seq={step.seq} data-iteration={step.rawIteration}>
      {/* Connector to the next step: order only, not time. */}
      {!last && <span className="absolute top-8 bottom-0 left-[0.9375rem] w-px bg-border" aria-hidden="true" />}
      <span
        className={cn('absolute top-0 left-0 flex size-8 items-center justify-center rounded-full border text-meta font-medium tabular-nums', MARKER[tone])}
        aria-hidden="true"
      >
        {step.seq}
      </span>
      <div className="min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 pt-1">
          <h3 className="text-label break-words">
            <span className="sr-only">Step {step.seq}: </span>
            {step.node || <span className="text-muted-foreground italic">Unnamed step</span>}
          </h3>
          {step.runs > 1 && (
            <Badge tone="neutral" data-repeat={`${step.run}/${step.runs}`}>
              <Repeat className="size-3" aria-hidden="true" />
              Run {step.run} of {step.runs}
            </Badge>
          )}
          <Badge tone={tone}>{iterationLabel(step.iteration, step.rawIteration)}</Badge>
        </div>
        {step.action ? (
          <p className="break-words text-muted-foreground">{step.action}</p>
        ) : (
          <p className="text-muted-foreground italic">No action recorded.</p>
        )}
        <div className="rounded-md bg-surface-muted px-3 py-2">
          <p className="text-overline text-muted-foreground uppercase">Output summary</p>
          {step.summary ? (
            <p className="mt-0.5 leading-6 break-words whitespace-pre-line">{step.summary}</p>
          ) : (
            <p className="mt-0.5 text-muted-foreground italic">No output summary recorded.</p>
          )}
        </div>
      </div>
    </li>
  )
}

function Timeline({ steps, label }: { steps: TraceStep[]; label: string }) {
  return (
    <ol start={steps[0]?.seq} aria-label={label}>
      {steps.map((step, index) => (
        <Step key={step.seq} step={step} last={index === steps.length - 1} />
      ))}
    </ol>
  )
}

function GroupCard({ group, single }: { group: TraceGroup; single: boolean }) {
  const label = iterationLabel(group.iteration, group.rawIteration)
  const first = group.steps[0].seq
  const last = group.steps.at(-1)?.seq ?? first
  return (
    <Card className={cn('min-w-0', !single && ACCENT[toneOf(group.iteration)])} data-group={group.rawIteration}>
      <CardHeader
        title={single ? 'Timeline' : label}
        description={`${iterationMeaning(group.iteration)} ${first === last ? `Step ${first}.` : `Steps ${first}–${last}.`}`}
        action={<Badge tone={toneOf(group.iteration)}>{single ? label : plural(group.steps.length, 'step')}</Badge>}
      />
      <CardContent className="py-5">
        <Timeline steps={group.steps} label={single ? 'Execution steps' : `${label} steps`} />
      </CardContent>
    </Card>
  )
}

export function TraceTab({ result }: { result: ArchitectureResult }) {
  const trace = readTrace(result)

  if (trace.steps.length === 0) {
    return (
      <Card>
        <EmptyState icon={ListOrdered} title="No execution trace" description="This result contains no recorded workflow steps." />
      </Card>
    )
  }

  const single = trace.groups.length === 1
  const rounds = trace.revisionRounds

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Execution trace"
          description="Every workflow step in the order the backend recorded it. The trace has no timestamps or durations."
        />
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-3 gap-4">
            <div>
              <dt className="text-meta text-muted-foreground">Steps</dt>
              <dd className="text-stat tabular-nums">{trace.steps.length}</dd>
            </div>
            <div>
              <dt className="text-meta text-muted-foreground">Distinct nodes</dt>
              <dd className="text-stat tabular-nums">{trace.distinctNodes}</dd>
            </div>
            <div>
              <dt className="text-meta text-muted-foreground">Revision rounds</dt>
              <dd className="text-stat tabular-nums">{rounds.length}</dd>
            </div>
          </dl>
          <p className="text-meta text-muted-foreground">
            {trace.iterations.length > 0 && `Iteration values in the trace: ${trace.iterations.join(', ')}. Revision rounds count the values above 0. `}
            {trace.hasUnexpectedIteration && 'Some steps have no valid iteration value. '}
            Steps from a parallel stage appear in the order they were recorded.
          </p>
          {trace.repeated.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5" aria-label="Repeated nodes" role="group">
              <span className="mr-1 text-meta text-muted-foreground">Repeated nodes:</span>
              {trace.repeated.map(({ node, runs }) => (
                <Badge key={node}>
                  <Repeat className="size-3" aria-hidden="true" />
                  {node} ×{runs}
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {trace.groups.map((group) => (
        <GroupCard key={group.steps[0].seq} group={group} single={single} />
      ))}
    </div>
  )
}
