import type { LucideIcon } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { cn } from '@/utils/cn'

type StatTone = 'neutral' | 'success' | 'danger'

const ICON_TONES: Record<StatTone, string> = {
  neutral: 'text-muted-foreground',
  success: 'text-success',
  danger: 'text-danger',
}

interface StatCardProps {
  label: string
  value: string
  detail: string
  icon: LucideIcon
  tone?: StatTone
}

/** One statistic; render inside a <dl>. */
export function StatCard({ label, value, detail, icon: Icon, tone = 'neutral' }: StatCardProps) {
  return (
    <Card className="p-5">
      <dt className="flex items-center justify-between gap-3 text-sm font-medium text-muted-foreground">
        {label}
        <Icon className={cn('size-4 shrink-0', ICON_TONES[tone])} aria-hidden="true" />
      </dt>
      <dd className="mt-3 text-2xl font-semibold tracking-tight tabular-nums">{value}</dd>
      <dd className="mt-1 text-xs text-muted-foreground">{detail}</dd>
    </Card>
  )
}
