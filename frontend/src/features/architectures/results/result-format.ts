import type { ArchitecturePlan, Requirements, TrafficPattern } from '@/types/api'

export const TRAFFIC_PATTERN_LABEL: Record<TrafficPattern, string> = {
  steady: 'Steady',
  spiky: 'Spiky',
  seasonal: 'Seasonal',
  unpredictable: 'Unpredictable',
}

/** The 12 plan concerns, in the backend model's order. */
export const PLAN_AREAS: ReadonlyArray<[keyof ArchitecturePlan, string]> = [
  ['frontend', 'Frontend'],
  ['networking', 'Networking'],
  ['compute', 'Compute'],
  ['database', 'Database'],
  ['caching', 'Caching'],
  ['storage', 'Storage'],
  ['messaging', 'Messaging'],
  ['security', 'Security'],
  ['observability', 'Observability'],
  ['reliability', 'Reliability'],
  ['scalability', 'Scalability'],
  ['cost', 'Cost'],
]

/** Free-text requirement fields shown in the key requirements table (traffic pattern is shown separately). */
export const REQUIREMENT_ROWS: ReadonlyArray<[keyof Requirements, string]> = [
  ['application_type', 'Application'],
  ['expected_users', 'Expected users'],
  ['concurrent_users', 'Concurrent users'],
  ['traffic_characteristics', 'Traffic'],
  ['latency_requirements', 'Latency'],
  ['availability_requirements', 'Availability'],
  ['scalability_requirements', 'Scalability'],
  ['storage_requirements', 'Storage'],
  ['database_requirements', 'Database'],
  ['security_requirements', 'Security'],
  ['compliance_requirements', 'Compliance'],
  ['geographic_requirements', 'Geography'],
  ['budget_constraints', 'Budget'],
]

/**
 * Split the free-text cost range into a short amount and a note, for a
 * statistic card: "$4,120 - $34,800 per month (educational estimate)" ->
 * { amount: "$4,120 - $34,800", note: "per month · educational estimate" }.
 * Text that doesn't start with a dollar amount is returned whole.
 */
export function splitCostRange(text: string): { amount: string; note: string } {
  const match = /^\s*(\$[\d,.]+(?:\s*[-–]\s*\$[\d,.]+)?)\s*(.*)$/.exec(text)
  if (!match) return { amount: text.trim(), note: '' }
  const note = match[2]
    .replace(/\s*\(\s*/g, ' · ')
    .replace(/\s*\)\s*/g, ' ')
    .replace(/^\s*·\s*/, '')
    .replace(/\s+/g, ' ')
    .trim()
  return { amount: match[1], note }
}
