import { Construction } from 'lucide-react'

import { Card, EmptyState } from '@/components/ui'

import type { ResultTab } from './results-tabs'

/** Temporary content for tabs implemented in later Stage 4B steps. */
const UPCOMING: Record<Exclude<ResultTab, 'overview' | 'architecture'>, { label: string; content: string; step: string }> = {
  cost: { label: 'Cost', content: 'the cost estimate, drivers, breakdown and optimizations', step: '4B-3' },
  review: { label: 'Review', content: 'the critic review, validation results, open recommendations and revisions', step: '4B-3' },
  analyses: { label: 'Analyses', content: 'the five specialist analyses', step: '4B-4' },
  report: { label: 'Report', content: 'the full final report', step: '4B-4' },
  trace: { label: 'Trace', content: 'the step-by-step execution trace', step: '4B-4' },
}

export function TabPlaceholder({ tab }: { tab: Exclude<ResultTab, 'overview' | 'architecture'> }) {
  const { label, content, step } = UPCOMING[tab]
  return (
    <Card>
      <EmptyState
        icon={Construction}
        title={`${label}: coming soon`}
        description={`Temporary placeholder. This tab will show ${content} (Stage ${step}).`}
      />
    </Card>
  )
}
