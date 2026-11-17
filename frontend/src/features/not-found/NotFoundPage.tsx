import { Compass } from 'lucide-react'
import { Link } from 'react-router'

import { buttonVariants } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'

export function NotFoundPage() {
  return (
    <Card>
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="This page doesn't exist. Check the address or go back to the dashboard."
        action={
          <Link to="/dashboard" className={buttonVariants({ variant: 'outline' })}>
            Go to dashboard
          </Link>
        }
      />
    </Card>
  )
}
