import { Card, CardContent } from '@/components/ui'

import { ShowcaseSection } from './showcase-helpers'

const COLORS = [
  ['Background', '--background'],
  ['Surface', '--surface'],
  ['Surface (muted)', '--surface-muted'],
  ['Elevated surface', '--surface-elevated'],
  ['Text primary', '--foreground'],
  ['Text secondary', '--muted-foreground'],
  ['Border', '--border'],
  ['Border (strong)', '--border-strong'],
  ['Primary', '--primary'],
  ['Secondary', '--secondary'],
  ['Destructive', '--destructive'],
  ['Success', '--success'],
  ['Warning', '--warning'],
  ['Error', '--danger'],
  ['Information', '--info'],
  ['Focus ring', '--ring'],
] as const

const TYPE_ROLES = [
  ['Page heading', 'text-page-title', 'Architecture History'],
  ['Section heading', 'text-section-title', 'Recent architectures'],
  ['Card heading', 'text-card-title', 'Cost estimate'],
  ['Body', 'text-body', 'Multi-AZ deployment behind an Application Load Balancer.'],
  ['Supporting', 'text-body text-muted-foreground', 'Describe your workload in plain language.'],
  ['Label', 'text-label', 'Project name'],
  ['Metadata', 'text-meta text-muted-foreground', 'Updated 5 minutes ago · 9 services'],
  ['Technical value', 'font-mono text-meta', 'job 7f3c9a21 · ap-south-1 · t4g.medium'],
  ['Overline', 'text-overline uppercase text-muted-foreground', 'Workspace'],
  ['Statistic', 'text-stat', '1,284'],
] as const

export function FoundationsShowcase() {
  return (
    <ShowcaseSection
      id="foundations"
      title="Foundations"
      description="Semantic color and type tokens from styles/tokens.css. Switch the theme to compare."
    >
      <Card>
        <CardContent className="grid gap-x-6 gap-y-4 py-5 sm:grid-cols-2 lg:grid-cols-4">
          {COLORS.map(([name, variable]) => (
            <div key={variable} className="flex items-center gap-3">
              <span
                className="size-9 shrink-0 rounded-md border border-border"
                style={{ backgroundColor: `var(${variable})` }}
              />
              <div className="min-w-0">
                <p className="text-label">{name}</p>
                <p className="font-mono text-meta text-muted-foreground">{variable}</p>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <ul className="divide-y divide-border">
          {TYPE_ROLES.map(([role, classes, sample]) => (
            <li key={role} className="grid gap-1 px-5 py-3 sm:grid-cols-[10rem_1fr] sm:items-baseline sm:gap-4">
              <div>
                <p className="text-label">{role}</p>
                <p className="font-mono text-meta text-muted-foreground">{classes}</p>
              </div>
              <p className={classes}>{sample}</p>
            </li>
          ))}
        </ul>
      </Card>
    </ShowcaseSection>
  )
}
