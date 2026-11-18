import { useState, type FormEvent } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router'

import { ApiError } from '@/api/client'
import { Button, Field, Input } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { toast } from '@/stores/toast.store'

import { AuthShell, FormAlert, PasswordInput } from './AuthShell'
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, safeNext, validateConfirmation, validateEmail, validateNewPassword } from './auth-validation'
import { withNext } from './LoginPage'
import { useMe, useRegister } from './useAuth'

const GENERIC_ERROR = 'Something went wrong while creating your account. Please try again.'

export function RegisterPage() {
  useDocumentTitle('Create account')
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const me = useMe()
  const signUp = useRegister()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [attempted, setAttempted] = useState(false)

  if (me.data) return <Navigate to={next} replace />

  const apiError = signUp.error
  const emailTaken = apiError instanceof ApiError && apiError.status === 409
  const fieldErrors = apiError instanceof ApiError && apiError.kind === 'validation' ? apiError.fieldErrors : {}
  const emailError = (attempted ? validateEmail(email) : undefined) ?? fieldErrors.email
  const passwordError = (attempted ? validateNewPassword(password) : undefined) ?? fieldErrors.password
  const confirmationError = attempted ? validateConfirmation(password, confirmation) : undefined
  const formError =
    apiError && !emailTaken && !fieldErrors.email && !fieldErrors.password
      ? apiError instanceof ApiError
        ? apiError.message
        : GENERIC_ERROR
      : undefined

  const edit = (setter: (value: string) => void) => (value: string) => {
    setter(value)
    if (signUp.isError) signUp.reset()
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (signUp.isPending) return
    setAttempted(true)
    if (validateEmail(email) || validateNewPassword(password) || validateConfirmation(password, confirmation)) return
    signUp.mutate(
      { email: email.trim(), password },
      { onSuccess: (user) => toast({ tone: 'success', title: 'Account created', description: `Signed in as ${user.email}` }) },
    )
  }

  const signInLink = (
    <Link to={withNext('/login', next)} className="font-medium text-primary hover:underline">
      Sign in
    </Link>
  )

  return (
    <AuthShell
      title="Create an account"
      description="Create an account to design and review AWS architectures."
      footer={<>Already have an account? {signInLink}</>}
    >
      <form noValidate onSubmit={handleSubmit} className="space-y-4" aria-label="Create an account">
        {formError && <FormAlert>{formError}</FormAlert>}
        <Field
          label="Email"
          error={
            emailError ??
            (emailTaken ? (
              <span>
                An account with this email already exists. {signInLink} instead.
              </span>
            ) : undefined)
          }
        >
          <Input type="email" autoComplete="email" inputMode="email" value={email} onChange={(e) => edit(setEmail)(e.target.value)} autoFocus />
        </Field>
        <Field label="Password" hint={`${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters.`} error={passwordError}>
          <PasswordInput autoComplete="new-password" value={password} onChange={(e) => edit(setPassword)(e.target.value)} />
        </Field>
        <Field label="Confirm password" error={confirmationError}>
          <PasswordInput autoComplete="new-password" value={confirmation} onChange={(e) => edit(setConfirmation)(e.target.value)} />
        </Field>
        <Button type="submit" className="w-full" loading={signUp.isPending}>
          Create account
        </Button>
      </form>
    </AuthShell>
  )
}
