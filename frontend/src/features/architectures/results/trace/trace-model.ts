import type { ArchitectureResult, TraceEntry } from '@/types/api'

/** One trace entry made safe to display, with its position in the array the backend returned. */
export interface TraceStep {
  /** 1-based position in the returned array: the execution order. */
  seq: number
  node: string
  action: string
  summary: string
  /** A whole number >= 0, or null when the value is missing or unexpected. */
  iteration: number | null
  /** What the backend sent, for display when the iteration is unexpected. */
  rawIteration: string
  /** This node's 1-based occurrence in the trace, and how many times it occurs in total. */
  run: number
  runs: number
}

/** Consecutive steps that share an iteration value. Groups never reorder steps. */
export interface TraceGroup {
  iteration: number | null
  rawIteration: string
  steps: TraceStep[]
}

export interface TraceSummary {
  steps: TraceStep[]
  groups: TraceGroup[]
  distinctNodes: number
  /** Distinct valid iteration values, ascending. */
  iterations: number[]
  /** Distinct valid iteration values above 0. */
  revisionRounds: number[]
  /** True if any step has a missing or unexpected iteration value. */
  hasUnexpectedIteration: boolean
  /** Nodes that occur more than once, in order of first occurrence. */
  repeated: Array<{ node: string; runs: number }>
}

const text = (value: unknown) => (typeof value === 'string' ? value.replace(/\r\n?/g, '\n').trim() : '')

function readIteration(value: unknown): { iteration: number | null; rawIteration: string } {
  if (typeof value === 'number' && Number.isInteger(value) && value >= 0) return { iteration: value, rawIteration: String(value) }
  return { iteration: null, rawIteration: value === undefined || value === null ? '' : String(value).slice(0, 40) }
}

/**
 * The trace exactly in the order returned, never re-sorted by a presumed workflow sequence.
 * Anything malformed (absent array, non-object entry, missing field) becomes a blank value.
 */
export function readTrace(result: ArchitectureResult): TraceSummary {
  // Widened on purpose: a stored result could lack the trace even though the type says otherwise.
  const raw: unknown = (result as { execution_trace?: unknown }).execution_trace
  const entries: Array<Partial<TraceEntry>> = Array.isArray(raw) ? raw.map((e) => (e && typeof e === 'object' ? (e as Partial<TraceEntry>) : {})) : []

  const totals = new Map<string, number>()
  for (const entry of entries) {
    const node = text(entry.node)
    if (node) totals.set(node, (totals.get(node) ?? 0) + 1)
  }

  const seen = new Map<string, number>()
  const steps = entries.map((entry, index): TraceStep => {
    const node = text(entry.node)
    const run = node ? (seen.get(node) ?? 0) + 1 : 1
    if (node) seen.set(node, run)
    return {
      seq: index + 1,
      node,
      action: text(entry.action),
      summary: text(entry.output_summary),
      ...readIteration(entry.iteration),
      run,
      runs: node ? (totals.get(node) ?? 1) : 1,
    }
  })

  const groups: TraceGroup[] = []
  for (const step of steps) {
    const last = groups.at(-1)
    if (last && last.iteration === step.iteration && last.rawIteration === step.rawIteration) last.steps.push(step)
    else groups.push({ iteration: step.iteration, rawIteration: step.rawIteration, steps: [step] })
  }

  const iterations = [...new Set(steps.flatMap((s) => (s.iteration === null ? [] : [s.iteration])))].sort((a, b) => a - b)
  return {
    steps,
    groups,
    distinctNodes: totals.size,
    iterations,
    revisionRounds: iterations.filter((i) => i > 0),
    hasUnexpectedIteration: steps.some((s) => s.iteration === null),
    repeated: [...totals].filter(([, runs]) => runs > 1).map(([node, runs]) => ({ node, runs })),
  }
}

/** "Iteration 2", or a clear label for a missing or unexpected value. */
export function iterationLabel(iteration: number | null, rawIteration: string): string {
  if (iteration !== null) return `Iteration ${iteration}`
  return rawIteration ? `Unexpected iteration "${rawIteration}"` : 'Iteration not recorded'
}

/** What an iteration value records: the workflow's revision count when the step ran. */
export function iterationMeaning(iteration: number | null): string {
  if (iteration === null) return 'The backend did not send a valid iteration number for these steps.'
  return iteration === 0 ? 'Recorded before any revision (revision count 0).' : `Recorded with the revision count at ${iteration}.`
}
