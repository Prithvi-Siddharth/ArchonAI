import { Construction } from 'lucide-react'

import { Card, EmptyState } from '@/components/ui'

import type { ResultTab } from './results-tabs'

/** Temporary content for tabs implemented in later Stage 4B steps. */
const UPCOMING: Record<Exclude<ResultTab, 'overview' | 'architecture' | 'cost' | 'review' | 'analyses'>, { label: string; content: string; step: string }> = {
  report: { label: 'Report', content: 'the full final report', step: '4B-4' },
  trace: { label: 'Trace', content: 'the step-by-step execution trace', step: '4B-4' },
}

export function TabPlaceholder({ tab }: { tab: Exclude<ResultTab, 'overview' | 'architecture' | 'cost' | 'review' | 'analyses'> }) {
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
