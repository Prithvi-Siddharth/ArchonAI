import { PageHeader } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import { NotificationsCard } from '@/features/notifications/NotificationsCard'

import { AccountCard } from './AccountCard'
import { PasswordCard } from './PasswordCard'
import { StatsCard } from './StatsCard'

/** Your account, your password, and statistics about your own jobs. */
export function SettingsPage() {
  useDocumentTitle('Settings')
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Your account, notifications, password and usage. The theme can be switched from the header." />
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <AccountCard />
          <NotificationsCard />
          <PasswordCard />
        </div>
        <StatsCard />
      </div>
    </div>
  )
}
