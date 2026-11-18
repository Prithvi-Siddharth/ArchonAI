import { ArrowRight, Cpu, Database, LifeBuoy, Network, ShieldCheck, TriangleAlert, Users, type LucideIcon } from 'lucide-react'

import { Badge, Card, CardContent, EmptyState, SectionHeader } from '@/components/ui'
import type { AnalysisResult, ArchitectureResult } from '@/types/api'

type AnalysisKey = 'compute_analysis' | 'database_analysis' | 'networking_analysis' | 'security_analysis' | 'reliability_analysis'

/** The five specialists, in the order the workflow runs them. */
export const SPECIALISTS: ReadonlyArray<{ key: AnalysisKey; label: string; icon: LucideIcon }> = [
  { key: 'compute_analysis', label: 'Compute', icon: Cpu },
  { key: 'database_analysis', label: 'Database', icon: Database },
  { key: 'networking_analysis', label: 'Networking', icon: Network },
  { key: 'security_analysis', label: 'Security', icon: ShieldCheck },
  { key: 'reliability_analysis', label: 'Reliability', icon: LifeBuoy },
]

/** One analysis with every field made safe to read (an absent object or array becomes empty). */
function readAnalysis(analysis: AnalysisResult | undefined) {
  return {
    present: analysis !== undefined && analysis !== null,
    domain: analysis?.domain?.trim() ?? '',
    recommendations: analysis?.recommendations ?? [],
    reasoning: analysis?.reasoning?.trim() ?? '',
    risks: analysis?.risks ?? [],
  }
}

type ReadAnalysis = ReturnType<typeof readAnalysis>

const isEmpty = (a: ReadAnalysis) => a.recommendations.length === 0 && a.risks.length === 0 && a.reasoning === ''

const sectionId = (key: AnalysisKey) => `analysis-${key.replace('_analysis', '')}`

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

function ItemList({ items, kind }: { items: string[]; kind: 'recommendation' | 'risk' }) {
  const Icon = kind === 'risk' ? TriangleAlert : ArrowRight
  return (
    <ul className="space-y-2" aria-label={kind === 'risk' ? 'Risks' : 'Recommendations'}>
      {items.map((item, index) => (
        <li key={index} className="flex gap-2.5">
          <Icon className={kind === 'risk' ? 'mt-0.5 size-4 shrink-0 text-warning' : 'mt-0.5 size-4 shrink-0 text-primary'} aria-hidden="true" />
          <span className="min-w-0 break-words">{item}</span>
        </li>
      ))}
    </ul>
  )
}

function SpecialistSection({ label, icon: Icon, sectionKey, analysis }: { label: string; icon: LucideIcon; sectionKey: AnalysisKey; analysis: ReadAnalysis }) {
  const id = sectionId(sectionKey)
  return (
    <Card>
      <section aria-labelledby={`${id}-title`} id={id} className="scroll-mt-6">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-surface-muted text-muted-foreground">
              <Icon className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h3 id={`${id}-title`} className="text-card-title break-words">
                {analysis.domain || label}
              </h3>
              <p className="text-meta text-muted-foreground">{label} specialist</p>
            </div>
          </div>
          {analysis.present && (
            <div className="flex flex-wrap gap-1.5">
              <Badge tone="info">{plural(analysis.recommendations.length, 'recommendation')}</Badge>
              <Badge tone={analysis.risks.length > 0 ? 'warning' : 'neutral'}>{plural(analysis.risks.length, 'risk')}</Badge>
            </div>
          )}
        </div>

        {!analysis.present || isEmpty(analysis) ? (
          <EmptyState
            compact
            icon={Icon}
            title={analysis.present ? 'No analysis content' : 'Analysis not available'}
            description={
              analysis.present
                ? `The ${label.toLowerCase()} specialist returned no recommendations, reasoning or risks.`
                : `This result has no ${label.toLowerCase()} analysis.`
            }
          />
        ) : (
          <CardContent className="space-y-5">
            <div className="grid gap-5 md:grid-cols-2">
              <div className="min-w-0 space-y-2">
                <h4 className="text-label">Recommendations</h4>
                {analysis.recommendations.length > 0 ? (
                  <ItemList items={analysis.recommendations} kind="recommendation" />
                ) : (
                  <p className="text-muted-foreground">No recommendations.</p>
                )}
              </div>
              <div className="min-w-0 space-y-2 rounded-md border border-warning/25 bg-warning/5 p-3">
                <h4 className="text-label">Risks</h4>
                {analysis.risks.length > 0 ? <ItemList items={analysis.risks} kind="risk" /> : <p className="text-muted-foreground">No risks identified.</p>}
              </div>
            </div>
            <div className="space-y-1.5">
              <h4 className="text-label">Reasoning</h4>
              {analysis.reasoning ? (
                <p className="break-words whitespace-pre-line text-muted-foreground">{analysis.reasoning}</p>
              ) : (
                <p className="text-muted-foreground">No reasoning provided.</p>
              )}
            </div>
          </CardContent>
        )}
      </section>
    </Card>
  )
}

export function AnalysesTab({ result }: { result: ArchitectureResult }) {
  // Widened on purpose: a stored result could lack an analysis even though the type says otherwise.
  const analyses = SPECIALISTS.map((s) => ({ ...s, analysis: readAnalysis(result[s.key] as AnalysisResult | undefined) }))
  const totalRecommendations = analyses.reduce((sum, a) => sum + a.analysis.recommendations.length, 0)
  const totalRisks = analyses.reduce((sum, a) => sum + a.analysis.risks.length, 0)
  const available = analyses.filter((a) => a.analysis.present).length

  if (analyses.every((a) => !a.analysis.present || isEmpty(a.analysis))) {
    return (
      <Card>
        <EmptyState icon={Users} title="No specialist analyses" description="This result contains no content from the five specialist agents." />
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <section aria-labelledby="analyses-overview" className="px-5 py-4">
          <h2 id="analyses-overview" className="text-card-title">
            Specialist analyses
          </h2>
          <p className="mt-0.5 text-muted-foreground">
            Five specialist agents each reviewed the design in their domain. Counts are taken from their lists.
          </p>
          <dl className="mt-4 grid grid-cols-3 gap-4">
            <div>
              <dt className="text-meta text-muted-foreground">Specialist analyses</dt>
              <dd className="text-stat tabular-nums">{available}</dd>
            </div>
            <div>
              <dt className="text-meta text-muted-foreground">Recommendations</dt>
              <dd className="text-stat tabular-nums">{totalRecommendations}</dd>
            </div>
            <div>
              <dt className="text-meta text-muted-foreground">Risks</dt>
              <dd className="text-stat tabular-nums">{totalRisks}</dd>
            </div>
          </dl>
          <nav aria-label="Specialist sections" className="mt-4 flex flex-wrap gap-2">
            {analyses.map(({ key, label, icon: Icon, analysis }) => (
              <a
                key={key}
                href={`#${sectionId(key)}`}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-meta hover:bg-surface-muted"
              >
                <Icon className="size-3.5 text-muted-foreground" aria-hidden="true" />
                {analysis.domain || label}
                <span className="text-muted-foreground tabular-nums">
                  {analysis.recommendations.length}/{analysis.risks.length}
                </span>
                <span className="sr-only">
                  : {plural(analysis.recommendations.length, 'recommendation')}, {plural(analysis.risks.length, 'risk')}
                </span>
              </a>
            ))}
          </nav>
          <p className="mt-2 text-meta text-muted-foreground">Numbers after each name: recommendations / risks.</p>
        </section>
      </Card>

      <SectionHeader title="By specialist" />
      <div className="space-y-6">
        {analyses.map(({ key, label, icon, analysis }) => (
          <SpecialistSection key={key} sectionKey={key} label={label} icon={icon} analysis={analysis} />
        ))}
      </div>
    </div>
  )
}
