import { Construction } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'

export function ArchitectureHistoryPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Architecture History" description="Every architecture you have generated, with its status." />
      <Card>
        <EmptyState
          icon={Construction}
          title="Not available yet"
          description="Job history arrives in a later phase, once the frontend is connected to the ArchonAI API."
        />
      </Card>
    </div>
  )
}
