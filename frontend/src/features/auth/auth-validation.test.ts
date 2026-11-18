import { describe, expect, it } from 'vitest'

import { safeNext, validateConfirmation, validateEmail, validateLoginPassword, validateNewPassword } from './auth-validation'

describe('auth validation (mirrors the backend)', () => {
  it.each([
    ['', 'Enter your email address.'],
    ['   ', 'Enter your email address.'],
    ['ada', 'Enter a valid email address, like you@example.com.'],
    ['ada@example', 'Enter a valid email address, like you@example.com.'],
    ['a da@example.com', 'Enter a valid email address, like you@example.com.'],
    [`${'a'.repeat(250)}@x.io`, 'Enter a valid email address, like you@example.com.'],
    ['  Ada@Example.com ', undefined],
  ])('email %j', (email, expected) => {
    expect(validateEmail(email)).toBe(expected)
  })

  it('new passwords: 8 to 128 characters, counted like the backend', () => {
    expect(validateNewPassword('')).toBe('Choose a password.')
    expect(validateNewPassword('1234567')).toBe('Use at least 8 characters.')
    expect(validateNewPassword('12345678')).toBeUndefined()
    expect(validateNewPassword('        ')).toBeUndefined() // spaces count
    expect(validateNewPassword('x'.repeat(128))).toBeUndefined()
    expect(validateNewPassword('x'.repeat(129))).toBe('Use at most 128 characters.')
    expect(validateNewPassword('😀'.repeat(8))).toBeUndefined() // 8 code points, 16 UTF-16 units
    expect(validateNewPassword('😀'.repeat(7))).toBe('Use at least 8 characters.')
  })

  it('login passwords have no minimum', () => {
    expect(validateLoginPassword('')).toBe('Enter your password.')
    expect(validateLoginPassword('x')).toBeUndefined()
    expect(validateLoginPassword('x'.repeat(129))).toBe('Passwords are at most 128 characters.')
  })

  it('confirmation must match exactly', () => {
    expect(validateConfirmation('secret pass', '')).toBe('Enter the password again.')
    expect(validateConfirmation('secret pass', 'secret pass ')).toBe("The passwords don't match.")
    expect(validateConfirmation('secret pass', 'secret pass')).toBeUndefined()
  })
})

describe('safeNext', () => {
  it.each([
    ['/architectures/abc', '/architectures/abc'],
    ['/architectures/abc/results?tab=cost#x', '/architectures/abc/results?tab=cost#x'],
    ['/settings', '/settings'],
    [null, '/dashboard'],
    ['', '/dashboard'],
    ['https://evil.example', '/dashboard'],
    ['//evil.example', '/dashboard'],
    ['/\\evil.example', '/dashboard'],
    ['/\t/evil.example', '/dashboard'],
    ['/ok\nbad', '/dashboard'],
    ['javascript:alert(1)', '/dashboard'],
    ['/login', '/dashboard'],
    ['/login?next=/x', '/dashboard'],
    ['/register', '/dashboard'],
    ['/loginx', '/loginx'],
  ])('%j -> %s', (raw, expected) => {
    expect(safeNext(raw)).toBe(expected)
  })
})
