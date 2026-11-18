import { LogOut } from 'lucide-react'
import { useNavigate } from 'react-router'

import { Button, Tooltip } from '@/components/ui'
import { toast } from '@/stores/toast.store'

import { useLogout, useMe } from './useAuth'

/** The signed-in email and a sign-out button, for the app header. */
export function AccountMenu() {
  const me = useMe()
  const signOut = useLogout()
  const navigate = useNavigate()
  if (!me.data) return null

  const handleSignOut = () =>
    signOut.mutate(undefined, {
      onSuccess: () => navigate('/login', { replace: true }),
      onError: () => toast({ tone: 'danger', title: "Couldn't sign out", description: 'Please try again.' }),
    })

  return (
    <div className="flex min-w-0 items-center gap-1">
      <span className="hidden max-w-56 truncate text-meta text-muted-foreground md:block" title={me.data.email} data-testid="account-email">
        {me.data.email}
      </span>
      <Tooltip content="Sign out" side="bottom" describeTrigger={false}>
        <Button variant="ghost" size="icon" onClick={handleSignOut} loading={signOut.isPending} aria-label="Sign out">
          {!signOut.isPending && <LogOut className="size-4" aria-hidden="true" />}
        </Button>
      </Tooltip>
    </div>
  )
}
