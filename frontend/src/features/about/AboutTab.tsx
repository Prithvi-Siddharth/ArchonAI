import { Badge, Card, CardContent } from '@/components/ui'

import { APP_VERSION } from './about-tabs'
import { Bullets, Prose, Section } from './parts'

const STACK: ReadonlyArray<[string, string]> = [
  ['Interface', 'React and TypeScript'],
  ['API', 'FastAPI (Python)'],
  ['Agents', 'LangGraph'],
  ['Background jobs', 'Celery and Redis'],
  ['Storage', 'MySQL'],
]

function VersionCard() {
  return (
    <Card role="group" aria-label="Version">
      <CardContent className="space-y-4 py-5">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-meta text-muted-foreground">Version</p>
          <Badge tone="info" data-testid="app-version">
            v{APP_VERSION}
          </Badge>
        </div>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <div>
            <dt className="text-meta text-muted-foreground">License</dt>
            <dd className="mt-0.5 font-medium">MIT, free to use and modify</dd>
          </div>
          {STACK.map(([label, value]) => (
            <div key={label}>
              <dt className="text-meta text-muted-foreground">{label}</dt>
              <dd className="mt-0.5 font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

export function AboutTab() {
  return (
    <div className="space-y-6">
      <Prose>
        <Section title="What ArchonAI is">
          <p>
            ArchonAI turns a plain-English description of a system, such as “an e-commerce platform for 500,000 concurrent users”, into a reviewed AWS
            architecture. A team of AI agents, coordinated by LangGraph, does the work a small design review would: it analyses your requirements, designs
            the architecture, examines it from several angles, criticises it, and revises it until it holds up.
          </p>
          <p>The result is a structured recommendation, not a chat transcript.</p>
        </Section>
        <Section title="What you get for each request">
          <Bullets
            items={[
              'The AWS services your system needs, how they connect, and why each was chosen.',
              'Separate analyses of compute, database, networking, security and reliability.',
              'A monthly cost range with a per-service breakdown.',
              'A critic’s score and review, and how many revision rounds the design went through.',
              'A full written report you can download as Markdown, and a step-by-step trace of what each agent did.',
            ]}
          />
        </Section>
        <Section title="About this project">
          <p>
            ArchonAI is a portfolio project built to show agentic AI system design: a graph of cooperating agents with a real decision loop, rather than a
            single prompt wrapped in a chat window. Treat its output as a well-organised starting point for a design discussion, not as a final answer.
          </p>
        </Section>
      </Prose>
      <VersionCard />
    </div>
  )
}
