import { Construction } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'

export function NewArchitecturePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="New Architecture"
        description="Describe a workload and generate a reviewed AWS architecture."
      />
      <Card>
        <EmptyState
          icon={Construction}
          title="Not available yet"
          description="The request form arrives in a later phase, once the frontend is connected to the ArchonAI API."
        />
      </Card>
    </div>
  )
}
