import { OctagonAlert, TriangleAlert } from 'lucide-react'

import { Badge } from '@/components/ui'
import type { Tone } from '@/components/ui/tones'
import type { Severity } from '@/types/api'

/** Most to least severe. */
export const SEVERITIES: readonly Severity[] = ['critical', 'high', 'medium', 'low']

const STYLE: Record<Severity, { label: string; tone: Tone }> = {
  critical: { label: 'Critical', tone: 'danger' },
  high: { label: 'High', tone: 'warning' },
  medium: { label: 'Medium', tone: 'info' },
  low: { label: 'Low', tone: 'neutral' },
}

/** Severity as text plus tone (and an icon for critical/high), so colour is never the only cue. */
export function SeverityBadge({ severity }: { severity: Severity }) {
  const { label, tone } = STYLE[severity] ?? { label: severity, tone: 'neutral' }
  const Icon = severity === 'critical' ? OctagonAlert : severity === 'high' ? TriangleAlert : null
  return (
    <Badge tone={tone} data-severity={severity}>
      {Icon && <Icon className="size-3" aria-hidden="true" />}
      {label}
    </Badge>
  )
}

/** "1 critical · 2 high · 1 medium", most severe first; only levels that occur. */
export function severityCounts(severities: Severity[]): string {
  return SEVERITIES.filter((s) => severities.includes(s))
    .map((s) => `${severities.filter((x) => x === s).length} ${s}`)
    .join(' · ')
}
