import { Card, CardContent } from '@/components/ui'

import { Bullets, InlineLink, Prose, Section } from './parts'

export function HowToUseTab() {
  const steps = [
    <>
      <strong className="font-medium text-foreground">Create an account or sign in.</strong> Your jobs and results belong to your account, and only you can see them.
    </>,
    <>
      <strong className="font-medium text-foreground">Optional: use your own AI provider.</strong> Add your own Groq or Google Gemini key on{' '}
      <InlineLink to="/byok">Bring Your Own Key</InlineLink>. If you skip this, your jobs use the provider set up on the server.
    </>,
    <>
      <strong className="font-medium text-foreground">Describe your system.</strong> Open <InlineLink to="/architectures/new">New Architecture</InlineLink>, write
      your request (10 to 4,000 characters) and submit it, or start from one of the example prompts.
    </>,
    <>
      <strong className="font-medium text-foreground">Follow its progress.</strong> The design runs in the background and usually takes several minutes. Watch it on{' '}
      <InlineLink to="/activity">Activity</InlineLink>, or leave and come back; nothing is lost.
    </>,
    <>
      <strong className="font-medium text-foreground">Read the results.</strong> When a job succeeds, open its results: overview, architecture, cost, review,
      analyses, report and trace. The report can be downloaded as a Markdown file.
    </>,
    <>
      <strong className="font-medium text-foreground">Find it again later.</strong> Every job is kept in{' '}
      <InlineLink to="/architectures/history">Architecture History</InlineLink>, where you can search by request text or job ID and filter by status.
    </>,
  ]

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="py-6">
          <ol aria-label="Steps" className="space-y-5">
            {steps.map((step, index) => (
              <li key={index} className="flex gap-4">
                <span
                  className="flex size-7 shrink-0 items-center justify-center rounded-full border border-border font-mono text-meta text-muted-foreground"
                  aria-hidden="true"
                >
                  {index + 1}
                </span>
                <p className="min-w-0 pt-0.5 leading-6 text-muted-foreground">{step}</p>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
      <Prose>
        <Section title="Writing a good request">
          <Bullets
            items={[
              'Say what the system is and who uses it, for example “a video streaming platform for 2 million daily users”.',
              'Give numbers where you have them: users, requests per second, data volume, how long data must be kept.',
              'Name constraints that matter: latency targets, regions, compliance rules such as PCI-DSS or HIPAA, or a budget.',
              'Mention anything the design must reuse or avoid.',
            ]}
          />
        </Section>
        <Section title="If a job fails">
          <Bullets
            items={[
              'A temporary problem, such as the provider’s rate limit, is retried automatically once. The Activity page shows that it is waiting to retry.',
              'If the provider rejects your key, check it on the Bring Your Own Key page, or remove it to use the server’s provider.',
              'Any other failure shows its message on the job page. You can submit the request again.',
            ]}
          />
        </Section>
      </Prose>
    </div>
  )
}
