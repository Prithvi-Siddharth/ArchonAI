import { Boxes, Workflow } from 'lucide-react'

import { Badge, Card, CardContent, CardHeader, EmptyState, SectionHeader } from '@/components/ui'
import type { AWSService, ArchitectureResult, DataFlowStep } from '@/types/api'

import { DataFlowDiagram } from './DataFlowDiagram'

function DataFlowSteps({ steps }: { steps: DataFlowStep[] }) {
  return (
    <Card>
      <CardHeader title="Data-flow steps" description="Every step as returned, in order." />
      <CardContent>
        <ol aria-label="Data-flow steps" className="space-y-3">
          {steps.map((step, index) => (
            <li key={`${step.step}-${index}`} className="flex gap-3">
              <Badge className="mt-px h-5 shrink-0 font-mono" aria-hidden="true">
                {step.step}
              </Badge>
              <div className="min-w-0">
                <p className="font-medium break-words">
                  <span className="sr-only">Step {step.step}: </span>
                  {step.source}
                  <span aria-hidden="true" className="px-1.5 text-muted-foreground">
                    →
                  </span>
                  <span className="sr-only"> to </span>
                  {step.destination}
                </p>
                <p className="text-muted-foreground">{step.description}</p>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}

/** Services grouped by their (free-text) category, in the order categories first appear. */
function groupByCategory(services: AWSService[]): Array<[string, AWSService[]]> {
  const groups = new Map<string, AWSService[]>()
  for (const service of services) groups.set(service.category, [...(groups.get(service.category) ?? []), service])
  return [...groups.entries()]
}

function Services({ services }: { services: AWSService[] }) {
  const groups = groupByCategory(services)
  return (
    <section aria-labelledby="architecture-services" className="space-y-4">
      <SectionHeader
        id="architecture-services"
        title="AWS services"
        description={
          services.length > 0
            ? `${services.length} ${services.length === 1 ? 'service' : 'services'} in ${groups.length} ${groups.length === 1 ? 'category' : 'categories'}, as returned. Services are listed whether or not a data-flow step names them.`
            : undefined
        }
      />
      {services.length === 0 ? (
        <Card>
          <EmptyState icon={Boxes} title="No services listed" description="This architecture's result contains no AWS services." />
        </Card>
      ) : (
        <div className="space-y-6">
          {groups.map(([category, members]) => (
            <div key={category} className="space-y-3">
              <h3 className="flex items-center gap-2 text-card-title">
                {category}
                <Badge>{members.length}</Badge>
              </h3>
              <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {members.map((service, index) => (
                  <li key={`${service.name}-${index}`} className="min-w-0">
                    <Card className="h-full">
                      <CardContent className="space-y-3 py-4">
                        <div className="flex items-start justify-between gap-3">
                          <h4 className="text-card-title break-words">{service.name}</h4>
                          <Badge className="shrink-0">{service.category}</Badge>
                        </div>
                        <dl className="space-y-2">
                          <div>
                            <dt className="text-meta font-medium text-muted-foreground uppercase">Purpose</dt>
                            <dd>{service.purpose}</dd>
                          </div>
                          <div>
                            <dt className="text-meta font-medium text-muted-foreground uppercase">Justification</dt>
                            <dd className="text-muted-foreground">{service.justification}</dd>
                          </div>
                        </dl>
                      </CardContent>
                    </Card>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export function ArchitectureTab({ result }: { result: ArchitectureResult }) {
  const { summary, data_flow: steps = [], services = [] } = result.architecture
  const endpoints = new Set(steps.flatMap((s) => [s.source, s.destination])).size

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Architecture summary" />
        <CardContent>
          <p className="whitespace-pre-line">{summary}</p>
        </CardContent>
      </Card>

      {steps.length === 0 ? (
        <Card>
          <EmptyState
            icon={Workflow}
            title="No data flow recorded"
            description="This architecture's result has no data-flow steps, so there is nothing to draw."
          />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader
              title="Data-flow diagram"
              description={`${steps.length} ${steps.length === 1 ? 'step' : 'steps'} between ${endpoints} endpoints. Endpoint labels are shown exactly as the backend wrote them.`}
            />
            <CardContent>
              <DataFlowDiagram steps={steps} services={services} />
            </CardContent>
          </Card>
          <DataFlowSteps steps={steps} />
        </>
      )}

      <Services services={services} />
    </div>
  )
}
