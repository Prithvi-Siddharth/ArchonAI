import { ArrowRight, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { ApiError } from '@/api/client'
import { Badge, Button, buttonVariants, Card, CardHeader, Field, Input, Skeleton } from '@/components/ui'
import { FormAlert } from '@/features/auth/AuthShell'
import { useMe } from '@/features/auth/useAuth'
import { useLLMSettings } from '@/features/byok/useLLMSettings'
import { toast } from '@/stores/toast.store'
import type { User } from '@/types/api'
import { formatDateTime } from '@/utils/format'

import { DISPLAY_NAME_MAX, normaliseDisplayName, validateDisplayName } from './account-validation'
import { useUpdateProfile } from './useAccount'

const GENERIC_ERROR = 'Something went wrong while saving. Please try again.'

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-meta text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words font-medium">{children}</dd>
    </div>
  )
}

/** One line saying whose LLM key the user's jobs run on, linking to where it is changed. */
function ProviderRow() {
  const query = useLLMSettings()
  const settings = query.data
  const provider = settings?.providers.find((p) => p.id === settings.provider)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5" data-testid="provider-row">
      <div className="min-w-0">
        <p className="text-meta text-muted-foreground">AI provider</p>
        {settings ? (
          settings.configured ? (
            <p className="mt-0.5 flex flex-wrap items-center gap-2 font-medium">
              <Badge tone="success">
                <ShieldCheck className="size-3.5" aria-hidden="true" />
                Your own key
              </Badge>
              {provider?.label ?? settings.provider}
              <span className="font-mono text-meta font-normal text-muted-foreground">key ending …{settings.key_hint}</span>
            </p>
          ) : (
            <p className="mt-0.5 flex flex-wrap items-center gap-2 font-medium">
              <Badge>Server default</Badge>
              <span className="font-normal text-muted-foreground">Jobs use the provider set up on the server.</span>
            </p>
          )
        ) : query.isError ? (
          <p className="mt-0.5 text-muted-foreground">Couldn’t load your provider settings.</p>
        ) : (
          <Skeleton className="mt-1.5 h-5 w-48" />
        )}
      </div>
      <Link to="/byok" className={buttonVariants({ variant: 'outline', size: 'sm' })}>
        Manage
        <ArrowRight className="size-3.5" aria-hidden="true" />
      </Link>
    </div>
  )
}

function ProfileForm({ user }: { user: User }) {
  const save = useUpdateProfile()
  const [name, setName] = useState(user.display_name ?? '')
  const [attempted, setAttempted] = useState(false)

  const dirty = normaliseDisplayName(name) !== (user.display_name ?? '')
  const nameError = attempted ? validateDisplayName(name) : undefined
  const apiError = save.error
  const fieldError = apiError instanceof ApiError && apiError.kind === 'validation' ? apiError.fieldErrors.display_name : undefined
  const formError = apiError && !fieldError ? (apiError instanceof ApiError ? apiError.message : GENERIC_ERROR) : undefined

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (save.isPending) return
    setAttempted(true)
    if (validateDisplayName(name)) return
    const next = normaliseDisplayName(name) || null
    save.mutate(next, {
      onSuccess: (updated) => {
        setName(updated.display_name ?? '')
        setAttempted(false)
        toast({ tone: 'success', title: next ? 'Display name saved' : 'Display name cleared' })
      },
    })
  }

  return (
    <form noValidate onSubmit={handleSubmit} aria-label="Display name" className="space-y-4">
      {formError && <FormAlert>{formError}</FormAlert>}
      <Field
        label="Display name"
        error={nameError ?? fieldError}
        hint="Shown in the header instead of your email. Leave empty to show your email."
      >
        <Input
          autoComplete="nickname"
          value={name}
          maxLength={DISPLAY_NAME_MAX * 2}
          onChange={(event) => {
            if (save.isError) save.reset()
            setName(event.target.value)
          }}
        />
      </Field>
      <Button type="submit" loading={save.isPending} disabled={!dirty}>
        Save name
      </Button>
    </form>
  )
}

/** Email and member-since (read-only), the display name, and which AI provider the jobs use. */
export function AccountCard() {
  const me = useMe()
  const user = me.data
  return (
    <Card>
      <CardHeader title="Account" description="Your sign-in and how you appear in ArchonAI." />
      <div className="space-y-5 px-5 py-5">
        {user ? (
          <>
            <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
              <Fact label="Email (your sign-in)">{user.email}</Fact>
              <Fact label="Member since">
                <time dateTime={user.created_at}>{formatDateTime(user.created_at)}</time>
              </Fact>
            </dl>
            <ProfileForm key={user.display_name ?? ''} user={user} />
          </>
        ) : (
          <div aria-busy="true">
            <span className="sr-only">Loading your account</span>
            <Skeleton className="h-24 w-full" />
          </div>
        )}
        <ProviderRow />
      </div>
    </Card>
  )
}
