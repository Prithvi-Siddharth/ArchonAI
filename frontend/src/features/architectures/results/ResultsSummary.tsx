import { Boxes, Gauge, GitBranch, TriangleAlert, Wallet } from 'lucide-react'

import { StatCard } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import type { ArchitectureResult } from '@/types/api'
import { cn } from '@/utils/cn'

import { splitCostRange } from './result-format'

interface ResultsSummaryProps {
  result: ArchitectureResult
  /** Opens the Review tab (for the not-approved warning). */
  onOpenReview: () => void
}

/** Four headline numbers, plus a warning when the critic did not approve the design. */
export function ResultsSummary({ result, onOpenReview }: ResultsSummaryProps) {
  const { approved, critic_review, architecture, cost_analysis, revision_count, max_revisions_reached } = result
  const categories = new Set(architecture.services.map((service) => service.category)).size
  const cost = splitCostRange(cost_analysis.estimated_monthly_range)

  return (
    // Columns follow the space this section actually has (sidebar expanded or collapsed),
    // so the cost range never wraps: 2 columns from 32rem, 4 only from 64rem.
    <div className="@container space-y-4">
      <div className="grid gap-4 @lg:grid-cols-2 @5xl:grid-cols-4">
        <StatCard
          label="Critic score"
          value={`${critic_review.score}/100`}
          detail={approved ? 'Approved by the critic' : 'Not approved by the critic'}
          icon={Gauge}
          tone={approved ? 'success' : 'warning'}
        />
        <StatCard
          label="AWS services"
          value={String(architecture.services.length)}
          detail={`${categories} ${categories === 1 ? 'category' : 'categories'}`}
          icon={Boxes}
        />
        <StatCard label="Estimated monthly cost" value={cost.amount} detail={cost.note || undefined} icon={Wallet} />
        <StatCard
          label="Revision rounds"
          value={String(revision_count)}
          detail={`Architecture version ${architecture.version}${max_revisions_reached ? ' · limit reached' : ''}`}
          icon={GitBranch}
        />
      </div>

      {!approved && (
        <div className={cn('flex flex-col gap-3 rounded-md border px-4 py-3 sm:flex-row sm:items-center', TONE_SOFT.warning)}>
          <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">
            <span className="font-medium">The critic did not approve this architecture</span>
            {max_revisions_reached ? ` after ${revision_count} revision rounds, the limit.` : '.'} The Review tab lists the
            remaining issues and open recommendations.
          </p>
          <button
            type="button"
            onClick={onOpenReview}
            className="shrink-0 self-start rounded-sm font-medium underline underline-offset-2 hover:no-underline sm:self-auto"
          >
            Open the Review tab
          </button>
        </div>
      )}
    </div>
  )
}
