import {
  CircleCheck,
  CircleX,
  ClipboardList,
  GitBranch,
  ListChecks,
  MessageSquareWarning,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge, Card, CardContent, CardHeader, EmptyState, Progress } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import type { ArchitectureResult } from '@/types/api'
import { cn } from '@/utils/cn'

import { SeverityBadge, severityCounts } from './SeverityBadge'

function SummaryItem({ label, icon: Icon, children }: { label: string; icon: LucideIcon; children: ReactNode }) {
  return (
    <div className="min-w-0 space-y-1.5">
      <dt className="flex items-center gap-1.5 text-label text-muted-foreground">
        <Icon className="size-4" aria-hidden="true" />
        {label}
      </dt>
      <dd className="flex flex-wrap items-center gap-1.5">{children}</dd>
    </div>
  )
}

function BulletList({ items, marker }: { items: string[]; marker?: ReactNode }) {
  return (
    <ul className="space-y-2.5">
      {items.map((item, index) => (
        <li key={index} className="flex gap-3">
          {marker ?? <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />}
          <span className="min-w-0 break-words">{item}</span>
        </li>
      ))}
    </ul>
  )
}

export function ReviewTab({ result }: { result: ArchitectureResult }) {
  const { critic_review: critic, validation_results: validation, revision_count, max_revisions_reached, architecture } = result
  const issues = critic.issues ?? []
  const strengths = critic.strengths ?? []
  const requiredChanges = critic.required_changes ?? []
  const validationIssues = validation.issues ?? []
  const openRecommendations = result.final_report.open_recommendations ?? []
  const changeLog = architecture.change_log ?? []

  return (
    <div className="space-y-6">
      {/* 1. Overall review summary. */}
      <Card>
        <CardHeader title="Review summary" />
        <CardContent>
          <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryItem label="Critic decision" icon={result.approved ? CircleCheck : CircleX}>
              <Badge tone={result.approved ? 'success' : 'warning'}>{result.approved ? 'Approved' : 'Not approved'}</Badge>
            </SummaryItem>
            <SummaryItem label="Critic score" icon={ListChecks}>
              <span className="text-card-title tabular-nums">{critic.score}/100</span>
            </SummaryItem>
            <SummaryItem label="Validation" icon={ShieldCheck}>
              <Badge tone={validation.passed ? 'success' : 'danger'}>{validation.passed ? 'Passed' : 'Failed'}</Badge>
              <span className="text-meta text-muted-foreground">
                {validationIssues.length} {validationIssues.length === 1 ? 'issue' : 'issues'}
              </span>
            </SummaryItem>
            <SummaryItem label="Revisions" icon={GitBranch}>
              <span className="tabular-nums">
                {revision_count} {revision_count === 1 ? 'round' : 'rounds'} · version {architecture.version}
              </span>
              {max_revisions_reached && <Badge tone="warning">Limit reached</Badge>}
            </SummaryItem>
          </dl>
        </CardContent>
      </Card>

      {/* 2. Critic score and approval. */}
      <Card>
        <CardHeader title="Critic score" description="The critic's overall quality score. Approval is a separate decision." />
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-stat tabular-nums">{critic.score}</span>
            <span className="text-muted-foreground">out of 100</span>
            <Badge tone={critic.approved ? 'success' : 'warning'} className="ml-auto">
              {critic.approved ? 'Approved by the critic' : 'Not approved by the critic'}
            </Badge>
          </div>
          <Progress label="Critic score" hideLabel value={critic.score} max={100} tone={critic.approved ? 'success' : 'warning'} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 3. Strengths. */}
        <Card className="self-start">
          <CardHeader title="Strengths" description="What the critic found the design does well." />
          {strengths.length === 0 ? (
            <EmptyState compact icon={Sparkles} title="No strengths listed" description="The critic did not list any." />
          ) : (
            <CardContent>
              <BulletList items={strengths} marker={<CircleCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />} />
            </CardContent>
          )}
        </Card>

        {/* 4. Critic issues. */}
        <Card className="min-w-0 self-start">
          <CardHeader
            title="Critic issues"
            description={issues.length > 0 ? `${severityCounts(issues.map((i) => i.severity))}, in the order the critic listed them.` : undefined}
          />
          {issues.length === 0 ? (
            <EmptyState compact icon={MessageSquareWarning} title="No issues raised" description="The critic did not report any issues." />
          ) : (
            <ul className="divide-y divide-border" aria-label="Critic issues">
              {issues.map((issue, index) => (
                <li key={index} className="space-y-1.5 px-5 py-3" data-severity={issue.severity}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <SeverityBadge severity={issue.severity} />
                    <Badge>{issue.category}</Badge>
                  </div>
                  <p className="break-words">{issue.issue}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* 5. Required changes. */}
      <Card>
        <CardHeader title="Required changes" description="Changes the critic required for approval, in its own words." />
        {requiredChanges.length === 0 ? (
          <EmptyState compact icon={ClipboardList} title="No required changes" description="The critic did not require any changes." />
        ) : (
          <CardContent>
            <ol className="list-decimal space-y-2.5 pl-5 marker:text-muted-foreground">
              {requiredChanges.map((change, index) => (
                <li key={index} className="pl-1 break-words">
                  {change}
                </li>
              ))}
            </ol>
          </CardContent>
        )}
      </Card>

      {/* 6. Validation results. */}
      <Card>
        <CardHeader
          title="Validation results"
          description="Findings from the rule-based validator, which checks the design against a fixed set of rules."
          action={<Badge tone={validation.passed ? 'success' : 'danger'}>{validation.passed ? 'Passed' : 'Failed'}</Badge>}
        />
        {validationIssues.length === 0 ? (
          validation.passed ? (
            <EmptyState
              compact
              icon={ShieldCheck}
              title="No validation issues reported"
              description="The validator's rules found no problems. This covers only the rules it checks, not every possible AWS concern."
            />
          ) : (
            <EmptyState compact tone="danger" icon={CircleX} title="Validation failed" description="Validation did not pass, but no specific issues were listed." />
          )
        ) : (
          <ul className="divide-y divide-border" aria-label="Validation issues">
            {validationIssues.map((issue, index) => (
              <li key={index} className="space-y-1.5 px-5 py-3" data-severity={issue.severity}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <SeverityBadge severity={issue.severity} />
                  <code className="rounded-sm bg-surface-muted px-1.5 py-0.5 font-mono text-meta break-all">{issue.rule}</code>
                </div>
                <p className="break-words">{issue.message}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* 7. Open recommendations: distinct from issues and failures. */}
      <section aria-labelledby="open-recommendations" className={cn('rounded-lg border', openRecommendations.length > 0 ? TONE_SOFT.info : 'border-border bg-surface')}>
        <div className="px-5 pt-4 pb-3">
          <h2 id="open-recommendations" className="flex items-center gap-2 text-card-title text-foreground">
            <ClipboardList className="size-4" aria-hidden="true" />
            Open recommendations
          </h2>
          <p className="mt-0.5 text-muted-foreground">
            Changes requested or proposed during review that the final architecture does not include. Some may repeat a
            required change above.
          </p>
        </div>
        {openRecommendations.length === 0 ? (
          <EmptyState compact icon={ClipboardList} title="No open recommendations" description="Everything requested or proposed is in the final architecture." />
        ) : (
          <div className="px-5 pb-4 text-foreground">
            <BulletList items={openRecommendations} />
          </div>
        )}
      </section>

      {/* 8. Revision history. */}
      <Card>
        <CardHeader title="Revision history" />
        <CardContent className="space-y-4">
          <dl className="grid gap-4 sm:grid-cols-3">
            <div>
              <dt className="text-label text-muted-foreground">Revision rounds</dt>
              <dd className="text-card-title tabular-nums">{revision_count}</dd>
            </div>
            <div>
              <dt className="text-label text-muted-foreground">Architecture version</dt>
              <dd className="text-card-title tabular-nums">{architecture.version}</dd>
            </div>
            <div>
              <dt className="text-label text-muted-foreground">Revision limit</dt>
              <dd>{max_revisions_reached ? <Badge tone="warning">Reached</Badge> : <Badge>Not reached</Badge>}</dd>
            </div>
          </dl>
          <p className="text-meta text-muted-foreground">
            The version counts accepted revisions only, so it can stay the same when a revision round is rejected.
          </p>
          <div>
            <h3 className="text-label">Change log</h3>
            <p className="text-meta text-muted-foreground">
              Entries as returned. The backend does not record which revision or time each entry belongs to.
            </p>
            {changeLog.length === 0 ? (
              <p className="mt-2 text-muted-foreground">No change-log entries.</p>
            ) : (
              <div className="mt-2.5">
                <BulletList items={changeLog} />
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
