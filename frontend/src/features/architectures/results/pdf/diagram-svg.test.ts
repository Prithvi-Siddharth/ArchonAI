/** The vector figures: word wrapping, the data-flow diagram and the services-by-category figure. */
import { describe, expect, it } from 'vitest'

import { REAL_ARCHITECTURE_BACKWARD, REAL_ARCHITECTURE_COMBINED } from '@/test/real-architectures'

import { categoryFigureSvg, escapeXml, flowDiagramSvg, wrapText } from './diagram-svg'
import { ICON_SVGS } from './icon-svgs'

const lookup = (key: string) => ICON_SVGS.get(key)
const parse = (svg: string) => new DOMParser().parseFromString(svg, 'image/svg+xml')

describe('wrapText', () => {
  it('wraps on word boundaries', () => {
    expect(wrapText('Amazon ECS Fargate plus Auto Scaling', 12, 3)).toEqual({ lines: ['Amazon ECS', 'Fargate plus', 'Auto Scaling'], truncated: false })
  })

  it('cuts words longer than a line', () => {
    expect(wrapText('Supercalifragilistic', 8, 3).lines).toEqual(['Supercal', 'ifragili', 'stic'])
  })

  it('marks text it had to leave out', () => {
    const { lines, truncated } = wrapText('one two three four five six seven', 7, 2)
    expect(truncated).toBe(true)
    expect(lines).toHaveLength(2)
    expect(lines[1].endsWith('…')).toBe(true)
  })

  it('handles empty text', () => {
    expect(wrapText('   ', 10, 2)).toEqual({ lines: [], truncated: false })
  })
})

describe('data-flow diagram', () => {
  it('is null when there are no steps (nothing is invented)', () => {
    expect(flowDiagramSvg([], lookup)).toBeNull()
  })

  it('draws one box per component and one numbered arrow per step', () => {
    const steps = REAL_ARCHITECTURE_COMBINED.data_flow
    const flow = flowDiagramSvg(steps, lookup)!
    const doc = parse(flow.svg)
    expect(doc.querySelector('parsererror')).toBeNull()
    const labels = new Set(steps.flatMap((s) => [s.source, s.destination]))
    const boxes = [...doc.documentElement.children].filter((el) => el.tagName === 'rect' && el.getAttribute('width') === '176')
    expect(boxes).toHaveLength(labels.size)
    const arrows = [...doc.querySelectorAll('path[marker-end]')]
    expect(arrows).toHaveLength(steps.length)
    const numbers = [...doc.querySelectorAll('circle + text')].map((t) => t.textContent)
    expect(numbers).toEqual(steps.map((_, i) => String(i + 1)))
  })

  it('uses official icons where a name matches, and a placeholder where none does', () => {
    const flow = flowDiagramSvg(REAL_ARCHITECTURE_COMBINED.data_flow, lookup)!
    expect(flow.icons.map((icon) => icon.key)).toEqual(expect.arrayContaining(['cloudfront', 'waf', 'ecs', 'aurora', 'sqs']))
    expect(flow.unmatched).toEqual(['User browser'])
    expect(flow.svg).toContain('Icon-Architecture-BG/64/') // the official artwork itself is embedded
    expect(flow.svg).toContain('>UB</text>') // the placeholder shows the initials
  })

  it('draws back edges dashed', () => {
    const flow = flowDiagramSvg(REAL_ARCHITECTURE_BACKWARD.data_flow, lookup)!
    expect(flow.hasBackEdges).toBe(true)
    expect(flow.svg).toContain('stroke-dasharray')
  })

  it('escapes text so labels can never break the SVG', () => {
    const flow = flowDiagramSvg([{ step: 1, source: 'Users & <apps>', destination: 'API "v2"', description: 'x' }], lookup)!
    expect(parse(flow.svg).querySelector('parsererror')).toBeNull()
    expect(escapeXml('a & <b> "c"')).toBe('a &amp; &lt;b&gt; &quot;c&quot;')
  })

  it('reports labels it had to shorten (their full text is in the step table)', () => {
    const long = 'A very long component name that keeps going well beyond what three lines in a box can hold at all'
    expect(flowDiagramSvg([{ step: 1, source: long, destination: 'S3', description: '' }], lookup)!.clipped).toEqual([long])
  })
})

describe('services by category', () => {
  it('is null without services', () => {
    expect(categoryFigureSvg([], lookup)).toBeNull()
  })

  it('groups every service under its own category, in first-appearance order', () => {
    const services = REAL_ARCHITECTURE_COMBINED.services
    const figure = categoryFigureSvg(services, lookup, 737)!
    const doc = parse(figure.svg)
    expect(doc.querySelector('parsererror')).toBeNull()
    const headers = [...doc.querySelectorAll('text[font-weight="bold"]')].map((t) => t.textContent ?? '').filter((t) => t.includes('·'))
    const categories = [...new Set(services.map((s) => s.category))]
    expect(headers.map((h) => h.split('·')[0].trim())).toEqual(categories)
    expect(figure.width).toBe(737)
  })
})
