/**
 * The PDF report as a pdfmake document definition, built only from the saved job result. Pure: no
 * network, no LLM, no browser APIs, so it can be tested directly.
 *
 * Every value is read defensively (a stored result can be older or partial); anything missing is
 * printed as "Not provided" instead of being guessed. Facts the result does not contain (VPC or
 * subnet layout, per-service configuration, dollar figures per service, trace timestamps) are
 * stated as absent, never invented.
 */
import type { Content, ContentTable, TableCell, TDocumentDefinitions } from 'pdfmake/interfaces'

import type { AnalysisResult, ArchitectureResult, AWSService, CriticIssue, DataFlowStep, Severity, ValidationIssue } from '@/types/api'

import { possibleServiceMatches } from '../architecture/service-matching'
import { costLevel } from '../cost/cost-levels'
import { REPORT_SECTIONS } from '../report/report-content'
import { PLAN_AREAS, REQUIREMENT_ROWS, TRAFFIC_PATTERN_LABEL } from '../result-format'
import { iterationLabel, readTrace } from '../trace/trace-model'
import { iconsFor } from './aws-icons'
import { categoryFigureSvg, flowDiagramSvg, placeIcon, placeholderIcon, type IconLookup } from './diagram-svg'
import { PALETTE } from './palette'

export interface ReportInput {
  result: ArchitectureResult
  jobId: string
  /** The request as submitted (from the job, not the result). */
  request: string | null
  createdAt?: string | null
  finishedAt?: string | null
  generatedAt: Date
  appVersion: string
  icons: IconLookup
}

// --- Safe readers --------------------------------------------------------------------------------

type Loose = Record<string, unknown>
const obj = (value: unknown): Loose => (value && typeof value === 'object' && !Array.isArray(value) ? (value as Loose) : {})
const str = (value: unknown): string => (typeof value === 'string' ? value.replace(/\r\n?/g, '\n').trim() : '')
const strs = (value: unknown): string[] => (Array.isArray(value) ? value.map(str).filter(Boolean) : [])
const arr = <T>(value: unknown): T[] => (Array.isArray(value) ? (value.filter((v) => v && typeof v === 'object') as T[]) : [])
const num = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null)
const bool = (value: unknown): boolean | null => (typeof value === 'boolean' ? value : null)

const NOT_PROVIDED = 'Not provided in the generated result.'

export const titleCase = (text: string) => text.replace(/(^|\s)(\S)/g, (_, space: string, ch: string) => space + ch.toUpperCase())

/** The architecture's display name: its application type, the only name-like field in the result. */
export function projectName(result: ArchitectureResult): string {
  const type = str(obj(obj(result).requirements).application_type)
  return type ? titleCase(type) : 'AWS Architecture'
}

const formatDate = (iso: string | null | undefined) => {
  if (!iso) return 'Not recorded'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString('en-GB', { dateStyle: 'long', timeStyle: 'short', timeZone: 'UTC' }) + ' UTC'
}

// --- Building blocks -----------------------------------------------------------------------------

const SEVERITY_COLOR: Record<string, string> = { critical: PALETTE.danger, high: PALETTE.danger, medium: PALETTE.warning, low: PALETTE.muted }
const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }

function sectionHeading(number: number, title: string, id: string, extra: Partial<Record<'pageOrientation', 'landscape' | 'portrait'>> = {}): Content {
  return {
    stack: [
      { text: `${number}. ${title}`, style: 'h1', tocItem: true, id, tocStyle: { color: PALETTE.ink }, tocMargin: [0, 3, 0, 0] },
      { canvas: [{ type: 'rect', x: 0, y: 2, w: 46, h: 3, color: PALETTE.orange }], margin: [0, 0, 0, 14] },
    ],
    pageBreak: 'before',
    ...extra,
  } as Content
}

const h2 = (text: string): Content => ({ text, style: 'h2', headlineLevel: 2 })
const h3 = (text: string): Content => ({ text, style: 'h3', headlineLevel: 3 })
const para = (text: string, fallback = NOT_PROVIDED): Content =>
  text ? { text, style: 'body' } : { text: fallback, style: 'muted', italics: true, margin: [0, 0, 0, 8] }
const note = (text: string): Content => ({ text, style: 'note' })

function bullets(items: string[], fallback = 'None listed in the generated result.'): Content {
  if (items.length === 0) return { text: fallback, style: 'muted', italics: true, margin: [0, 0, 0, 8] }
  return { ul: items.map((item) => ({ text: item, margin: [0, 0, 0, 3] })), style: 'body', markerColor: PALETTE.orange } as Content
}

function numbered(items: string[], fallback = 'None listed in the generated result.'): Content {
  if (items.length === 0) return { text: fallback, style: 'muted', italics: true, margin: [0, 0, 0, 8] }
  return { ol: items.map((item) => ({ text: item, margin: [0, 0, 0, 3] })), style: 'body' } as Content
}

const TABLE_LAYOUT = {
  hLineWidth: (i: number, node: ContentTable) => (i === 0 || i === node.table.body.length ? 0.8 : 0.5),
  vLineWidth: () => 0,
  hLineColor: () => PALETTE.border,
  fillColor: (row: number, node: ContentTable) => (row === 0 && (node.table.headerRows ?? 0) > 0 ? PALETTE.soft : null),
  paddingLeft: () => 6,
  paddingRight: () => 6,
  paddingTop: () => 5,
  paddingBottom: () => 5,
}

/** A table with a repeating header row. Rows may split across pages only when `splitRows` is set. */
function table(headers: string[], rows: TableCell[][], widths: Array<number | string>, splitRows = false): Content {
  return {
    table: {
      headerRows: 1,
      dontBreakRows: !splitRows,
      widths,
      body: [headers.map((h) => ({ text: h, style: 'th' })), ...rows],
    },
    layout: TABLE_LAYOUT,
    style: 'table',
  } as Content
}

/** Label/value rows without a header. */
function facts(rows: Array<[string, string | Content]>): Content {
  return {
    table: {
      widths: [132, '*'],
      dontBreakRows: true,
      body: rows.map(([label, value]) => [
        { text: label, style: 'factLabel' },
        typeof value === 'string' ? { text: value || 'Not provided', style: value ? 'td' : 'mutedTd' } : value,
      ]),
    },
    layout: { ...TABLE_LAYOUT, fillColor: () => null },
    style: 'table',
  } as Content
}

function callout(text: string, color: string, title?: string): Content {
  return {
    table: {
      widths: [3, '*'],
      body: [[{ text: '', fillColor: color }, { stack: [...(title ? [{ text: title, bold: true, color, margin: [0, 0, 0, 2] }] : []), { text, style: 'body', margin: [0, 0, 0, 0] }], fillColor: PALETTE.soft }]],
    },
    layout: { hLineWidth: () => 0, vLineWidth: () => 0, paddingLeft: (i: number) => (i === 0 ? 0 : 9), paddingRight: () => 8, paddingTop: () => 7, paddingBottom: () => 7 },
    margin: [0, 2, 0, 12],
    unbreakable: true,
  } as Content
}

const severityCell = (severity: Severity | string): TableCell => ({ text: str(severity).toUpperCase() || '—', bold: true, fontSize: 7.5, color: SEVERITY_COLOR[str(severity)] ?? PALETTE.muted })

/** A row of official icons for a name (or the neutral placeholder), as a small SVG for tables and cards. */
function iconStrip(name: string, icons: IconLookup, size: number, max = 3): Content {
  const matched = iconsFor(name, max).filter((icon) => icons(icon.key))
  const count = Math.max(1, matched.length)
  const width = count * size + (count - 1) * 3
  const body = matched.length ? matched.map((icon, i) => placeIcon(icons(icon.key)!, i * (size + 3), 0, size)).join('') : placeholderIcon(name, 0, 0, size)
  return { svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${size}" viewBox="0 0 ${width} ${size}">${body}</svg>`, width }
}

function analysisBlock(analysis: AnalysisResult | undefined, title: string): Content[] {
  const a = obj(analysis)
  if (Object.keys(a).length === 0) return [h2(title), para('', 'This specialist analysis is not in the generated result.')]
  return [
    h2(title),
    h3('Recommendations'),
    numbered(strs(a.recommendations)),
    h3('Reasoning'),
    para(str(a.reasoning)),
    h3('Risks'),
    bullets(strs(a.risks), 'No risks listed by this specialist.'),
  ]
}

function issuesTable(issues: CriticIssue[]): Content {
  const sorted = [...issues].sort((x, y) => (SEVERITY_ORDER[x.severity] ?? 9) - (SEVERITY_ORDER[y.severity] ?? 9))
  return table(
    ['Severity', 'Category', 'Issue'],
    sorted.map((issue) => [severityCell(issue.severity), { text: titleCase(str(issue.category)) || '—', style: 'td' }, { text: str(issue.issue) || '—', style: 'td' }]),
    [58, 80, '*'],
    true,
  )
}

/** Critic issues whose category matches any of the words (e.g. "security"). */
const issuesAbout = (issues: CriticIssue[], words: string[]) => issues.filter((issue) => words.some((word) => str(issue.category).toLowerCase().includes(word)))

// --- The document --------------------------------------------------------------------------------

/**
 * Figure sizes on the landscape pages (A4 landscape inside the margins is 737 x 467 pt). A figure,
 * its heading and its note are kept together as one unbreakable block, and pdfmake silently drops
 * an unbreakable block taller than a page, so every limit leaves room for the heading.
 */
export const FIGURE = { width: 737, pageHeight: 467, diagramHeight: 300, largeDiagramHeight: 340, categoryHeight: 340, headingAllowance: 64 } as const

/** Section numbers, fixed so sections can refer to each other. Cover and contents are unnumbered. */
export const SECTION = {
  executive: 1,
  diagram: 2,
  services: 3,
  cost: 4,
  security: 5,
  reliability: 6,
  networking: 7,
  compute: 8,
  review: 9,
  specialists: 10,
  final: 11,
  trace: 12,
} as const

/** Section titles in order, as printed in the contents. */
export const SECTION_TITLES: ReadonlyArray<readonly [number, string]> = [
  [SECTION.executive, 'Executive Summary'],
  [SECTION.diagram, 'Architecture Overview and Diagram'],
  [SECTION.services, 'AWS Services and Technical Specifications'],
  [SECTION.cost, 'Cost Analysis'],
  [SECTION.security, 'Security Analysis'],
  [SECTION.reliability, 'Reliability Analysis'],
  [SECTION.networking, 'Networking Analysis'],
  [SECTION.compute, 'Compute and Database Analysis'],
  [SECTION.review, 'Validation and Review'],
  [SECTION.specialists, 'Specialist Analyses'],
  [SECTION.final, 'Final Architecture Report'],
  [SECTION.trace, 'Execution Trace'],
]

export function buildReportDocument(input: ReportInput): TDocumentDefinitions {
  const { result, jobId, icons } = input
  const r = obj(result)
  const requirements = obj(r.requirements)
  const plan = obj(r.architecture_plan)
  const architecture = obj(r.architecture)
  const services = arr<AWSService>(architecture.services)
  const steps = arr<DataFlowStep>(architecture.data_flow)
  const cost = obj(r.cost_analysis)
  const critic = obj(r.critic_review)
  const validation = obj(r.validation_results)
  const report = obj(r.final_report)
  const criticIssues = arr<CriticIssue>(critic.issues)
  const validationIssues = arr<ValidationIssue>(validation.issues)
  const score = num(critic.score)
  const approved = bool(r.approved) ?? bool(critic.approved)
  const name = projectName(result)
  const shortId = jobId.slice(0, 8)
  const generated = input.generatedAt.toISOString()


  // ---- A. Cover ----------------------------------------------------------------------------------
  const logo =
    `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44"><rect width="44" height="44" rx="9" fill="#FFFFFF"/>` +
    `<g transform="translate(10 10) scale(1)" fill="none" stroke="${PALETTE.ink}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">` +
    '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z"/>' +
    '<path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12"/>' +
    '<path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17"/></g></svg>'
  const request = str(input.request)
  const coverRequest = request.length > 700 ? `${request.slice(0, 699).trimEnd()}… (the full request is in section 1)` : request
  const verdict = approved === null ? 'Not recorded' : approved ? 'Approved by the critic' : 'Not approved by the critic'
  const revisionCount = num(r.revision_count)

  const cover: Content[] = [
    {
      columns: [
        { svg: logo, width: 44 },
        { stack: [{ text: 'ArchonAI', fontSize: 17, bold: true, color: '#FFFFFF' }, { text: 'AWS architecture design', fontSize: 9, color: '#D5DBDB' }], margin: [10, 5, 0, 0] },
      ],
      margin: [0, 0, 0, 70],
    },
    { text: 'AWS ARCHITECTURE DESIGN REPORT', fontSize: 10, bold: true, color: PALETTE.orange, characterSpacing: 1.5, margin: [0, 0, 0, 8] },
    { text: name, fontSize: 30, bold: true, color: '#FFFFFF', lineHeight: 1.1, margin: [0, 0, 0, 10] },
    { text: str(architecture.summary).split('\n')[0].slice(0, 260) || ' ', fontSize: 10.5, color: '#D5DBDB', lineHeight: 1.35, margin: [0, 0, 0, 0] },
    { text: '', margin: [0, 92, 0, 0] },
    { text: 'ORIGINAL REQUEST', style: 'overline' },
    {
      table: { widths: ['*'], body: [[{ text: coverRequest || 'Not available', italics: !coverRequest, color: coverRequest ? PALETTE.text : PALETTE.muted, fontSize: 10, lineHeight: 1.35 }]] },
      layout: { hLineWidth: () => 0, vLineWidth: (i: number) => (i === 0 ? 3 : 0), vLineColor: () => PALETTE.orange, paddingLeft: () => 12, paddingTop: () => 8, paddingBottom: () => 8, fillColor: () => PALETTE.soft },
      margin: [0, 4, 0, 22],
    },
    {
      columns: [
        { stack: [{ text: 'CRITIC SCORE', style: 'overline' }, { text: score === null ? '—' : `${score}/100`, fontSize: 22, bold: true, color: PALETTE.ink }] },
        { stack: [{ text: 'VERDICT', style: 'overline' }, { text: verdict, fontSize: 11, bold: true, color: approved ? PALETTE.success : approved === false ? PALETTE.warning : PALETTE.muted, margin: [0, 6, 0, 0] }] },
        { stack: [{ text: 'AWS SERVICES', style: 'overline' }, { text: String(services.length), fontSize: 22, bold: true, color: PALETTE.ink }] },
        { stack: [{ text: 'REVISION ROUNDS', style: 'overline' }, { text: revisionCount === null ? '—' : String(revisionCount), fontSize: 22, bold: true, color: PALETTE.ink }] },
      ],
      margin: [0, 0, 0, 22],
    },
    facts([
      ['Job ID', jobId],
      ['Estimated monthly cost', str(cost.estimated_monthly_range)],
      ['Job submitted', formatDate(input.createdAt)],
      ['Job finished', formatDate(input.finishedAt)],
      ['Report generated', formatDate(generated)],
      ['Generated by', `ArchonAI ${input.appVersion}, from the saved job result`],
    ]),
  ]

  // ---- B. Contents -------------------------------------------------------------------------------
  const contents: Content[] = [
    { text: 'Contents', style: 'h1', pageBreak: 'before' },
    { canvas: [{ type: 'rect', x: 0, y: 2, w: 46, h: 3, color: PALETTE.orange }], margin: [0, 0, 0, 14] },
    { toc: { numberStyle: { bold: true, color: PALETTE.ink } } } as Content,
    {
      text: 'Everything in this report comes from the saved result of this job. Where the result does not contain a detail, the report says so instead of guessing.',
      style: 'note',
      margin: [0, 18, 0, 0],
    },
  ]

  // ---- C. Executive summary ----------------------------------------------------------------------
  const execNo = SECTION.executive
  const exec: Content[] = [
    sectionHeading(execNo, 'Executive Summary', 'sec-executive'),
    h2('Project overview'),
    para(str(report.executive_summary) || str(architecture.summary)),
    h2('Original request'),
    para(request, 'The request text is not available for this job.'),
    h2('Business and technical requirements'),
    facts([
      ...REQUIREMENT_ROWS.map(([key, label]) => [label, str(requirements[key])] as [string, string]),
      ['Traffic pattern', TRAFFIC_PATTERN_LABEL[requirements.traffic_pattern as keyof typeof TRAFFIC_PATTERN_LABEL] ?? str(requirements.traffic_pattern)],
    ]),
    h3('Stated by the user'),
    bullets(strs(requirements.explicit_requirements)),
    h3('Assumed by the requirements analyst'),
    bullets(strs(requirements.inferred_assumptions)),
    h2('Proposed architecture'),
    para(str(architecture.summary)),
    h2('Main AWS services'),
    services.length
      ? table(
          ['', 'Service', 'Category', 'Role in this architecture'],
          services.map((service) => [iconStrip(str(service.name), icons, 16) as TableCell, { text: str(service.name), style: 'tdBold' }, { text: str(service.category), style: 'td' }, { text: str(service.purpose), style: 'td' }]),
          [54, 120, 70, '*'],
          true,
        )
      : para('', 'No services are listed in the generated result.'),
    h2('Key architectural decisions'),
    note('The architecture planner’s decision for each concern, as written in the result.'),
    facts(PLAN_AREAS.map(([key, label]) => [label, str(plan[key])] as [string, string])),
    h2('Important design considerations'),
    h3('Trade-offs'),
    bullets(strs(report.trade_offs)),
    h3('Bottlenecks to watch'),
    bullets(strs(report.bottlenecks)),
  ]

  // ---- D. Architecture overview and diagram (landscape) ------------------------------------------
  const diagramNo = SECTION.diagram
  const flow = flowDiagramSvg(steps, icons)
  const overview = para(str(report.architecture_overview) || str(architecture.summary))
  const diagram: Content[] = [sectionHeading(diagramNo, 'Architecture Overview and Diagram', 'sec-diagram', { pageOrientation: 'landscape' })]
  if (flow) {
    // A diagram that would shrink a lot goes straight under the heading with the most room it can
    // have, and the overview text follows it. Every figure block is sized to fit one page (FIGURE).
    const fullSize = Math.min(FIGURE.width / flow.width, FIGURE.diagramHeight / flow.height) < 0.75
    if (!fullSize) diagram.push(overview)
    diagram.push({
      stack: [h2('Data-flow diagram'), { svg: flow.svg, fit: [FIGURE.width, fullSize ? FIGURE.largeDiagramHeight : FIGURE.diagramHeight], alignment: 'center', margin: [0, 4, 0, 8] }],
      unbreakable: true,
    } as Content)
    diagram.push({
      text: [
        { text: 'How to read it. ', bold: true },
        `Each box is a component named in the data flow; arrows follow the ${steps.length} steps in order and are numbered by step. `,
        ...(flow.hasBackEdges ? ['Dashed arrows return to a component that appeared earlier in the flow. '] : []),
        'Icons are official AWS Architecture Icons matched by service name; a grey tile with initials marks a component with no matching AWS icon. ',
        'VPCs, availability zones and subnets are not drawn because the generated result does not describe them.',
      ],
      style: 'note',
    })
    if (flow.icons.length) diagram.push({ text: [{ text: 'AWS icons used: ', bold: true }, flow.icons.map((icon) => icon.label).join(' · ')], style: 'note' })
    if (flow.clipped.length) diagram.push(note('Some long component names are shortened in the boxes; the full names are in the step table below.'))
    if (fullSize) diagram.push(h2('Overview'), overview)
    diagram.push(
      h2('Data-flow steps'),
      table(
        ['#', 'From', 'To', 'What happens'],
        steps.map((step, i) => [
          { text: String(num(step.step) ?? i + 1), style: 'tdBold' },
          { text: str(step.source), style: 'td' },
          { text: str(step.destination), style: 'td' },
          { text: str(step.description), style: 'td' },
        ]),
        [24, 150, 150, '*'],
        true,
      ),
    )
  } else {
    diagram.push(overview, callout('The generated result has no data-flow steps, so there is no diagram to draw.', PALETTE.muted))
  }
  const categories = categoryFigureSvg(services, icons, FIGURE.width)
  if (categories) {
    diagram.push({
      stack: [h2('Services by category'), note('Every service in the architecture, grouped by the category the designer gave it.'), { svg: categories.svg, fit: [FIGURE.width, FIGURE.categoryHeight], alignment: 'center' }],
      unbreakable: true,
    } as Content)
  }
  if (str(report.data_flow_summary)) diagram.push(h2('Data flow summary'), para(str(report.data_flow_summary)))

  // ---- E. Services and specifications (back to portrait) -----------------------------------------
  const servicesNo = SECTION.services
  const servicesSection: Content[] = [
    sectionHeading(servicesNo, 'AWS Services and Technical Specifications', 'sec-services', { pageOrientation: 'portrait' }),
    note(
      'For each service the result records its name, category, purpose and the reason it was chosen. It does not record configuration or sizing, so none is shown. Connections are the data-flow steps whose component name resembles the service (matched by name only).',
    ),
  ]
  if (services.length === 0) servicesSection.push(para('', 'No services are listed in the generated result.'))
  services.forEach((service, index) => {
    const serviceName = str(service.name) || `Service ${index + 1}`
    const connected = steps.filter((step) =>
      [step.source, step.destination].some((label) => possibleServiceMatches(str(label), [service]).length > 0),
    )
    const card: Content = {
      table: {
        widths: ['*'],
        body: [
          [
            {
              columns: [
                { ...(iconStrip(serviceName, icons, 30) as object), width: 'auto' },
                {
                  stack: [
                    { text: serviceName, fontSize: 12, bold: true, color: PALETTE.ink },
                    { text: str(service.category) || 'No category', fontSize: 8.5, color: PALETTE.muted, margin: [0, 2, 0, 0] },
                  ],
                  margin: [10, 2, 0, 0],
                },
              ],
              fillColor: PALETTE.soft,
            },
          ],
          [
            {
              stack: [
                { text: 'Purpose and responsibilities', style: 'cardLabel' },
                para(str(service.purpose)),
                { text: 'Why this service was selected', style: 'cardLabel' },
                para(str(service.justification)),
                { text: 'Dependencies and integrations (data-flow steps)', style: 'cardLabel' },
                connected.length
                  ? bullets(connected.map((step) => `Step ${num(step.step) ?? '?'}: ${str(step.source)} to ${str(step.destination)}`))
                  : para('', 'No data-flow step names this service.'),
              ],
            },
          ],
        ],
      },
      layout: { hLineWidth: () => 0.6, vLineWidth: () => 0.6, hLineColor: () => PALETTE.border, vLineColor: () => PALETTE.border, paddingLeft: () => 10, paddingRight: () => 10, paddingTop: () => 8, paddingBottom: () => 4 },
      margin: [0, 0, 0, 12],
      unbreakable: true,
    } as Content
    servicesSection.push(card)
  })
  servicesSection.push(
    note(`Security and reliability considerations are not recorded per service; they are covered across the architecture in sections ${SECTION.security} and ${SECTION.reliability}.`),
  )

  // ---- F. Cost -----------------------------------------------------------------------------------
  const costNo = SECTION.cost
  const breakdown = Object.entries(obj(cost.relative_cost_breakdown)).map(([area, level]) => [area, str(level)] as const)
  const levelBars = (level: string): TableCell => {
    const value = costLevel(level)
    if (value === null) return { text: level || '—', style: 'td' }
    return {
      columns: [
        { canvas: [0, 1, 2].map((i) => ({ type: 'rect', x: i * 15, y: 2, w: 12, h: 7, r: 1, color: i < value ? PALETTE.orange : PALETTE.border })), width: 48 },
        { text: titleCase(level.toLowerCase()), style: 'td', margin: [4, 0, 0, 0] },
      ],
    } as TableCell
  }
  const costSection: Content[] = [
    sectionHeading(costNo, 'Cost Analysis', 'sec-cost'),
    {
      table: { widths: ['*'], body: [[{ stack: [{ text: 'ESTIMATED MONTHLY COST', style: 'overline' }, { text: str(cost.estimated_monthly_range) || 'Not provided', fontSize: 18, bold: true, color: PALETTE.ink, margin: [0, 3, 0, 0] }] }]] },
      layout: { hLineWidth: () => 0, vLineWidth: (i: number) => (i === 0 ? 3 : 0), vLineColor: () => PALETTE.orange, paddingLeft: () => 12, paddingTop: () => 9, paddingBottom: () => 9, fillColor: () => PALETTE.soft },
      margin: [0, 0, 0, 12],
    } as Content,
    h2('Relative cost by area'),
    note('The cost agent ranks each area as low, medium or high. These are relative weights, not amounts or percentages, so no dollar breakdown per service is shown.'),
    breakdown.length ? table(['Area', 'Relative cost'], breakdown.map(([area, level]) => [{ text: titleCase(area), style: 'tdBold' }, levelBars(level)]), [180, '*']) : para('', 'The result has no relative cost breakdown.'),
    h2('Major cost drivers'),
    bullets(strs(cost.major_cost_drivers)),
    h2('Cost optimisation recommendations'),
    bullets(strs(cost.optimizations)),
    h2('Cost trade-offs'),
    bullets(strs(cost.trade_offs)),
    h2('Cost-shape decision (architecture plan)'),
    para(str(plan.cost)),
    h2('Budget stated in the requirements'),
    para(str(requirements.budget_constraints)),
    h2('Assumptions and disclaimer'),
    callout(str(cost.disclaimer) || 'No disclaimer was recorded. Treat all figures as educational estimates, not AWS quotes.', PALETTE.warning, 'Pricing note'),
  ]

  // ---- G-J. Domain sections ----------------------------------------------------------------------
  const analyses = {
    compute: obj(r.compute_analysis) as unknown as AnalysisResult,
    database: obj(r.database_analysis) as unknown as AnalysisResult,
    networking: obj(r.networking_analysis) as unknown as AnalysisResult,
    security: obj(r.security_analysis) as unknown as AnalysisResult,
    reliability: obj(r.reliability_analysis) as unknown as AnalysisResult,
  }
  const reportPointer = (title: string): Content => ({
    text: [`The final report’s ${title} is printed in full in section ${SECTION.final}, starting on page `, { pageReference: 'sec-final' } as Content, '.'],
    style: 'note',
  }) as Content
  const domainIssues = (words: string[], label: string): Content[] => {
    const found = issuesAbout(criticIssues, words)
    return [h2(`Critic findings about ${label}`), found.length ? issuesTable(found) : para('', `The critic raised no ${label} issues.`)]
  }

  const securityNo = SECTION.security
  const securitySection: Content[] = [
    sectionHeading(securityNo, 'Security Analysis', 'sec-security'),
    h2('Security requirements'),
    facts([
      ['Security', str(requirements.security_requirements)],
      ['Compliance', str(requirements.compliance_requirements)],
    ]),
    h2('Security architecture (plan)'),
    para(str(plan.security)),
    ...analysisBlock(analyses.security, 'Security specialist analysis'),
    ...domainIssues(['security', 'compliance', 'iam', 'encryption'], 'security'),
    reportPointer('security summary'),
  ]

  const reliabilityNo = SECTION.reliability
  const reliabilitySection: Content[] = [
    sectionHeading(reliabilityNo, 'Reliability Analysis', 'sec-reliability'),
    h2('Availability and scaling requirements'),
    facts([
      ['Availability', str(requirements.availability_requirements)],
      ['Scalability', str(requirements.scalability_requirements)],
      ['Traffic', str(requirements.traffic_characteristics)],
    ]),
    h2('Reliability, scalability and observability (plan)'),
    facts([
      ['Reliability', str(plan.reliability)],
      ['Scalability', str(plan.scalability)],
      ['Observability', str(plan.observability)],
    ]),
    ...analysisBlock(analyses.reliability, 'Reliability specialist analysis'),
    ...domainIssues(['reliab', 'availab', 'resilien', 'scalab', 'disaster', 'backup', 'fault'], 'reliability'),
    reportPointer('high-availability strategy and reliability summary'),
  ]

  const networkingNo = SECTION.networking
  const networkingSection: Content[] = [
    sectionHeading(networkingNo, 'Networking Analysis', 'sec-networking'),
    note('The generated result describes networking in prose. It does not list VPCs, subnets, route tables or security groups as structured data, so none are drawn or tabulated beyond what the text says.'),
    h2('Networking and delivery (plan)'),
    facts([
      ['Networking', str(plan.networking)],
      ['Frontend and delivery', str(plan.frontend)],
    ]),
    h2('Latency and geography requirements'),
    facts([
      ['Latency', str(requirements.latency_requirements)],
      ['Geography', str(requirements.geographic_requirements)],
    ]),
    ...analysisBlock(analyses.networking, 'Networking specialist analysis'),
    h2('Data flow between components'),
    note(`The ${steps.length} data-flow steps are drawn and listed in section ${diagramNo}.`),
    ...domainIssues(['network', 'latency', 'routing', 'dns', 'cdn'], 'networking'),
  ]

  const computeNo = SECTION.compute
  const computeSection: Content[] = [
    sectionHeading(computeNo, 'Compute and Database Analysis', 'sec-compute'),
    h2('Plan'),
    facts([
      ['Compute', str(plan.compute)],
      ['Database', str(plan.database)],
      ['Caching', str(plan.caching)],
      ['Storage', str(plan.storage)],
      ['Messaging', str(plan.messaging)],
    ]),
    h2('Data requirements'),
    facts([
      ['Database', str(requirements.database_requirements)],
      ['Storage', str(requirements.storage_requirements)],
    ]),
    ...analysisBlock(analyses.compute, 'Compute specialist analysis'),
    ...analysisBlock(analyses.database, 'Database specialist analysis'),
  ]

  // ---- K. Validation and review ------------------------------------------------------------------
  const reviewNo = SECTION.review
  const requiredChanges = strs(critic.required_changes)
  const validationPassed = bool(validation.passed)
  const reviewSection: Content[] = [
    sectionHeading(reviewNo, 'Validation and Review', 'sec-review'),
    facts([
      ['Critic score', score === null ? 'Not recorded' : `${score}/100`],
      ['Approval', verdict],
      ['Revision rounds', revisionCount === null ? 'Not recorded' : String(revisionCount)],
      ['Revision limit reached', bool(r.max_revisions_reached) === null ? 'Not recorded' : bool(r.max_revisions_reached) ? 'Yes: revisions stopped at the limit' : 'No'],
      ['Architecture version', num(architecture.version) === null ? 'Not recorded' : String(num(architecture.version))],
      ['Rule-based validation', validationPassed === null ? 'Not recorded' : validationPassed ? 'Passed: no rule was triggered' : `Not passed: ${validationIssues.length} issue(s)`],
    ]),
    callout(
      'ArchonAI does not label findings as blocking. In this report, the critic’s required changes are treated as blocking because they are its conditions for approval. Every other finding is non-blocking and keeps the severity the critic or validator gave it.',
      PALETTE.info,
      'How findings are classified',
    ),
    h2('Blocking: required changes'),
    requiredChanges.length ? numbered(requiredChanges) : para('', approved ? 'None: the critic approved the architecture.' : 'The critic listed no required changes.'),
    h2('Non-blocking: critic issues'),
    criticIssues.length ? issuesTable(criticIssues) : para('', 'The critic listed no issues.'),
    h2('Non-blocking: rule-based validation findings'),
    validationIssues.length
      ? table(
          ['Severity', 'Rule', 'Finding'],
          [...validationIssues]
            .sort((x, y) => (SEVERITY_ORDER[x.severity] ?? 9) - (SEVERITY_ORDER[y.severity] ?? 9))
            .map((issue) => [severityCell(issue.severity), { text: str(issue.rule), style: 'tdBold' }, { text: str(issue.message), style: 'td' }]),
          [58, 130, '*'],
          true,
        )
      : para('', validationPassed ? 'No validation rule was triggered.' : 'No validation findings were recorded.'),
    h2('Strengths noted by the critic'),
    bullets(strs(critic.strengths)),
    h2('Revision history'),
    bullets(strs(architecture.change_log), 'No revision changes were recorded.'),
    h2('Critic findings summary (final report)'),
    para(str(report.critic_findings_summary)),
  ]

  // ---- L. Specialist analyses overview -----------------------------------------------------------
  const specialistNo = SECTION.specialists
  const domainRows: Array<[string, AnalysisResult, string]> = [
    ['Compute', analyses.compute, 'sec-compute'],
    ['Database', analyses.database, 'sec-compute'],
    ['Networking', analyses.networking, 'sec-networking'],
    ['Security', analyses.security, 'sec-security'],
    ['Reliability', analyses.reliability, 'sec-reliability'],
  ]
  const specialistSection: Content[] = [
    sectionHeading(specialistNo, 'Specialist Analyses', 'sec-specialists'),
    note('Five specialist agents analysed the design. Each analysis is printed in full (recommendations, reasoning and risks) in its domain section; this table summarises them.'),
    table(
      ['Specialist', 'Recommendations', 'Risks', 'First recommendation', 'Page'],
      domainRows.map(([label, analysis, target]) => {
        const recs = strs(obj(analysis).recommendations)
        return [
          { text: label, style: 'tdBold' },
          { text: String(recs.length), style: 'td', alignment: 'center' },
          { text: String(strs(obj(analysis).risks).length), style: 'td', alignment: 'center' },
          { text: recs[0] ?? 'Not provided', style: recs[0] ? 'td' : 'mutedTd' },
          { pageReference: target, style: 'tdBold', alignment: 'center' } as unknown as TableCell,
        ]
      }),
      [64, 46, 32, '*', 30],
      true,
    ),
  ]

  // ---- M. Final report ---------------------------------------------------------------------------
  const finalNo = SECTION.final
  const finalSection: Content[] = [
    sectionHeading(finalNo, 'Final Architecture Report', 'sec-final'),
    note('The complete final report written by ArchonAI’s report agent, in its original order.'),
    ...REPORT_SECTIONS.flatMap((s): Content[] =>
      s.kind === 'text' ? [h2(s.title), para(str(report[s.key]))] : [h2(s.title), bullets(strs(report[s.key]))],
    ),
  ]

  // ---- N. Execution trace ------------------------------------------------------------------------
  const traceNo = SECTION.trace
  const trace = readTrace(result)
  const traceRows: TableCell[][] = []
  for (const group of trace.groups) {
    traceRows.push([{ text: iterationLabel(group.iteration, group.rawIteration), colSpan: 4, bold: true, fontSize: 8.5, color: PALETTE.ink, fillColor: PALETTE.soft }, {}, {}, {}])
    for (const step of group.steps) {
      traceRows.push([
        { text: String(step.seq), style: 'tdBold' },
        { text: [step.node || 'Unnamed step', ...(step.runs > 1 ? [{ text: `  run ${step.run} of ${step.runs}`, color: PALETTE.muted, fontSize: 7.5 }] : [])], style: 'tdBold' },
        { text: step.action || '—', style: 'td' },
        { text: step.summary || '—', style: 'td' },
      ])
    }
  }
  const traceSection: Content[] = [
    sectionHeading(traceNo, 'Execution Trace', 'sec-trace'),
    facts([
      ['Steps recorded', String(trace.steps.length)],
      ['Distinct agents', String(trace.distinctNodes)],
      ['Iterations', trace.iterations.length ? trace.iterations.join(', ') : 'Not recorded'],
      ['Revision rounds', String(trace.revisionRounds.length)],
      ['Agents that ran more than once', trace.repeated.length ? trace.repeated.map((x) => `${x.node} (${x.runs}×)`).join(', ') : 'None'],
      ['Timestamps', 'Not recorded: the trace stores the order of steps, not their times.'],
    ]),
    h2('How the workflow runs'),
    note(
      'This is ArchonAI’s fixed workflow design, not data from this run: requirements analysis, planning and design run in sequence; the specialists then run in three parallel pairs (compute and database, networking and security, reliability and cost); a rule-based validator and the critic follow; a rejected design is revised and checked again, up to the revision limit; the final report comes last. Steps of a parallel pair appear below in the order they were recorded.',
    ),
    h2('Steps in execution order'),
    trace.steps.length ? table(['#', 'Agent', 'What it did', 'Output'], traceRows, [20, 110, 150, '*'], true) : para('', 'The result has no execution trace.'),
  ]
  // The document's last block ends without a bottom margin: a margin that lands exactly on a
  // page boundary would otherwise start an empty final page.
  const last = traceSection[traceSection.length - 1] as { margin?: unknown }
  last.margin = [0, 2, 0, 0]

  return {
    pageSize: 'A4',
    pageMargins: [52, 70, 52, 58],
    info: {
      title: `${name} — AWS Architecture Design Report`,
      author: 'ArchonAI',
      subject: `Architecture job ${jobId}`,
      creator: `ArchonAI ${input.appVersion}`,
      producer: 'ArchonAI (pdfmake)',
    },
    background: (currentPage: number, pageSize: { width: number }) =>
      currentPage === 1
        ? ({
            canvas: [
              { type: 'rect', x: 0, y: 0, w: pageSize.width, h: 360, color: PALETTE.ink },
              { type: 'rect', x: 0, y: 360, w: pageSize.width, h: 5, color: PALETTE.orange },
            ],
          } as Content)
        : null,
    header: (currentPage: number, _pageCount: number, pageSize: { width: number }) =>
      currentPage === 1
        ? null
        : ({
            margin: [52, 28, 52, 0],
            stack: [
              {
                columns: [
                  { text: [{ text: 'ArchonAI', bold: true, color: PALETTE.ink }, { text: '  ·  AWS Architecture Design Report', color: PALETTE.muted }], fontSize: 8 },
                  { text: name, alignment: 'right', fontSize: 8, color: PALETTE.muted },
                ],
              },
              { canvas: [{ type: 'line', x1: 0, y1: 6, x2: pageSize.width - 104, y2: 6, lineWidth: 0.5, lineColor: PALETTE.border }] },
            ],
          } as Content),
    footer: (currentPage: number, pageCount: number) =>
      currentPage === 1
        ? null
        : ({
            margin: [52, 18, 52, 0],
            columns: [
              { text: `Job ${shortId} · Generated ${formatDate(generated)}`, fontSize: 7.5, color: PALETTE.muted },
              { text: `Page ${currentPage} of ${pageCount}`, alignment: 'right', fontSize: 7.5, color: PALETTE.muted },
            ],
          } as Content),
    // Never leave a heading alone at the bottom of a page: move it on when nothing follows it on
    // the page, or when it starts in the last 12% of the page (too little room for its text).
    pageBreakBefore: (currentNode, nodeQueries) =>
      Boolean(currentNode.headlineLevel) && (nodeQueries.getFollowingNodesOnPage().length === 0 || currentNode.startPosition.verticalRatio > 0.88),
    content: [
      ...cover,
      ...contents,
      ...exec,
      ...diagram,
      ...servicesSection,
      ...costSection,
      ...securitySection,
      ...reliabilitySection,
      ...networkingSection,
      ...computeSection,
      ...reviewSection,
      ...specialistSection,
      ...finalSection,
      ...traceSection,
    ],
    defaultStyle: { font: 'Roboto', fontSize: 9.5, color: PALETTE.text, lineHeight: 1.3 },
    styles: {
      h1: { fontSize: 20, bold: true, color: PALETTE.ink, margin: [0, 0, 0, 2] },
      h2: { fontSize: 12.5, bold: true, color: PALETTE.ink, margin: [0, 12, 0, 6] },
      h3: { fontSize: 10, bold: true, color: PALETTE.ink, margin: [0, 6, 0, 4] },
      body: { fontSize: 9.5, lineHeight: 1.35, margin: [0, 0, 0, 8] },
      muted: { fontSize: 9, color: PALETTE.muted },
      note: { fontSize: 8.5, color: PALETTE.muted, lineHeight: 1.3, margin: [0, 0, 0, 8] },
      overline: { fontSize: 7.5, bold: true, color: PALETTE.muted, characterSpacing: 1 },
      table: { margin: [0, 2, 0, 12] },
      th: { fontSize: 8, bold: true, color: PALETTE.ink },
      td: { fontSize: 8.5, lineHeight: 1.25 },
      tdBold: { fontSize: 8.5, bold: true, color: PALETTE.ink, lineHeight: 1.25 },
      mutedTd: { fontSize: 8.5, italics: true, color: PALETTE.muted },
      factLabel: { fontSize: 8.5, bold: true, color: PALETTE.muted },
      cardLabel: { fontSize: 7.5, bold: true, color: PALETTE.muted, characterSpacing: 0.6, margin: [0, 4, 0, 3] },
    },
  }
}

