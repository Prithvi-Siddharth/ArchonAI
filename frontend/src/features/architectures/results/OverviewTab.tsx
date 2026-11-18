import { ChevronDown } from 'lucide-react'

import { Badge, Card, CardContent, CardHeader } from '@/components/ui'
import type { ArchitectureResult } from '@/types/api'

import { PLAN_AREAS, REQUIREMENT_ROWS, TRAFFIC_PATTERN_LABEL } from './result-format'

function TextCard({ title, text }: { title: string; text: string }) {
  return (
    <Card>
      <CardHeader title={title} />
      <CardContent>
        <p className="whitespace-pre-line">{text}</p>
      </CardContent>
    </Card>
  )
}

function ListCard({ title, description, items }: { title: string; description: string; items: string[] }) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <CardContent>
        {items.length > 0 ? (
          <ul className="list-disc space-y-1.5 pl-5 marker:text-muted-foreground">
            {items.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">None recorded.</p>
        )}
      </CardContent>
    </Card>
  )
}

export function OverviewTab({ result }: { result: ArchitectureResult }) {
  const { final_report, architecture, requirements, architecture_plan } = result

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <TextCard title="Executive summary" text={final_report.executive_summary} />
        <TextCard title="Architecture summary" text={architecture.summary} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="min-w-0 self-start">
          <CardHeader title="Key requirements" description="As extracted from the request by the requirements analyzer." />
          <table className="w-full">
            <caption className="sr-only">Key requirements</caption>
            <tbody className="divide-y divide-border">
              <tr>
                <th scope="row" className="w-32 py-2.5 pr-4 pl-5 text-left align-top font-medium text-muted-foreground sm:w-44">
                  Traffic pattern
                </th>
                <td className="py-2.5 pr-5 align-top">
                  <Badge tone="info">{TRAFFIC_PATTERN_LABEL[requirements.traffic_pattern]}</Badge>
                </td>
              </tr>
              {REQUIREMENT_ROWS.map(([field, label]) => (
                <tr key={field}>
                  <th scope="row" className="w-32 py-2.5 pr-4 pl-5 text-left align-top font-medium text-muted-foreground sm:w-44">
                    {label}
                  </th>
                  <td className="py-2.5 pr-5 align-top break-words">{requirements[field]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <div className="min-w-0 space-y-6">
          <ListCard
            title="Explicit requirements"
            description="What the request stated."
            items={requirements.explicit_requirements}
          />
          <ListCard
            title="Inferred assumptions"
            description="What the analyst assumed. Worth checking."
            items={requirements.inferred_assumptions}
          />
        </div>
      </div>

      <details className="group rounded-lg border border-border bg-surface shadow-card">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-lg px-5 py-4 [&::-webkit-details-marker]:hidden">
          <div className="min-w-0">
            <h2 className="text-card-title">Architecture plan</h2>
            <p className="mt-0.5 text-muted-foreground">
              How the planner approached each of the {PLAN_AREAS.length} concerns before choosing services.
            </p>
          </div>
          <ChevronDown
            className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180 motion-reduce:transition-none"
            aria-hidden="true"
          />
        </summary>
        <dl className="grid gap-x-8 gap-y-4 border-t border-border px-5 py-4 sm:grid-cols-2">
          {PLAN_AREAS.map(([field, label]) => (
            <div key={field} className="min-w-0">
              <dt className="text-label">{label}</dt>
              <dd className="mt-0.5 text-muted-foreground">{architecture_plan[field]}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  )
}
