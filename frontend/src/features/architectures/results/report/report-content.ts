import type { FinalReport } from '@/types/api'

type KeysOfType<T, V> = { [K in keyof T]: T[K] extends V ? K : never }[keyof T]
export type ReportTextKey = KeysOfType<FinalReport, string>
export type ReportListKey = KeysOfType<FinalReport, string[]>

export type ReportSection = { kind: 'text'; key: ReportTextKey; title: string } | { kind: 'list'; key: ReportListKey; title: string }

/** Every final_report field, in the order the backend returns them (graph/state.py FinalReport). */
export const REPORT_SECTIONS: readonly ReportSection[] = [
  { kind: 'text', key: 'executive_summary', title: 'Executive summary' },
  { kind: 'text', key: 'requirements_summary', title: 'Requirements summary' },
  { kind: 'text', key: 'architecture_overview', title: 'Architecture overview' },
  { kind: 'text', key: 'aws_services_summary', title: 'AWS services summary' },
  { kind: 'text', key: 'data_flow_summary', title: 'Data flow summary' },
  { kind: 'text', key: 'scalability_strategy', title: 'Scalability strategy' },
  { kind: 'text', key: 'high_availability_strategy', title: 'High availability strategy' },
  { kind: 'text', key: 'security_summary', title: 'Security summary' },
  { kind: 'text', key: 'reliability_summary', title: 'Reliability summary' },
  { kind: 'text', key: 'observability_summary', title: 'Observability summary' },
  { kind: 'text', key: 'cost_summary', title: 'Cost summary' },
  { kind: 'list', key: 'bottlenecks', title: 'Bottlenecks' },
  { kind: 'list', key: 'trade_offs', title: 'Trade-offs' },
  { kind: 'text', key: 'critic_findings_summary', title: 'Critic findings summary' },
  { kind: 'list', key: 'final_recommendations', title: 'Final recommendations' },
  { kind: 'list', key: 'open_recommendations', title: 'Open recommendations' },
]

export const sectionTitle = (key: ReportTextKey | ReportListKey) => REPORT_SECTIONS.find((s) => s.key === key)?.title ?? key

/**
 * A text section without surrounding whitespace, with Windows line endings normalised.
 * Anything that is not a string (an absent report or field) reads as ''.
 */
export function reportText(report: FinalReport | undefined, key: ReportTextKey): string {
  const value: unknown = report?.[key]
  return typeof value === 'string' ? value.replace(/\r\n?/g, '\n').trim() : ''
}

/** A list section's items in their original order. Non-strings and blank items are skipped. */
export function reportList(report: FinalReport | undefined, key: ReportListKey): string[] {
  const value: unknown = report?.[key]
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim() !== '').map((item) => item.replace(/\r\n?/g, '\n').trim())
}

/** True when the report is absent or every section is blank. */
export function isReportEmpty(report: FinalReport | undefined): boolean {
  return REPORT_SECTIONS.every((s) => (s.kind === 'text' ? reportText(report, s.key) === '' : reportList(report, s.key).length === 0))
}
