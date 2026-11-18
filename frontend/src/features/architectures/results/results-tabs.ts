/** The results page's sections, in display order. The id is the `?tab=` value. */
export const RESULT_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'cost', label: 'Cost' },
  { id: 'review', label: 'Review' },
  { id: 'analyses', label: 'Analyses' },
  { id: 'report', label: 'Report' },
  { id: 'trace', label: 'Trace' },
] as const

export type ResultTab = (typeof RESULT_TABS)[number]['id']

/** The tab named by a `?tab=` value; anything missing or unknown falls back to Overview. */
export function parseResultTab(value: string | null): ResultTab {
  return RESULT_TABS.find((tab) => tab.id === value)?.id ?? 'overview'
}
