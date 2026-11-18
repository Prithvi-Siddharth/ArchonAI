/**
 * Layout for the data-flow diagram, built only from `architecture.data_flow`.
 *
 * Nodes are the unique source/destination labels (exact text, first-appearance
 * order). Edges are the steps, one per step, in backend order. A step whose
 * destination first appeared before its source is drawn as a "back" edge (an
 * arc under the diagram), so the left-to-right layout never needs a cycle.
 * Nothing is added: no extra nodes, edges, or service relationships.
 */
import type { DataFlowStep } from '@/types/api'

export const NODE_WIDTH = 176
export const NODE_HEIGHT = 56
const GAP_X = 72
const GAP_Y = 28
const PAD = 24
const SELF_LOOP_SPACE = 36
const BACK_EDGE_SPACING = 26
/** Vertical spread between repeated steps that join the same two endpoints. */
const PARALLEL_OFFSET = 8

export interface DiagramNode {
  /** The label exactly as the backend wrote it (also the node's identity). */
  label: string
  /** First-appearance order. */
  index: number
  column: number
  x: number
  y: number
}

export type EdgeKind = 'forward' | 'back' | 'self'

export interface DiagramEdge {
  step: DataFlowStep
  /** Position in the backend's data_flow array. */
  order: number
  kind: EdgeKind
  /** SVG path data. */
  path: string
  /** Where the step-number label sits. */
  labelX: number
  labelY: number
}

export interface DiagramLayout {
  nodes: DiagramNode[]
  edges: DiagramEdge[]
  width: number
  height: number
}

export function buildDiagram(steps: DataFlowStep[]): DiagramLayout {
  // 1. Nodes: unique labels in the order they first appear.
  const order = new Map<string, number>()
  for (const step of steps) {
    for (const label of [step.source, step.destination]) {
      if (!order.has(label)) order.set(label, order.size)
    }
  }
  const labels = [...order.keys()]

  // 2. Columns: longest path over forward steps (source seen before destination).
  //    First-appearance order is a topological order of these steps, so one pass suffices.
  const column = new Map(labels.map((label) => [label, 0]))
  const forward = steps
    .filter((s) => order.get(s.destination)! > order.get(s.source)!)
    .sort((a, b) => order.get(a.source)! - order.get(b.source)!)
  for (const step of forward) {
    column.set(step.destination, Math.max(column.get(step.destination)!, column.get(step.source)! + 1))
  }

  // 3. Rows: within a column, first-appearance order; columns are centred vertically.
  const columns = new Map<number, string[]>()
  for (const label of labels) {
    const c = column.get(label)!
    columns.set(c, [...(columns.get(c) ?? []), label])
  }
  const maxRows = Math.max(1, ...[...columns.values()].map((col) => col.length))
  const columnCount = Math.max(1, ...[...columns.keys()].map((c) => c + 1))
  const hasSelfLoop = steps.some((s) => s.source === s.destination)
  const top = PAD + (hasSelfLoop ? SELF_LOOP_SPACE : 0)
  const bandHeight = maxRows * NODE_HEIGHT + (maxRows - 1) * GAP_Y

  const nodes: DiagramNode[] = labels.map((label) => {
    const c = column.get(label)!
    const members = columns.get(c)!
    const row = members.indexOf(label)
    const columnHeight = members.length * NODE_HEIGHT + (members.length - 1) * GAP_Y
    return {
      label,
      index: order.get(label)!,
      column: c,
      x: PAD + c * (NODE_WIDTH + GAP_X),
      y: top + (bandHeight - columnHeight) / 2 + row * (NODE_HEIGHT + GAP_Y),
    }
  })
  const byLabel = new Map(nodes.map((node) => [node.label, node]))

  // 4. Edges.
  const pairCount = new Map<string, number>()
  const pairSeen = new Map<string, number>()
  for (const s of steps) {
    const key = `${s.source}\u0000${s.destination}`
    pairCount.set(key, (pairCount.get(key) ?? 0) + 1)
  }
  const nodesBottom = top + bandHeight
  let backEdges = 0

  const edges: DiagramEdge[] = steps.map((step, index) => {
    const from = byLabel.get(step.source)!
    const to = byLabel.get(step.destination)!
    const key = `${step.source}\u0000${step.destination}`
    const nth = pairSeen.get(key) ?? 0
    pairSeen.set(key, nth + 1)
    const offset = (nth - (pairCount.get(key)! - 1) / 2) * PARALLEL_OFFSET

    if (from === to) {
      const left = from.x + NODE_WIDTH * 0.35
      const right = from.x + NODE_WIDTH * 0.65
      const lift = from.y - 30 - Math.abs(offset)
      return {
        step,
        order: index,
        kind: 'self',
        path: `M ${right} ${from.y} C ${right} ${lift}, ${left} ${lift}, ${left} ${from.y}`,
        labelX: from.x + NODE_WIDTH / 2,
        labelY: lift + 8,
      }
    }

    if (to.index < from.index) {
      // Back edge: down from the source, along under all nodes, up into the destination.
      backEdges += 1
      const depth = nodesBottom + BACK_EDGE_SPACING * backEdges
      const sx = from.x + NODE_WIDTH / 2 + offset
      const tx = to.x + NODE_WIDTH / 2 + offset
      const sy = from.y + NODE_HEIGHT
      const ty = to.y + NODE_HEIGHT
      const r = 10
      const dir = tx < sx ? -1 : 1
      return {
        step,
        order: index,
        kind: 'back',
        path: `M ${sx} ${sy} L ${sx} ${depth - r} Q ${sx} ${depth} ${sx + dir * r} ${depth} L ${tx - dir * r} ${depth} Q ${tx} ${depth} ${tx} ${depth - r} L ${tx} ${ty}`,
        labelX: (sx + tx) / 2,
        labelY: depth,
      }
    }

    // Forward edge: right side of the source to the left side of the destination.
    const sx = from.x + NODE_WIDTH
    const sy = from.y + NODE_HEIGHT / 2 + offset
    const tx = to.x
    const ty = to.y + NODE_HEIGHT / 2 + offset
    const bend = Math.max(24, (tx - sx) / 2)
    return {
      step,
      order: index,
      kind: 'forward',
      path: `M ${sx} ${sy} C ${sx + bend} ${sy}, ${tx - bend} ${ty}, ${tx} ${ty}`,
      labelX: (sx + tx) / 2,
      labelY: (sy + ty) / 2,
    }
  })

  return {
    nodes,
    edges,
    width: PAD * 2 + columnCount * NODE_WIDTH + (columnCount - 1) * GAP_X,
    height: nodesBottom + (backEdges > 0 ? BACK_EDGE_SPACING * backEdges + 12 : 0) + PAD,
  }
}

/** The steps that enter and leave a node, in backend order. */
export function connectionsOf(label: string, steps: DataFlowStep[]) {
  return {
    incoming: steps.filter((s) => s.destination === label),
    outgoing: steps.filter((s) => s.source === label),
  }
}
