import { useState, type FormEvent } from 'react'

import { ApiError } from '@/api/client'
import { Button, Card, CardHeader, Field } from '@/components/ui'
import { FormAlert, PasswordInput } from '@/features/auth/AuthShell'
import { validateConfirmation, validateLoginPassword, validateNewPassword } from '@/features/auth/auth-validation'
import { toast } from '@/stores/toast.store'

import { useChangePassword } from './useAccount'

const GENERIC_ERROR = 'Something went wrong while changing your password. Please try again.'

/** Change the password. The current one is required; every other signed-in browser is signed out. */
export function PasswordCard() {
  const change = useChangePassword()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [attempted, setAttempted] = useState(false)

  const sameAsCurrent = Boolean(next) && next === current
  const currentError = attempted ? validateLoginPassword(current) : undefined
  const nextError = attempted ? (validateNewPassword(next) ?? (sameAsCurrent ? 'Choose a password different from your current one.' : undefined)) : undefined
  const confirmError = attempted ? validateConfirmation(next, confirmation) : undefined

  const apiError = change.error
  const fieldErrors = apiError instanceof ApiError && apiError.kind === 'validation' ? apiError.fieldErrors : {}
  // A wrong current password comes back as a plain 400 message: show it on that field.
  const wrongCurrent = apiError instanceof ApiError && apiError.status === 400 ? apiError.message : undefined
  const formError =
    apiError && !wrongCurrent && !fieldErrors.current_password && !fieldErrors.new_password
      ? apiError instanceof ApiError
        ? apiError.message
        : GENERIC_ERROR
      : undefined

  const edit = (setter: (value: string) => void) => (value: string) => {
    setter(value)
    if (change.isError) change.reset()
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (change.isPending) return
    setAttempted(true)
    if (validateLoginPassword(current) || validateNewPassword(next) || sameAsCurrent || validateConfirmation(next, confirmation)) return
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent('')
          setNext('')
          setConfirmation('')
          setAttempted(false)
          toast({ tone: 'success', title: 'Password changed', description: 'You were signed out on every other device.' })
        },
      },
    )
  }

  return (
    <Card>
      <CardHeader title="Password" description="Change the password you sign in with." />
      <form noValidate onSubmit={handleSubmit} aria-label="Change password" className="space-y-4 px-5 py-5">
        {formError && <FormAlert>{formError}</FormAlert>}
        <Field label="Current password" error={currentError ?? wrongCurrent ?? fieldErrors.current_password}>
          <PasswordInput autoComplete="current-password" value={current} onChange={(event) => edit(setCurrent)(event.target.value)} />
        </Field>
        <Field label="New password" error={nextError ?? fieldErrors.new_password} hint="8 to 128 characters.">
          <PasswordInput autoComplete="new-password" value={next} onChange={(event) => edit(setNext)(event.target.value)} />
        </Field>
        <Field label="Confirm new password" error={confirmError}>
          <PasswordInput autoComplete="new-password" value={confirmation} onChange={(event) => edit(setConfirmation)(event.target.value)} />
        </Field>
        <p className="text-meta text-muted-foreground">Changing your password signs you out everywhere else. This browser stays signed in.</p>
        <Button type="submit" loading={change.isPending}>
          Change password
        </Button>
      </form>
    </Card>
  )
}
