/**
 * Vector SVG figures for the PDF, drawn only from the saved result:
 *
 * - the data-flow diagram, laid out by the same `buildDiagram()` the Architecture tab uses (one node
 *   per source/destination label, one numbered arrow per step, back edges dashed under the nodes);
 * - a "services by category" figure from `architecture.services`.
 *
 * Nodes carry the official AWS icons their name matches (see aws-icons.ts); a label with no match
 * gets a neutral placeholder showing its initials, never a guessed icon. Nothing is added that the
 * data does not contain: no VPCs, availability zones or subnets, because the result has none.
 */
import type { AWSService, DataFlowStep } from '@/types/api'

import { buildDiagram, NODE_HEIGHT, NODE_WIDTH } from '../architecture/diagram-layout'
import { iconsFor, type AwsIcon } from './aws-icons'
import { PALETTE } from './palette'

/** Returns an icon's SVG text by key, or undefined when the file is missing. */
export type IconLookup = (key: string) => string | undefined

export function escapeXml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/**
 * Greedy word wrap to at most `maxLines` lines of about `maxChars` characters. Words longer than a
 * line are cut. When text is left out the last line ends with "…" and `truncated` is true (the full
 * text is always printed in a table as well).
 */
export function wrapText(text: string, maxChars: number, maxLines: number): { lines: string[]; truncated: boolean } {
  const all: string[] = []
  let current = ''
  for (let word of text.replace(/\s+/g, ' ').trim().split(' ').filter(Boolean)) {
    while (word.length > maxChars) {
      if (current) {
        all.push(current)
        current = ''
      }
      all.push(word.slice(0, maxChars))
      word = word.slice(maxChars)
    }
    if (!word) continue
    if (!current) current = word
    else if (current.length + 1 + word.length <= maxChars) current = `${current} ${word}`
    else {
      all.push(current)
      current = word
    }
  }
  if (current) all.push(current)
  if (all.length <= maxLines) return { lines: all, truncated: false }
  const lines = all.slice(0, maxLines)
  const last = lines[maxLines - 1]
  lines[maxLines - 1] = `${last.length >= maxChars ? last.slice(0, maxChars - 1) : last}…`
  return { lines, truncated: true }
}

/** Place an official icon (a whole <svg> document) at x, y, scaled to `size`, keeping its proportions. */
export function placeIcon(iconSvg: string, x: number, y: number, size: number): string {
  const inner = iconSvg.replace(/<\?xml[^>]*>/, '').trim()
  const viewBox = /viewBox="([^"]+)"/.exec(inner)?.[1] ?? '0 0 80 80'
  const body = inner.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '')
  return `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="${viewBox}" preserveAspectRatio="xMidYMid meet">${body}</svg>`
}

/** The consistent stand-in for a component with no matching AWS icon: a grey tile with its initials. */
export function placeholderIcon(label: string, x: number, y: number, size: number): string {
  const initials =
    label
      .replace(/[^A-Za-z0-9 ]+/g, ' ')
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((word) => word[0].toUpperCase())
      .join('') || '?'
  return (
    `<rect x="${x}" y="${y}" width="${size}" height="${size}" rx="${size * 0.12}" fill="${PALETTE.placeholder}"/>` +
    `<text x="${x + size / 2}" y="${y + size / 2 + size * 0.14}" font-size="${size * 0.38}" font-weight="bold" fill="#FFFFFF" text-anchor="middle">${escapeXml(initials)}</text>`
  )
}

/** Up to `max` icons for a name, side by side starting at x; returns the SVG and the width used. */
function iconRow(name: string, icons: AwsIcon[], lookup: IconLookup, x: number, y: number, size: number, gap: number): { svg: string; width: number; matched: AwsIcon[] } {
  const usable = icons.filter((icon) => lookup(icon.key))
  if (usable.length === 0) return { svg: placeholderIcon(name, x, y, size), width: size, matched: [] }
  const svg = usable.map((icon, i) => placeIcon(lookup(icon.key)!, x + i * (size + gap), y, size)).join('')
  return { svg, width: usable.length * size + (usable.length - 1) * gap, matched: usable }
}

const ARROW_DEFS =
  '<defs>' +
  `<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${PALETTE.edge}"/></marker>` +
  '</defs>'

export interface FlowDiagram {
  svg: string
  width: number
  height: number
  /** Distinct icons drawn, for the legend. */
  icons: AwsIcon[]
  /** Labels drawn with the placeholder because no icon matched. */
  unmatched: string[]
  /** Labels whose text did not fit in the box (shown in full in the step table). */
  clipped: string[]
  hasBackEdges: boolean
}

/** The data-flow diagram. Returns null when there are no steps (nothing to draw). */
export function flowDiagramSvg(steps: DataFlowStep[], lookup: IconLookup): FlowDiagram | null {
  if (steps.length === 0) return null
  const layout = buildDiagram(steps)
  const icons = new Map<string, AwsIcon>()
  const unmatched: string[] = []
  const clipped: string[] = []

  const edges = layout.edges
    .map((edge) => {
      const dash = edge.kind === 'back' ? ' stroke-dasharray="5 3"' : ''
      return `<path d="${edge.path}" fill="none" stroke="${PALETTE.edge}" stroke-width="1.3"${dash} marker-end="url(#arrow)"/>`
    })
    .join('')

  const nodes = layout.nodes
    .map((node) => {
      const found = iconsFor(node.label, 3)
      const size = found.length <= 1 ? 30 : found.length === 2 ? 22 : 17
      const row = iconRow(node.label, found, lookup, node.x + 9, node.y + (NODE_HEIGHT - size) / 2, size, 3)
      row.matched.forEach((icon) => icons.set(icon.key, icon))
      if (row.matched.length === 0) unmatched.push(node.label)
      const textX = node.x + 9 + row.width + 8
      const maxChars = Math.max(8, Math.floor((node.x + NODE_WIDTH - 8 - textX) / (9 * 0.52)))
      const { lines, truncated } = wrapText(node.label, maxChars, 3)
      if (truncated) clipped.push(node.label)
      const lineHeight = 11
      const firstY = node.y + NODE_HEIGHT / 2 - ((lines.length - 1) * lineHeight) / 2 + 3
      const text = lines
        .map((line, i) => `<text x="${textX}" y="${firstY + i * lineHeight}" font-size="9" fill="${PALETTE.ink}">${escapeXml(line)}</text>`)
        .join('')
      return (
        `<rect x="${node.x}" y="${node.y}" width="${NODE_WIDTH}" height="${NODE_HEIGHT}" rx="8" fill="#FFFFFF" stroke="${PALETTE.nodeBorder}" stroke-width="1"/>` +
        row.svg +
        text
      )
    })
    .join('')

  // Step numbers on top of everything, so arrows never hide them.
  const badges = layout.edges
    .map(
      (edge) =>
        `<circle cx="${edge.labelX}" cy="${edge.labelY}" r="8" fill="${PALETTE.ink}"/>` +
        `<text x="${edge.labelX}" y="${edge.labelY + 3}" font-size="7.5" font-weight="bold" fill="#FFFFFF" text-anchor="middle">${edge.order + 1}</text>`,
    )
    .join('')

  return {
    svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${layout.width}" height="${layout.height}" viewBox="0 0 ${layout.width} ${layout.height}">${ARROW_DEFS}${edges}${nodes}${badges}</svg>`,
    width: layout.width,
    height: layout.height,
    icons: [...icons.values()],
    unmatched,
    clipped,
    hasBackEdges: layout.edges.some((edge) => edge.kind === 'back'),
  }
}

export interface CategoryFigure {
  svg: string
  width: number
  height: number
}

/**
 * Services grouped by their own category, in the order categories first appear, laid out as cards
 * in columns (each card goes to the shortest column). Null when there are no services.
 */
export function categoryFigureSvg(services: AWSService[], lookup: IconLookup, width = 495): CategoryFigure | null {
  if (services.length === 0) return null
  const groups = new Map<string, AWSService[]>()
  for (const service of services) {
    const category = (service.category ?? '').trim() || 'Uncategorised'
    groups.set(category, [...(groups.get(category) ?? []), service])
  }
  const groupColumns = width >= 600 ? 3 : 2
  const columnGap = 12
  const groupW = (width - columnGap * (groupColumns - 1)) / groupColumns
  const tileColumns = groupW >= 330 ? 2 : 1
  const pad = 8
  const gap = 6
  const tileW = (groupW - pad * 2 - gap * (tileColumns - 1)) / tileColumns
  const tileH = 40
  const heights = Array.from({ length: groupColumns }, () => 0)
  let svg = ''
  for (const [category, members] of groups) {
    const rows = Math.ceil(members.length / tileColumns)
    const boxH = 24 + rows * tileH + (rows - 1) * gap + pad
    const column = heights.indexOf(Math.min(...heights))
    const x = column * (groupW + columnGap)
    const y = heights[column]
    svg += `<rect x="${x + 0.5}" y="${y + 0.5}" width="${groupW - 1}" height="${boxH}" rx="8" fill="${PALETTE.soft}" stroke="${PALETTE.border}"/>`
    svg += `<text x="${x + pad}" y="${y + 16}" font-size="9" font-weight="bold" fill="${PALETTE.ink}">${escapeXml(category)}  ·  ${members.length}</text>`
    members.forEach((service, i) => {
      const tx = x + pad + (i % tileColumns) * (tileW + gap)
      const ty = y + 24 + Math.floor(i / tileColumns) * (tileH + gap)
      const found = iconsFor(service.name ?? '', 3)
      const size = found.length <= 1 ? 24 : found.length === 2 ? 18 : 14
      const row = iconRow(service.name ?? '', found, lookup, tx + 7, ty + (tileH - size) / 2, size, 2)
      const textX = tx + 7 + row.width + 7
      const maxChars = Math.max(6, Math.floor((tx + tileW - 6 - textX) / (8.5 * 0.52)))
      const { lines } = wrapText(service.name ?? '', maxChars, 3)
      const firstY = ty + tileH / 2 - ((lines.length - 1) * 10) / 2 + 3
      svg += `<rect x="${tx}" y="${ty}" width="${tileW}" height="${tileH}" rx="6" fill="#FFFFFF" stroke="${PALETTE.nodeBorder}"/>`
      svg += row.svg
      svg += lines.map((line, j) => `<text x="${textX}" y="${firstY + j * 10}" font-size="8.5" fill="${PALETTE.ink}">${escapeXml(line)}</text>`).join('')
    })
    heights[column] += boxH + 10
  }
  const height = Math.max(1, Math.max(...heights) - 10)
  return { svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${svg}</svg>`, width, height }
}
