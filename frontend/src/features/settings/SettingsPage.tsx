import { Construction } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Preferences for this workspace." />
      <Card>
        <EmptyState
          icon={Construction}
          title="Not available yet"
          description="Settings arrive in a later phase. The theme can already be switched from the header."
        />
      </Card>
    </div>
  )
}
