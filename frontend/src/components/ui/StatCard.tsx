import type { LucideIcon } from 'lucide-react'

import { cn } from '@/utils/cn'

import { Card } from './Card'
import { Skeleton } from './Skeleton'
import { TONE_TEXT, type Tone } from './tones'

interface StatCardProps {
  label: string
  value: string
  detail?: string
  icon?: LucideIcon
  tone?: Tone
  /** Shows skeletons instead of the value and detail. */
  loading?: boolean
}

/** One statistic (label, value, detail) as a self-contained description list. */
export function StatCard({ label, value, detail, icon: Icon, tone = 'neutral', loading = false }: StatCardProps) {
  return (
    <Card className="p-5" aria-busy={loading || undefined}>
      <dl>
        <dt className="flex items-center justify-between gap-3 text-label text-muted-foreground">
          {label}
          {Icon && <Icon className={cn('size-4 shrink-0', TONE_TEXT[tone])} aria-hidden="true" />}
        </dt>
        {loading ? (
          <dd>
            <Skeleton className="mt-3 h-8 w-20" />
            <Skeleton className="mt-2 h-3 w-28" />
          </dd>
        ) : (
          <>
            <dd className="mt-3 text-stat tabular-nums">{value}</dd>
            {detail && <dd className="mt-1 text-meta text-muted-foreground">{detail}</dd>}
          </>
        )}
      </dl>
    </Card>
  )
}
