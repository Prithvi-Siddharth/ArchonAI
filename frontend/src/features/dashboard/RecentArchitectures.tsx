import { ArrowRight, Layers } from 'lucide-react'
import { Link } from 'react-router'

import { buttonVariants } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { JobStatusBadge } from '@/features/architectures/JobStatusBadge'
import type { ArchitectureSummary } from '@/types/architecture'
import { formatDateTime, formatRelativeTime, shortId } from '@/utils/format'

const EMPTY = '—'

export function RecentArchitectures({ items }: { items: ArchitectureSummary[] }) {
  return (
    <Card>
      <CardHeader
        title="Recent architectures"
        description="The latest architecture generation jobs."
        action={
          <Link to="/architectures/history" className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
            View all
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        }
      />

      {items.length === 0 ? (
        <EmptyState
          icon={Layers}
          title="No architectures yet"
          description="Architectures you generate will be listed here."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th scope="col" className="px-5 py-2.5 font-medium">
                  Request
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium">
                  Status
                </th>
                <th scope="col" className="hidden px-3 py-2.5 text-right font-medium md:table-cell">
                  Services
                </th>
                <th scope="col" className="hidden px-3 py-2.5 text-right font-medium md:table-cell">
                  Score
                </th>
                <th scope="col" className="hidden px-5 py-2.5 text-right font-medium sm:table-cell">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((item) => {
                const created = formatRelativeTime(item.createdAt)
                return (
                  <tr key={item.jobId}>
                    {/* w-full + max-w-0 lets the request text truncate inside the table. */}
                    <td className="w-full max-w-0 px-5 py-3">
                      <p className="truncate font-medium" title={item.request}>
                        {item.request}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        <span className="font-mono">{shortId(item.jobId)}</span>
                        <span className="sm:hidden"> · {created}</span>
                      </p>
                    </td>
                    <td className="px-3 py-3">
                      <JobStatusBadge status={item.status} />
                    </td>
                    <td className="hidden px-3 py-3 text-right tabular-nums md:table-cell">
                      {item.serviceCount ?? EMPTY}
                    </td>
                    <td className="hidden px-3 py-3 text-right tabular-nums md:table-cell">
                      {item.criticScore ?? EMPTY}
                    </td>
                    <td className="hidden px-5 py-3 text-right whitespace-nowrap text-muted-foreground sm:table-cell">
                      <time dateTime={item.createdAt} title={formatDateTime(item.createdAt)}>
                        {created}
                      </time>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
