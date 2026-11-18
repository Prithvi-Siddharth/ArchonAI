import { ClipboardList, FileDown, FileText, Gauge, Scale, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button, Card, CardContent, CardHeader, EmptyState } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import type { ArchitectureResult, FinalReport } from '@/types/api'
import { cn } from '@/utils/cn'
import { downloadText } from '@/utils/download'

import { isReportEmpty, reportList, reportText, sectionTitle, type ReportListKey, type ReportTextKey } from './report-content'
import { reportFilename, reportToMarkdown } from './report-markdown'

const headingId = (key: string) => `report-${key.replace(/_/g, '-')}`

/** Report prose: original wording, paragraph and line breaks kept, nothing truncated. */
function Prose({ text, className }: { text: string; className?: string }) {
  return <p className={cn('max-w-readable leading-6 break-words whitespace-pre-line', className)}>{text}</p>
}

function TextSection({ report, field }: { report: FinalReport | undefined; field: ReportTextKey }) {
  const text = reportText(report, field)
  return (
    <section aria-labelledby={headingId(field)} className="min-w-0 space-y-1.5">
      <h3 id={headingId(field)} className="text-label">
        {sectionTitle(field)}
      </h3>
      {text ? <Prose text={text} /> : <p className="text-muted-foreground italic">Not provided in this report.</p>}
    </section>
  )
}

function ListSection({ report, field, icon: Icon, iconClass }: { report: FinalReport | undefined; field: ReportListKey; icon: LucideIcon; iconClass: string }) {
  const items = reportList(report, field)
  return (
    <section aria-labelledby={headingId(field)} className="min-w-0 space-y-2">
      <h3 id={headingId(field)} className="text-label">
        {sectionTitle(field)}
      </h3>
      {items.length > 0 ? (
        <ul className="space-y-2" aria-labelledby={headingId(field)}>
          {items.map((item, index) => (
            <li key={index} className="flex gap-2.5">
              <Icon className={cn('mt-1 size-4 shrink-0', iconClass)} aria-hidden="true" />
              <Prose text={item} className="min-w-0" />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground italic">None listed in this report.</p>
      )}
    </section>
  )
}

function Group({ title, description, children, className }: { title: string; description?: string; children: ReactNode; className?: string }) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <CardContent className={cn('py-5', className)}>{children}</CardContent>
    </Card>
  )
}

export function ReportTab({ result, jobId }: { result: ArchitectureResult; jobId?: string }) {
  // Widened on purpose: a stored result could lack the report even though the type says otherwise.
  const report = result.final_report as FinalReport | undefined

  if (isReportEmpty(report)) {
    return (
      <Card>
        <EmptyState icon={FileText} title="No final report" description="This result contains no final report content." />
      </Card>
    )
  }

  const executive = reportText(report, 'executive_summary')
  const finalRecommendations = reportList(report, 'final_recommendations')
  const openRecommendations = reportList(report, 'open_recommendations')

  return (
    <article aria-labelledby="final-report-title" className="space-y-6">
      {/* Title, download and the executive summary, the most prominent part. */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 id="final-report-title" className="text-section-title">
              Final report
            </h2>
            <p className="mt-0.5 text-muted-foreground">The final report from the result, shown exactly as returned.</p>
          </div>
          <Button variant="outline" onClick={() => downloadText(reportFilename(jobId), reportToMarkdown(report, jobId), 'text/markdown;charset=utf-8')}>
            <FileDown className="size-4" aria-hidden="true" />
            Download Markdown
          </Button>
        </div>
        <section aria-labelledby={headingId('executive_summary')} className="space-y-2 px-5 py-5">
          <h3 id={headingId('executive_summary')} className="text-overline text-muted-foreground uppercase">
            {sectionTitle('executive_summary')}
          </h3>
          {executive ? (
            <Prose text={executive} className="text-section-title leading-7 font-normal" />
          ) : (
            <p className="text-muted-foreground italic">Not provided in this report.</p>
          )}
        </section>
      </Card>

      <Group title="Requirements and design" className="space-y-6">
        <TextSection report={report} field="requirements_summary" />
        <TextSection report={report} field="architecture_overview" />
        <TextSection report={report} field="aws_services_summary" />
        <TextSection report={report} field="data_flow_summary" />
      </Group>

      <Group title="Strategies and summaries" className="grid gap-x-8 gap-y-6 lg:grid-cols-2">
        <TextSection report={report} field="scalability_strategy" />
        <TextSection report={report} field="high_availability_strategy" />
        <TextSection report={report} field="security_summary" />
        <TextSection report={report} field="reliability_summary" />
        <TextSection report={report} field="observability_summary" />
        <TextSection report={report} field="cost_summary" />
      </Group>

      <Group title="Bottlenecks, trade-offs and critic findings" className="space-y-6">
        <ListSection report={report} field="bottlenecks" icon={Gauge} iconClass="text-warning" />
        <ListSection report={report} field="trade_offs" icon={Scale} iconClass="text-muted-foreground" />
        <TextSection report={report} field="critic_findings_summary" />
      </Group>

      <Group title="Recommendations" className="space-y-6">
        <section aria-labelledby={headingId('final_recommendations')} className="space-y-2">
          <h3 id={headingId('final_recommendations')} className="text-label">
            {sectionTitle('final_recommendations')}
          </h3>
          <p className="text-meta text-muted-foreground">In the order the report lists them.</p>
          {finalRecommendations.length > 0 ? (
            <ol className="list-decimal space-y-2 pl-5 marker:text-muted-foreground" aria-labelledby={headingId('final_recommendations')}>
              {finalRecommendations.map((item, index) => (
                <li key={index} className="pl-1">
                  <Prose text={item} />
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-muted-foreground italic">None listed in this report.</p>
          )}
        </section>

        {/* Kept apart from the final recommendations: these are NOT in the final architecture. */}
        <section
          aria-labelledby={headingId('open_recommendations')}
          className={cn('space-y-2 rounded-md border p-4', openRecommendations.length > 0 ? TONE_SOFT.info : 'border-border')}
        >
          <h3 id={headingId('open_recommendations')} className="flex items-center gap-2 text-label text-foreground">
            <ClipboardList className="size-4" aria-hidden="true" />
            {sectionTitle('open_recommendations')}
          </h3>
          <p className="text-meta text-muted-foreground">Requested or proposed during review, but not included in the final architecture.</p>
          {openRecommendations.length > 0 ? (
            <ul className="space-y-2 text-foreground" aria-labelledby={headingId('open_recommendations')}>
              {openRecommendations.map((item, index) => (
                <li key={index} className="flex gap-2.5">
                  <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-current opacity-60" aria-hidden="true" />
                  <Prose text={item} className="min-w-0" />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground italic">None listed in this report.</p>
          )}
        </section>
      </Group>
    </article>
  )
}
