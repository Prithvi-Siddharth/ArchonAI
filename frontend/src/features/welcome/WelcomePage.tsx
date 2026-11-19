import { ArrowRight, Bot, Check, FileText, MessageSquareText, Network, ShieldCheck, Wallet, type LucideIcon } from 'lucide-react'
import { Link, Navigate } from 'react-router'

import { Brand } from '@/components/layout/Sidebar'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { buttonVariants, Card } from '@/components/ui'
import { useMe } from '@/features/auth/useAuth'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/utils/cn'

const FEATURES: ReadonlyArray<{ icon: LucideIcon; title: string; text: string }> = [
  {
    icon: Network,
    title: 'Architecture design',
    text: 'The AWS services your system needs, how they connect, and the reasoning behind each choice.',
  },
  {
    icon: ShieldCheck,
    title: 'Critic review',
    text: 'A reviewer agent scores the design and sends it back for revision when it falls short, alongside detailed analyses.',
  },
  {
    icon: Wallet,
    title: 'Cost estimate',
    text: 'A monthly cost range with a per-service breakdown, so you can see where the money goes.',
  },
  {
    icon: FileText,
    title: 'Report and trace',
    text: 'A full written report you can download as Markdown, and a step-by-step trace of what each agent did.',
  },
]

const STEPS: ReadonlyArray<{ title: string; text: string }> = [
  { title: 'Describe your system', text: 'Write what you need in plain language: users, traffic, data, and any requirements like latency or compliance.' },
  { title: 'The agents get to work', text: 'Your request runs in the background and usually takes several minutes. Follow its progress live on the Activity page.' },
  { title: 'Explore the results', text: 'Open the design, review, cost and report. Every job is saved to your account in Architecture History.' },
]

/** A static picture of a finished job, to show what the app produces. Purely illustrative. */
function ExampleJob() {
  return (
    <figure className="w-full">
      <Card className="p-5" aria-hidden="true">
        <p className="text-meta text-muted-foreground">Request</p>
        <p className="mt-1 font-medium">Design a video streaming platform for 2 million daily users with 4K playback and global delivery.</p>
        <ol className="mt-5 grid grid-cols-3">
          {['Queued', 'Running', 'Completed'].map((label, index) => (
            <li key={label} className="relative flex flex-col items-center text-center">
              {index < 2 && <span className="absolute top-4 right-[calc(-50%+1.25rem)] left-[calc(50%+1.25rem)] h-px bg-success/50" />}
              <span className="flex size-8 items-center justify-center rounded-full border border-success/30 bg-success/10 text-success">
                <Check className="size-4" />
              </span>
              <span className="mt-2 text-label">{label}</span>
            </li>
          ))}
        </ol>
        <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-border pt-4">
          {[
            ['AWS services', '9'],
            ['Critic score', '82/100'],
            ['Version', '2'],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-meta text-muted-foreground">{label}</dt>
              <dd className="mt-0.5 font-medium tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 flex items-center gap-2 rounded-md bg-surface-muted px-3 py-2 text-meta text-muted-foreground">
          <Bot className="size-3.5 text-primary" />
          Designed, reviewed, costed and reported by agents
        </div>
      </Card>
      <figcaption className="mt-2 text-center text-meta text-muted-foreground">An example of a finished job</figcaption>
    </figure>
  )
}

/** Public landing page for signed-out visitors, with the way in to sign in or create an account. */
export function WelcomePage() {
  useDocumentTitle('Welcome')
  const me = useMe()
  // Already signed in: straight to the app.
  if (me.data) return <Navigate to="/dashboard" replace />

  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="sticky top-0 z-10 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-header max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          <Brand />
          <nav aria-label="Account" className="flex items-center gap-1 sm:gap-2">
            <ThemeToggle />
            <Link to="/login" className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
              Sign in
            </Link>
            <Link to="/register" className={cn(buttonVariants({ size: 'sm' }), 'max-sm:hidden')}>
              Create account
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-12 sm:px-6 sm:py-16 lg:grid-cols-[minmax(0,1fr)_26rem] lg:gap-16 lg:py-24">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-meta text-muted-foreground">
              <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
              AWS architecture design with AI agents
            </p>
            <h1 className="mt-5 text-3xl font-semibold tracking-tight text-balance sm:text-4xl lg:text-5xl">
              Turn your requirements into a reviewed AWS architecture
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground">
              Describe the system you need in plain language. ArchonAI&apos;s agents analyze the requirements, design an AWS
              architecture, review and revise it, estimate its monthly cost, and write it all up in a report.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/register" className={buttonVariants({ size: 'lg' })}>
                Get started
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
              <Link to="/login" className={buttonVariants({ variant: 'outline', size: 'lg' })}>
                Sign in
              </Link>
            </div>
          </div>
          <ExampleJob />
        </section>

        <section aria-labelledby="welcome-features" className="border-t border-border bg-surface-muted/40">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-16">
            <h2 id="welcome-features" className="text-2xl font-semibold tracking-tight">
              What you get for every request
            </h2>
            <p className="mt-2 max-w-2xl text-muted-foreground">Each finished job opens to a set of results you can explore tab by tab.</p>
            <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <li key={title}>
                  <Card className="h-full p-5">
                    <span className="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <Icon className="size-5" aria-hidden="true" />
                    </span>
                    <h3 className="mt-4 text-card-title">{title}</h3>
                    <p className="mt-1.5 text-muted-foreground">{text}</p>
                  </Card>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="welcome-steps" className="border-t border-border">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-16">
            <h2 id="welcome-steps" className="text-2xl font-semibold tracking-tight">
              How it works
            </h2>
            <ol className="mt-8 grid gap-6 md:grid-cols-3">
              {STEPS.map(({ title, text }, index) => (
                <li key={title} className="flex gap-4">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border font-mono text-meta" aria-hidden="true">
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="text-card-title">{title}</h3>
                    <p className="mt-1.5 text-muted-foreground">{text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section aria-labelledby="welcome-cta" className="border-t border-border">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-16">
            <Card className="flex flex-col items-start gap-5 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
              <div className="flex items-start gap-3">
                <MessageSquareText className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
                <div>
                  <h2 id="welcome-cta" className="text-section-title">
                    Ready to design your first architecture?
                  </h2>
                  <p className="mt-1 text-muted-foreground">Create an account and submit your first request in a minute.</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-3">
                <Link to="/register" className={buttonVariants()}>
                  Create account
                </Link>
                <Link to="/login" className={buttonVariants({ variant: 'outline' })}>
                  Sign in
                </Link>
              </div>
            </Card>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-6 text-meta text-muted-foreground sm:flex-row sm:justify-between sm:px-6">
          <p>ArchonAI · AWS architecture design</p>
          <p>Cost figures are educational estimates, not AWS quotes.</p>
        </div>
      </footer>
    </div>
  )
}
