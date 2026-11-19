/**
 * The Settings page: display name, password change and statistics, against a fake API.
 * fetch is stubbed in every test: nothing reaches a real backend, and all passwords are fakes.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AccountMenu } from '@/features/auth/AccountMenu'
import { useToastStore } from '@/stores/toast.store'
import type { LLMSettings, Stats, User } from '@/types/api'

import { normaliseDisplayName, validateDisplayName } from './account-validation'
import { SettingsPage } from './SettingsPage'

const ADA: User = { id: 'u-1', email: 'ada@example.com', display_name: null, created_at: '2026-11-01T09:30:00Z' }
const OLD = 'old password 1'
const NEW = 'brand new password 2'

const days = (jobs: number[]) => jobs.map((count, i) => ({ date: `2026-11-${String(i + 6).padStart(2, '0')}`, jobs: count }))
const STATS: Stats = {
  jobs: { total: 12, queued: 1, running: 1, succeeded: 8, failed: 2 },
  success_rate: 0.8,
  average_total_seconds: 372,
  average_critic_score: 81.5,
  approval_rate: 0.625,
  average_aws_services: 9.2,
  jobs_last_7_days: 5,
  jobs_last_30_days: 12,
  first_job_at: '2026-11-03T08:00:00Z',
  last_job_at: '2026-11-19T07:00:00Z',
  daily: days([0, 0, 1, 0, 0, 2, 0, 0, 0, 3, 0, 1, 0, 5]),
  sample_size: 8,
  sample_capped: false,
}
const NO_JOBS: Stats = {
  ...STATS,
  jobs: { total: 0, queued: 0, running: 0, succeeded: 0, failed: 0 },
  success_rate: null,
  average_total_seconds: null,
  average_critic_score: null,
  approval_rate: null,
  average_aws_services: null,
  jobs_last_7_days: 0,
  jobs_last_30_days: 0,
  first_job_at: null,
  last_job_at: null,
  daily: days(Array(14).fill(0)),
  sample_size: 0,
}
const PROVIDERS = [{ id: 'groq', label: 'Groq', default_model: 'groq-default', key_url: 'https://console.groq.com/keys' }]
const NO_KEY: LLMSettings = { configured: false, provider: null, model: null, key_hint: null, updated_at: null, encryption_available: true, providers: PROVIDERS }
const OWN_KEY: LLMSettings = { ...NO_KEY, configured: true, provider: 'groq', key_hint: 'cdef', updated_at: '2026-11-19T10:00:00Z' }

type Reply = { status: number; body?: unknown } | 'network-error'
interface Overrides {
  me?: User
  stats?: Reply
  llm?: LLMSettings
  patch?: (body: { display_name: string | null }) => Reply
  password?: (body: { current_password: string; new_password: string }) => Reply
}

/** A tiny fake of the account endpoints that remembers what was sent. */
function fakeApi({ me = ADA, stats = { status: 200, body: STATS }, llm = NO_KEY, patch, password }: Overrides = {}) {
  const state = { me, patches: [] as Array<{ display_name: string | null }>, passwords: [] as Array<{ current_password: string; new_password: string }>, calls: [] as string[] }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      state.calls.push(`${method} ${path}`)
      const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
      let reply: Reply
      if (`${method} ${path}` === 'GET /api/v1/auth/me') reply = { status: 200, body: state.me }
      else if (`${method} ${path}` === 'GET /api/v1/stats') reply = stats
      else if (`${method} ${path}` === 'GET /api/v1/settings/llm') reply = { status: 200, body: llm }
      else if (`${method} ${path}` === 'PATCH /api/v1/auth/me') {
        const sent = body as { display_name: string | null }
        state.patches.push(sent)
        reply =
          patch?.(sent) ??
          (() => {
            state.me = { ...state.me, display_name: sent.display_name }
            return { status: 200, body: state.me }
          })()
      } else if (`${method} ${path}` === 'POST /api/v1/auth/password') {
        const sent = body as { current_password: string; new_password: string }
        state.passwords.push(sent)
        reply = password?.(sent) ?? { status: 204 }
      } else throw new Error(`unexpected request ${method} ${path}`)
      if (reply === 'network-error') throw new TypeError('Failed to fetch')
      return new Response(reply.status === 204 ? null : JSON.stringify(reply.body), { status: reply.status })
    }),
  )
  return state
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AccountMenu />
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

const nameBox = () => screen.getByRole('textbox', { name: 'Display name' }) as HTMLInputElement
const form = (name: string) => within(screen.getByRole('form', { name }))

afterEach(() => {
  cleanup()
  useToastStore.setState({ toasts: [] })
  vi.unstubAllGlobals()
})

describe('display name validation', () => {
  it('trims and collapses whitespace, and checks the length', () => {
    expect(normaliseDisplayName('  Ada   Lovelace ')).toBe('Ada Lovelace')
    expect(validateDisplayName('')).toBeUndefined()
    expect(validateDisplayName('   ')).toBeUndefined()
    expect(validateDisplayName('A')).toMatch(/2 to 60/)
    expect(validateDisplayName('x'.repeat(61))).toMatch(/2 to 60/)
    expect(validateDisplayName('Åda 🙂')).toBeUndefined()
  })
})

describe('Settings: account', () => {
  it('shows the email and member-since as read-only facts', async () => {
    fakeApi()
    renderPage()
    const account = await screen.findByText('Email (your sign-in)')
    expect(account.parentElement?.textContent).toContain('ada@example.com')
    expect(screen.getByText('Member since').parentElement?.textContent).toMatch(/Nov 1, 2026/)
    expect(screen.queryByLabelText('Email')).toBeNull() // not an input
  })

  it('saves a display name and the header shows it instead of the email', async () => {
    const api = fakeApi()
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    expect(screen.getByTestId('account-email').textContent).toBe('ada@example.com')
    expect((form('Display name').getByRole('button', { name: 'Save name' }) as HTMLButtonElement).disabled).toBe(true)

    await user.type(nameBox(), '  Ada   Lovelace ')
    await user.click(form('Display name').getByRole('button', { name: 'Save name' }))

    await waitFor(() => expect(api.patches).toEqual([{ display_name: 'Ada Lovelace' }]))
    await waitFor(() => expect(screen.getByTestId('account-email').textContent).toBe('Ada Lovelace'))
    expect(screen.getByTestId('account-email').getAttribute('title')).toBe('ada@example.com')
    expect(useToastStore.getState().toasts.map((t) => t.title)).toEqual(['Display name saved'])
  })

  it('clears the display name when the box is emptied', async () => {
    const api = fakeApi({ me: { ...ADA, display_name: 'Ada' } })
    const user = renderPage()
    await waitFor(() => expect(nameBox().value).toBe('Ada'))
    await user.clear(nameBox())
    await user.click(form('Display name').getByRole('button', { name: 'Save name' }))
    await waitFor(() => expect(api.patches).toEqual([{ display_name: null }]))
    await waitFor(() => expect(screen.getByTestId('account-email').textContent).toBe('ada@example.com'))
    expect(useToastStore.getState().toasts.map((t) => t.title)).toEqual(['Display name cleared'])
  })

  it('checks the length before sending anything', async () => {
    const api = fakeApi()
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    await user.type(nameBox(), 'A')
    await user.click(form('Display name').getByRole('button', { name: 'Save name' }))
    expect(screen.getByText(/The display name must be 2 to 60 characters/)).toBeTruthy()
    expect(api.patches).toEqual([])
  })

  it('shows a server error in the form', async () => {
    fakeApi({ patch: () => ({ status: 503, body: { detail: 'Account store is unavailable. Please retry later.' } }) })
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    await user.type(nameBox(), 'Ada')
    await user.click(form('Display name').getByRole('button', { name: 'Save name' }))
    expect((await screen.findByRole('alert', {}, { timeout: 4000 })).textContent).toBe('Account store is unavailable. Please retry later.')
    expect(nameBox().value).toBe('Ada')
  })

  it('says which AI provider is in use, with a link to change it', async () => {
    fakeApi({ llm: OWN_KEY })
    renderPage()
    const row = within(await screen.findByTestId('provider-row'))
    expect(await row.findByText('Your own key')).toBeTruthy()
    expect(row.getByText('key ending …cdef')).toBeTruthy()
    expect(row.getByRole('link', { name: /Manage/ }).getAttribute('href')).toBe('/byok')
  })

  it('says it is the server default when there is no own key', async () => {
    fakeApi({ llm: NO_KEY })
    renderPage()
    expect(await within(await screen.findByTestId('provider-row')).findByText('Server default')).toBeTruthy()
  })
})

describe('Settings: password', () => {
  const fill = async (user: ReturnType<typeof userEvent.setup>, current: string, next: string, confirmation: string) => {
    const f = form('Change password')
    if (current) await user.type(f.getByLabelText('Current password'), current)
    if (next) await user.type(f.getByLabelText('New password'), next)
    if (confirmation) await user.type(f.getByLabelText('Confirm new password'), confirmation)
    await user.click(f.getByRole('button', { name: 'Change password' }))
  }

  it('checks the fields before sending anything', async () => {
    const api = fakeApi()
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')

    await fill(user, '', '', '')
    expect(screen.getByText('Enter your password.')).toBeTruthy()
    expect(screen.getByText('Choose a password.')).toBeTruthy()
    expect(screen.getByText('Enter the password again.')).toBeTruthy()
    expect(api.passwords).toEqual([])
  })

  it('rejects a short new password, a mismatch, and reusing the current password', async () => {
    const api = fakeApi()
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    await fill(user, OLD, 'short', 'different')
    expect(screen.getByText('Use at least 8 characters.')).toBeTruthy()
    expect(screen.getByText("The passwords don't match.")).toBeTruthy()

    cleanup()
    fakeApi()
    const second = renderPage()
    await screen.findByText('Email (your sign-in)')
    await fill(second, OLD, OLD, OLD)
    expect(screen.getByText('Choose a password different from your current one.')).toBeTruthy()
    expect(api.passwords).toEqual([])
  })

  it('changes the password, empties the boxes and says other devices were signed out', async () => {
    const api = fakeApi()
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    await fill(user, OLD, NEW, NEW)

    await waitFor(() => expect(api.passwords).toEqual([{ current_password: OLD, new_password: NEW }]))
    await waitFor(() => expect((form('Change password').getByLabelText('Current password') as HTMLInputElement).value).toBe(''))
    expect((form('Change password').getByLabelText('New password') as HTMLInputElement).value).toBe('')
    const toast = useToastStore.getState().toasts[0]
    expect([toast.title, toast.description]).toEqual(['Password changed', 'You were signed out on every other device.'])
    expect(screen.queryByRole('alert')).toBeNull()
    // The session this browser has is untouched: no sign-out request is made.
    expect(api.calls.some((c) => c.includes('logout'))).toBe(false)
  })

  it('a wrong current password is shown on that field, and the new password stays typed', async () => {
    fakeApi({ password: () => ({ status: 400, body: { detail: 'The current password is incorrect.' } }) })
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    await fill(user, 'wrong password', NEW, NEW)
    expect(await screen.findByText('The current password is incorrect.')).toBeTruthy()
    expect(form('Change password').getByLabelText('Current password').getAttribute('aria-invalid')).toBe('true')
    expect(screen.queryByRole('alert')).toBeNull()
    expect((form('Change password').getByLabelText('New password') as HTMLInputElement).value).toBe(NEW)
  })

  it('shows a field message from a 422', async () => {
    fakeApi({ password: () => ({ status: 422, body: { detail: [{ type: 'value_error', loc: ['body', 'new_password'], msg: 'Choose a password different from your current one.' }] } }) })
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    await fill(user, OLD, NEW, NEW)
    expect(await screen.findByText('Choose a password different from your current one.')).toBeTruthy()
  })

  it('shows an unreachable API in the form', async () => {
    fakeApi({ password: () => 'network-error' })
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    await fill(user, OLD, NEW, NEW)
    expect((await screen.findByRole('alert', {}, { timeout: 4000 })).textContent).toMatch(/Can't reach the ArchonAI API/)
  })

  it('never keeps a password in browser storage', async () => {
    fakeApi()
    const user = renderPage()
    await screen.findByText('Email (your sign-in)')
    await fill(user, OLD, NEW, NEW)
    await waitFor(() => expect(useToastStore.getState().toasts).toHaveLength(1))
    const stored = JSON.stringify({ ...localStorage, ...sessionStorage })
    expect(stored).not.toContain(OLD)
    expect(stored).not.toContain(NEW)
  })
})

describe('Settings: statistics', () => {
  it('shows the numbers', async () => {
    fakeApi()
    renderPage()
    await screen.findByText('Total jobs')
    const value = (label: string) => screen.getByText(label).closest('dl')?.textContent ?? ''
    expect(value('Total jobs')).toContain('12')
    expect(value('Total jobs')).toContain('8 succeeded · 2 failed')
    expect(value('Success rate')).toContain('80%')
    expect(value('Success rate')).toContain('of 10 finished jobs')
    expect(value('Average time to finish')).toContain('6m 12s')
    expect(value('Average critic score')).toContain('81.5/100')
    expect(value('Average critic score')).toContain('63% approved by the critic')
    expect(value('Average AWS services')).toContain('9.2')
    expect(value('Last 7 days')).toContain('5')
    expect(value('Last 7 days')).toContain('12 in the last 30 days')
    expect(screen.getByText(/Averages are based on your 8 succeeded jobs\./)).toBeTruthy()
    expect(screen.getByText('First job:').parentElement?.textContent).toMatch(/Nov 3, 2026/)
    expect(screen.getByText('Latest job:').parentElement?.textContent).toMatch(/Nov 19, 2026/)
  })

  it('says when the averages come from only the newest jobs', async () => {
    fakeApi({ stats: { status: 200, body: { ...STATS, sample_size: 500, sample_capped: true } } })
    renderPage()
    expect(await screen.findByText(/Averages are based on your newest 500 succeeded jobs\./)).toBeTruthy()
  })

  it('draws the last 14 days, with the numbers also in a table for screen readers', async () => {
    fakeApi()
    renderPage()
    const table = await screen.findByRole('table', { name: /Jobs submitted per day, last 14 days/ })
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(14)
    expect(rows.map((r) => r.querySelector('td')?.textContent)).toEqual(['0', '0', '1', '0', '0', '2', '0', '0', '0', '3', '0', '1', '0', '5'])
    expect(screen.getByText(/Jobs per day over the last 14 days \(UTC\): 12 in total\./)).toBeTruthy()
  })

  it('shows dashes, not made-up numbers, while there is nothing to average', async () => {
    fakeApi({ stats: { status: 200, body: { ...STATS, success_rate: null, average_total_seconds: null, average_critic_score: null, approval_rate: null, average_aws_services: null, jobs: { total: 1, queued: 1, running: 0, succeeded: 0, failed: 0 }, sample_size: 0 } } })
    renderPage()
    const card = await screen.findByText('Success rate')
    expect(card.closest('dl')?.textContent).toContain('—')
    expect(card.closest('dl')?.textContent).toContain('No finished jobs yet')
    expect(screen.getByText('Average critic score').closest('dl')?.textContent).toContain('No reviews yet')
    expect(screen.queryByText(/Averages are based on/)).toBeNull()
  })

  it('a new account sees an empty state with a way to start', async () => {
    fakeApi({ stats: { status: 200, body: NO_JOBS } })
    renderPage()
    expect(await screen.findByText('No jobs yet')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'New Architecture' }).getAttribute('href')).toBe('/architectures/new')
    expect(screen.queryByText('Total jobs')).toBeNull()
  })

  it('shows an error with retry when the statistics cannot be loaded', async () => {
    const api = fakeApi({ stats: { status: 503, body: { detail: 'Job store is unavailable. Please retry later.' } } })
    renderPage()
    expect(await screen.findByText("Couldn't load your statistics", {}, { timeout: 4000 })).toBeTruthy()
    expect(screen.getByText('Job store is unavailable. Please retry later.')).toBeTruthy()
    const before = api.calls.filter((c) => c === 'GET /api/v1/stats').length
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(api.calls.filter((c) => c === 'GET /api/v1/stats').length).toBeGreaterThan(before))
  })
})
