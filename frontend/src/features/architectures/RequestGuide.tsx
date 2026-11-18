import { Card, CardContent, CardHeader } from '@/components/ui'

/** What the planner looks for in a request (the fields of the backend's Requirements model). */
const TOPICS = [
  ['Application', 'What it is and its main features'],
  ['Users and load', 'Total users and peak concurrent users'],
  ['Traffic pattern', 'Steady, spiky or seasonal'],
  ['Performance', 'Latency and availability targets'],
  ['Data', 'Storage and database needs'],
  ['Security', 'Compliance such as PCI-DSS or HIPAA'],
  ['Regions', 'Where your users are'],
  ['Budget', 'A monthly cost limit, if any'],
] as const

export function RequestGuide() {
  return (
    <Card className="self-start">
      <CardHeader title="What to include" description="Anything you leave out is inferred or marked not specified." />
      <CardContent>
        <dl className="space-y-3">
          {TOPICS.map(([topic, detail]) => (
            <div key={topic}>
              <dt className="text-label">{topic}</dt>
              <dd className="text-meta text-muted-foreground">{detail}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
