import { ExternalLink, KeyRound, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import { Badge, Button, Card, CardHeader, ConfirmDialog, ErrorState, Field, Input, Select, Skeleton } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import { FormAlert, PasswordInput } from '@/features/auth/AuthShell'
import { toast } from '@/stores/toast.store'
import type { LLMSettings } from '@/types/api'
import { cn } from '@/utils/cn'
import { formatDateTime } from '@/utils/format'

import { validateApiKey, validateModel } from './llm-validation'
import { useDeleteLLMSettings, useLLMSettings, useSaveLLMSettings } from './useLLMSettings'

const GENERIC_ERROR = 'Something went wrong while saving. Please try again.'

function LoadingBody() {
  return (
    <div className="space-y-4 px-5 py-5" aria-busy="true">
      <span className="sr-only">Loading your AI provider settings</span>
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
    </div>
  )
}

function Status({ settings }: { settings: LLMSettings }) {
  const provider = settings.providers.find((p) => p.id === settings.provider)
  if (!settings.configured) {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1" data-testid="llm-status">
        <Badge>Server default</Badge>
        <p className="text-muted-foreground">Your jobs use the provider set up on this server. Add your own key below to use yours.</p>
      </div>
    )
  }
  return (
    <div className="space-y-1" data-testid="llm-status">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Badge tone="success">
          <ShieldCheck className="size-3.5" aria-hidden="true" />
          Using your own key
        </Badge>
        <p className="font-medium">
          {provider?.label ?? settings.provider} <span className="font-mono text-meta text-muted-foreground">key ending …{settings.key_hint}</span>
        </p>
      </div>
      <p className="text-meta text-muted-foreground">
        Model: {settings.model ?? `${provider?.default_model ?? 'provider default'} (default)`}
        {settings.updated_at && <> · Saved {formatDateTime(settings.updated_at)}</>}
      </p>
    </div>
  )
}

function Form({ settings }: { settings: LLMSettings }) {
  const save = useSaveLLMSettings()
  const remove = useDeleteLLMSettings()
  const [provider, setProvider] = useState(settings.provider ?? settings.providers[0]?.id ?? '')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(settings.model ?? '')
  const [attempted, setAttempted] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(false)

  const option = settings.providers.find((p) => p.id === provider)
  const label = option?.label ?? 'provider'
  // A key must be given for a first save and whenever the provider changes; otherwise empty keeps the saved key.
  const keyRequired = !settings.configured || provider !== settings.provider
  const locked = !settings.encryption_available
  const dirty = !settings.configured || apiKey !== '' || provider !== settings.provider || model.trim() !== (settings.model ?? '')

  const keyError = attempted ? validateApiKey(apiKey, keyRequired, label) : undefined
  const modelError = attempted ? validateModel(model) : undefined
  const apiError = save.error
  const fieldErrors = apiError instanceof ApiError && apiError.kind === 'validation' ? apiError.fieldErrors : {}
  const formError = apiError && !fieldErrors.api_key && !fieldErrors.model && !fieldErrors.provider ? (apiError instanceof ApiError ? apiError.message : GENERIC_ERROR) : undefined

  const touch = () => {
    if (save.isError) save.reset()
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (save.isPending || locked) return
    setAttempted(true)
    if (validateApiKey(apiKey, keyRequired, label) || validateModel(model)) return
    save.mutate(
      { provider, ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}), model: model.trim() || null },
      {
        onSuccess: () => {
          setApiKey('')
          toast({ tone: 'success', title: 'API key saved', description: 'Your next jobs will run on your own provider.' })
        },
      },
    )
  }

  const handleRemove = async () => {
    try {
      await remove.mutateAsync()
      setConfirmRemove(false)
      toast({ tone: 'success', title: 'API key removed', description: 'Your jobs use the server’s default provider again.' })
    } catch {
      setConfirmRemove(false)
      toast({ tone: 'danger', title: "Couldn't remove the key", description: 'Please try again.' })
    }
  }

  return (
    <>
      <form noValidate onSubmit={handleSubmit} aria-label="AI provider settings" className="space-y-5 px-5 py-5">
        <Status settings={settings} />

        {locked && (
          <div role="note" className={cn('flex items-start gap-2.5 rounded-md border px-3 py-2.5', TONE_SOFT.warning)}>
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p>Saving your own key isn’t available on this server yet. Ask whoever runs this ArchonAI server to turn it on.</p>
          </div>
        )}
        {formError && <FormAlert>{formError}</FormAlert>}

        <Field label="Provider" error={fieldErrors.provider} disabled={locked}>
          <Select
            value={provider}
            onChange={(event) => {
              touch()
              setProvider(event.target.value)
              // A model name belongs to one provider.
              setModel('')
            }}
            options={settings.providers.map((p) => ({ value: p.id, label: p.label }))}
            disabled={locked}
          />
        </Field>

        <Field
          label="API key"
          disabled={locked}
          error={keyError ?? fieldErrors.api_key}
          hint={
            !keyRequired ? (
              'Leave empty to keep the saved key. Enter a new one to replace it.'
            ) : option ? (
              <>
                Create one in your {option.label} account:{' '}
                <a href={option.key_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
                  Get a key
                  <ExternalLink className="size-3" aria-hidden="true" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              </>
            ) : undefined
          }
        >
          <PasswordInput
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="off"
            placeholder={!keyRequired ? '••••••••••••' : 'Paste your key'}
            value={apiKey}
            onChange={(event) => {
              touch()
              setApiKey(event.target.value)
            }}
            disabled={locked}
          />
        </Field>

        <Field
          label="Model (optional)"
          disabled={locked}
          error={modelError ?? fieldErrors.model}
          hint={option ? `Leave empty to use ${option.default_model}.` : undefined}
        >
          <Input
            autoComplete="off"
            spellCheck={false}
            placeholder={option?.default_model}
            value={model}
            maxLength={100}
            onChange={(event) => {
              touch()
              setModel(event.target.value)
            }}
            disabled={locked}
          />
        </Field>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={save.isPending} disabled={locked || !dirty}>
            {settings.configured ? 'Save changes' : 'Save key'}
          </Button>
          {settings.configured && (
            <Button type="button" variant="outline" onClick={() => setConfirmRemove(true)} disabled={remove.isPending}>
              Remove key
            </Button>
          )}
        </div>

        <p className="flex items-start gap-2 text-meta text-muted-foreground">
          <KeyRound className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          Your key is encrypted before it is stored and is never shown again. It is used only to run your own jobs, and it is sent to the provider you choose, not to anyone else.
        </p>
      </form>

      <ConfirmDialog
        open={confirmRemove}
        onCancel={() => setConfirmRemove(false)}
        onConfirm={handleRemove}
        title="Remove your API key?"
        description="Your jobs will use this server’s default provider again. You can add a key again at any time."
        confirmLabel="Remove key"
        tone="destructive"
      />
    </>
  )
}

/** Bring your own key: choose a provider and save an API key that is used for the user's own jobs. */
export function LLMKeyCard() {
  const query = useLLMSettings()
  const settings = query.data

  let body
  if (settings) {
    // Remounts after every save or removal, so the form starts clean (key box emptied).
    body = <Form key={`${settings.configured}-${settings.updated_at ?? 'none'}`} settings={settings} />
  } else if (query.isError) {
    body = (
      <ErrorState
        compact
        title="Couldn't load your AI provider settings"
        description={query.error instanceof ApiError ? query.error.message : 'Please try again.'}
        onRetry={() => void query.refetch()}
        isRetrying={query.isFetching}
      />
    )
  } else {
    body = <LoadingBody />
  }

  return (
    <Card>
      <CardHeader
        title="AI provider"
        description="Run your architecture jobs on your own LLM account by bringing your own API key."
      />
      {body}
    </Card>
  )
}
