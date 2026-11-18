import { useState, type FormEvent } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router'

import { ApiError } from '@/api/client'
import { Button, Field, Input } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import { AuthShell, FormAlert, PasswordInput } from './AuthShell'
import { safeNext, validateEmail, validateLoginPassword } from './auth-validation'
import { useLogin, useMe } from './useAuth'

const GENERIC_ERROR = 'Something went wrong while signing in. Please try again.'

/** Keeps ?next= when moving between the sign-in and registration pages. */
export const withNext = (path: string, next: string) => (next === '/dashboard' ? path : `${path}?next=${encodeURIComponent(next)}`)

export function LoginPage() {
  useDocumentTitle('Sign in')
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const me = useMe()
  const signIn = useLogin()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [attempted, setAttempted] = useState(false)

  // Signed in (already, or just now): continue to where the user was going.
  if (me.data) return <Navigate to={next} replace />

  const emailError = attempted ? validateEmail(email) : undefined
  const passwordError = attempted ? validateLoginPassword(password) : undefined
  const apiError = signIn.error
  const fieldErrors = apiError instanceof ApiError && apiError.kind === 'validation' ? apiError.fieldErrors : {}
  const formError =
    apiError && !fieldErrors.email && !fieldErrors.password ? (apiError instanceof ApiError ? apiError.message : GENERIC_ERROR) : undefined

  const edit = (setter: (value: string) => void) => (value: string) => {
    setter(value)
    if (signIn.isError) signIn.reset()
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (signIn.isPending) return
    setAttempted(true)
    if (validateEmail(email) || validateLoginPassword(password)) return
    signIn.mutate({ email: email.trim(), password })
  }

  return (
    <AuthShell
      title="Sign in"
      description="Sign in to design and review your AWS architectures."
      footer={
        <>
          New to ArchonAI?{' '}
          <Link to={withNext('/register', next)} className="font-medium text-primary hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form noValidate onSubmit={handleSubmit} className="space-y-4" aria-label="Sign in">
        {formError && <FormAlert>{formError}</FormAlert>}
        <Field label="Email" error={emailError ?? fieldErrors.email}>
          <Input type="email" autoComplete="email" inputMode="email" value={email} onChange={(e) => edit(setEmail)(e.target.value)} autoFocus />
        </Field>
        <Field label="Password" error={passwordError ?? fieldErrors.password}>
          <PasswordInput autoComplete="current-password" value={password} onChange={(e) => edit(setPassword)(e.target.value)} />
        </Field>
        <Button type="submit" className="w-full" loading={signIn.isPending}>
          Sign in
        </Button>
      </form>
    </AuthShell>
  )
}
