import { Clock, Coins, Gauge, RotateCw, Sparkles, Waypoints } from 'lucide-react'

import { StatCard } from '@/components/ui'
import type { MonitoringSummary } from '@/types/api'
import { formatNumber } from '@/utils/format'

import { count, duration, EMPTY } from './format'

/** The headline numbers for one job, all worked out from its own log events. */
export function SummaryCards({ summary }: { summary: MonitoringSummary }) {
  const total = summary.job_duration_ms ?? summary.workflow_duration_ms
  const tokens = summary.input_tokens + summary.output_tokens
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatCard
        label="Total time"
        value={duration(total)}
        detail={`${formatNumber(summary.attempts)} ${summary.attempts === 1 ? 'attempt' : 'attempts'}${
          summary.workflow_duration_ms !== null && summary.job_duration_ms !== null ? ` · workflow ${duration(summary.workflow_duration_ms)}` : ''
        }`}
        icon={Clock}
      />
      <StatCard
        label="LLM calls"
        value={formatNumber(summary.llm_calls)}
        detail={summary.llm_failures ? `${formatNumber(summary.llm_failures)} failed` : 'None failed'}
        icon={Sparkles}
        tone={summary.llm_failures ? 'warning' : 'neutral'}
      />
      <StatCard
        label="Tokens"
        value={formatNumber(tokens)}
        detail={`${formatNumber(summary.input_tokens)} in · ${formatNumber(summary.output_tokens)} out${summary.reasoning_tokens ? ` · ${formatNumber(summary.reasoning_tokens)} reasoning` : ''}`}
        icon={Coins}
      />
      <StatCard
        label="Retries"
        value={formatNumber(summary.retries)}
        detail={summary.rate_limited_responses ? `${formatNumber(summary.rate_limited_responses)} rate-limited responses` : 'No rate limiting'}
        icon={RotateCw}
        tone={summary.rate_limited_responses ? 'warning' : 'neutral'}
      />
      <StatCard
        label="Revision rounds"
        value={count(summary.revisions)}
        detail={summary.approved === null ? 'No verdict logged yet' : summary.approved ? 'Approved by the critic' : 'Not approved by the critic'}
        icon={Waypoints}
        tone={summary.approved === null ? 'neutral' : summary.approved ? 'success' : 'warning'}
      />
      <StatCard label="Workflow time" value={duration(summary.workflow_duration_ms)} detail={summary.workflow_duration_ms === null ? 'Not finished yet' : 'Agents only, without queueing'} icon={Gauge} />
    </div>
  )
}

export { EMPTY }
