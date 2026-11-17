import { Badge, PageHeader } from '@/components/ui'
import { useUIStore, type Theme } from '@/stores/ui.store'

import { ButtonsShowcase, InputsShowcase } from './ControlsShowcase'
import { CardsShowcase, DataShowcase, StatusShowcase } from './DisplayShowcase'
import { FeedbackShowcase } from './FeedbackShowcase'
import { FoundationsShowcase } from './FoundationsShowcase'
import { Segmented } from './showcase-helpers'

const SECTIONS = [
  ['foundations', 'Foundations'],
  ['buttons', 'Buttons'],
  ['inputs', 'Inputs'],
  ['cards', 'Cards'],
  ['status', 'Status'],
  ['data', 'Data display'],
  ['feedback', 'Feedback'],
] as const

/**
 * Internal component library page (development builds only, at /dev/components).
 * Not linked from the navigation; delete freely once real pages cover the components.
 */
export function ComponentShowcasePage() {
  const theme = useUIStore((state) => state.theme)
  const setTheme = useUIStore((state) => state.setTheme)

  return (
    <div className="space-y-10">
      <div className="space-y-4">
        <PageHeader
          title="Component library"
          description="Every reusable UI component and its states, for development and visual checks in both themes."
          badge={<Badge tone="warning">Dev only</Badge>}
          actions={
            <Segmented<Theme>
              label="Theme"
              value={theme}
              onChange={setTheme}
              options={[
                { value: 'light', label: 'Light' },
                { value: 'dark', label: 'Dark' },
              ]}
            />
          }
        />
        <nav aria-label="Component sections" className="flex flex-wrap gap-x-4 gap-y-1">
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="rounded-sm text-muted-foreground hover:text-foreground">
              {label}
            </a>
          ))}
        </nav>
      </div>

      <FoundationsShowcase />
      <ButtonsShowcase />
      <InputsShowcase />
      <CardsShowcase />
      <StatusShowcase />
      <DataShowcase />
      <FeedbackShowcase />
    </div>
  )
}
