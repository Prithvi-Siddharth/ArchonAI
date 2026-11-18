/**
 * Client-side checks that mirror the backend (api/schemas.py RegisterRequest / LoginRequest),
 * so most mistakes are caught before a request. The backend checks again either way.
 */

export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128
const EMAIL_MAX_LENGTH = 254
/** Same shape check as the backend: something@something.tld, no spaces. */
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

/** Characters as the backend counts them (code points, so an emoji counts once). */
const length = (value: string) => Array.from(value).length

export function validateEmail(email: string): string | undefined {
  const value = email.trim()
  if (!value) return 'Enter your email address.'
  if (value.length > EMAIL_MAX_LENGTH || !EMAIL_PATTERN.test(value)) return 'Enter a valid email address, like you@example.com.'
  return undefined
}

/** For a new password. Spaces are allowed and count. */
export function validateNewPassword(password: string): string | undefined {
  if (!password) return 'Choose a password.'
  if (length(password) < PASSWORD_MIN_LENGTH) return `Use at least ${PASSWORD_MIN_LENGTH} characters.`
  if (length(password) > PASSWORD_MAX_LENGTH) return `Use at most ${PASSWORD_MAX_LENGTH} characters.`
  return undefined
}

/** For signing in: no minimum, so a rule change never locks anyone out. */
export function validateLoginPassword(password: string): string | undefined {
  if (!password) return 'Enter your password.'
  if (length(password) > PASSWORD_MAX_LENGTH) return `Passwords are at most ${PASSWORD_MAX_LENGTH} characters.`
  return undefined
}

export function validateConfirmation(password: string, confirmation: string): string | undefined {
  if (!confirmation) return 'Enter the password again.'
  if (confirmation !== password) return "The passwords don't match."
  return undefined
}

const HOME = '/dashboard'

/**
 * Where to go after signing in: only a path inside this app. Anything that could leave the
 * site ("//evil.example", "/\\evil", absolute URLs, control characters) or loop back to the
 * sign-in pages falls back to the dashboard.
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return HOME
  if (/[\\\s\u0000-\u001f\u007f]/.test(raw)) return HOME
  if (/^\/(login|register)(?=$|[/?#])/.test(raw)) return HOME
  return raw
}
