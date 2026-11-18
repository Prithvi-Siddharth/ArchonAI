import { Info, Lightbulb, Scale, Wallet, type LucideIcon } from 'lucide-react'

import { Badge, Card, CardContent, CardHeader, EmptyState } from '@/components/ui'
import type { Tone } from '@/components/ui/tones'
import type { ArchitectureResult } from '@/types/api'
import { cn } from '@/utils/cn'

import { costLevel, type CostLevel } from './cost-levels'

const LEVEL_TONE: Record<CostLevel, Tone> = { 1: 'neutral', 2: 'info', 3: 'warning' }

/** Three-step meter for a recognised low/medium/high value (decorative; the text carries the meaning). */
function LevelMeter({ level }: { level: CostLevel }) {
  return (
    <span className="flex gap-1" aria-hidden="true">
      {[1, 2, 3].map((step) => (
        <span key={step} className={cn('h-2 w-6 rounded-full', step <= level ? 'bg-primary' : 'bg-surface-muted')} />
      ))}
    </span>
  )
}

function TextList({ items, emptyIcon, emptyTitle }: { items: string[]; emptyIcon: LucideIcon; emptyTitle: string }) {
  if (items.length === 0) {
    return <EmptyState compact icon={emptyIcon} title={emptyTitle} description="The cost analysis did not include any." />
  }
  return (
    <CardContent>
      <ul className="space-y-2.5">
        {items.map((item, index) => (
          <li key={index} className="flex gap-3">
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
            <span className="min-w-0 break-words">{item}</span>
          </li>
        ))}
      </ul>
    </CardContent>
  )
}

export function CostTab({ result }: { result: ArchitectureResult }) {
  const {
    estimated_monthly_range: range,
    major_cost_drivers: drivers = [],
    relative_cost_breakdown: breakdown = {},
    optimizations = [],
    trade_offs: tradeOffs = [],
    disclaimer,
  } = result.cost_analysis
  const areas = Object.entries(breakdown)
  const allRecognised = areas.every(([, value]) => costLevel(value) !== null)

  return (
    <div className="space-y-6">
      {/* 1. Estimated monthly cost: the backend's text, unparsed. */}
      <Card>
        <CardContent className="space-y-3 py-5">
          <div className="flex flex-wrap items-center gap-2">
            <Wallet className="size-4 text-muted-foreground" aria-hidden="true" />
            <h2 className="text-label text-muted-foreground">Estimated monthly cost</h2>
            <Badge tone="warning">Educational estimate</Badge>
          </div>
          <p className="text-stat break-words">{range.trim() || 'Not provided'}</p>
          <p className="text-muted-foreground">
            An order-of-magnitude figure from the cost agent, shown exactly as returned. It is not a quote or real-time
            AWS pricing; see the disclaimer below.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        {/* 2. Major cost drivers. */}
        <Card className="self-start">
          <CardHeader title="Major cost drivers" description="The parts of the design that drive the most cost." />
          {drivers.length === 0 ? (
            <EmptyState compact icon={Wallet} title="No cost drivers listed" description="The cost analysis did not name any." />
          ) : (
            <CardContent>
              <ul className="flex flex-wrap gap-2">
                {drivers.map((driver, index) => (
                  <li key={index} className="rounded-md border border-border bg-surface-muted/50 px-3 py-1.5 text-label break-words">
                    {driver}
                  </li>
                ))}
              </ul>
            </CardContent>
          )}
        </Card>

        {/* 3. Relative cost breakdown: ordinal levels, never amounts or percentages. */}
        <Card className="min-w-0 self-start">
          <CardHeader
            title="Relative cost breakdown"
            description={
              allRecognised
                ? 'How each area compares, on the low / medium / high scale the cost agent used. A ranking, not amounts or percentages of spend.'
                : 'How each area compares, as the cost agent described it. A ranking, not amounts or percentages of spend.'
            }
          />
          {areas.length === 0 ? (
            <EmptyState compact icon={Scale} title="No breakdown provided" description="The cost analysis did not rank any areas." />
          ) : (
            <table className="w-full">
              <caption className="sr-only">Relative cost breakdown by area</caption>
              <thead>
                <tr className="border-b border-border text-left text-meta text-muted-foreground">
                  <th scope="col" className="py-2.5 pr-3 pl-5 font-medium">
                    Area
                  </th>
                  <th scope="col" className="px-3 py-2.5 font-medium">
                    Relative weight
                  </th>
                  <th scope="col" className="hidden py-2.5 pr-5 pl-3 font-medium sm:table-cell">
                    <span className="sr-only">Scale</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {areas.map(([area, value]) => {
                  const level = costLevel(value)
                  return (
                    <tr key={area} data-area={area} data-level={level ?? 'text'}>
                      <th scope="row" className="py-2.5 pr-3 pl-5 text-left font-medium break-words">
                        {area}
                      </th>
                      <td className="px-3 py-2.5">
                        <Badge tone={level ? LEVEL_TONE[level] : 'neutral'}>{value}</Badge>
                      </td>
                      <td className="hidden py-2.5 pr-5 pl-3 sm:table-cell">
                        {level ? <LevelMeter level={level} /> : <span className="text-meta text-muted-foreground">Not on the low / medium / high scale</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 4. Optimizations. */}
        <Card className="self-start">
          <CardHeader
            title="Cost optimization recommendations"
            description="Suggestions from the cost agent. Actual savings depend on usage and are not guaranteed."
          />
          <TextList items={optimizations} emptyIcon={Lightbulb} emptyTitle="No optimizations suggested" />
        </Card>

        {/* 5. Trade-offs. */}
        <Card className="self-start">
          <CardHeader
            title="Architectural trade-offs"
            description="Cost-versus-capability choices in this design. These are trade-offs, not necessarily savings."
          />
          <TextList items={tradeOffs} emptyIcon={Scale} emptyTitle="No trade-offs listed" />
        </Card>
      </div>

      {/* 6. Disclaimer, verbatim. */}
      <section aria-labelledby="cost-disclaimer" className="flex gap-3 rounded-lg border border-border bg-surface-muted/40 px-5 py-4">
        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0">
          <h2 id="cost-disclaimer" className="text-card-title">
            Disclaimer
          </h2>
          <p className="mt-0.5 text-muted-foreground">
            {disclaimer.trim() || 'No disclaimer was provided. Treat this as an educational estimate, not a quote.'}
          </p>
        </div>
      </section>
    </div>
  )
}
