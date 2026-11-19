/**
 * Sign-in, registration, the route guard and sign-out, against a stubbed API.
 * fetch is replaced in every test: nothing reaches a real backend.
 */
import { QueryClientProvider, useQuery, type QueryClient } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, Outlet, RouterProvider, useLocation } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiRequest } from '@/api/client'
import { createAppQueryClient } from '@/app/providers'
import { useToastStore } from '@/stores/toast.store'
import type { User } from '@/types/api'

import { WelcomePage } from '@/features/welcome/WelcomePage'

import { AccountMenu } from './AccountMenu'
import { LoginPage } from './LoginPage'
import { RegisterPage } from './RegisterPage'
import { RequireAuth } from './RequireAuth'
import { ME_QUERY_KEY } from './useAuth'

const ADA: User = { id: 'u-1', email: 'ada@example.com', display_name: null, created_at: '2026-11-18T10:00:00Z' }
const PASSWORD = 'correct horse'

type Reply = { status: number; body?: unknown } | 'network-error' | 'pending'

/** A tiny fake of the auth API. `signedIn` plays the role of the session cookie. */
function fakeApi(overrides: Partial<Record<string, (body: unknown) => Reply>> = {}) {
  const state = { signedIn: null as User | null, calls: [] as Array<{ method: string; path: string; body: unknown }> }
  const routes: Record<string, (body: unknown) => Reply> = {
    'GET /api/v1/auth/me': () => (state.signedIn ? { status: 200, body: state.signedIn } : { status: 401, body: { detail: 'Not signed in, or the session has expired.' } }),
    'POST /api/v1/auth/login': (body) => {
      const { email, password } = body as { email: string; password: string }
      if (email.toLowerCase() === ADA.email && password === PASSWORD) {
        state.signedIn = ADA
        return { status: 200, body: ADA }
      }
      return { status: 401, body: { detail: 'Invalid email or password.' } }
    },
    'POST /api/v1/auth/register': (body) => {
      const { email } = body as { email: string }
      if (email.toLowerCase() === ADA.email) return { status: 409, body: { detail: 'An account with this email already exists.' } }
      state.signedIn = { ...ADA, id: 'u-2', email: email.toLowerCase() }
      return { status: 201, body: state.signedIn }
    },
    'POST /api/v1/auth/logout': () => {
      state.signedIn = null
      return { status: 204 }
    },
    'GET /api/v1/private': () => ({ status: 401, body: { detail: 'Not signed in, or the session has expired.' } }),
    ...overrides,
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
      state.calls.push({ method, path, body })
      const handler = routes[`${method} ${path}`]
      const reply: Reply = handler ? handler(body) : { status: 404, body: { detail: 'Not Found' } }
      if (reply === 'network-error') throw new TypeError('Failed to fetch')
      if (reply === 'pending') return new Promise<Response>(() => {})
      return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), { status: reply.status })
    }),
  )
  return state
}

function Shell() {
  const location = useLocation()
  return (
    <div>
      <AccountMenu />
      <p data-testid="location">{`${location.pathname}${location.search}`}</p>
      <Outlet />
    </div>
  )
}

/** A page that calls a protected endpoint, to check that any 401 signs the user out. */
function PrivatePage() {
  useQuery({ queryKey: ['private'], queryFn: () => apiRequest('/api/v1/private') })
  return <p>Private page</p>
}

function renderApp(path: string, client: QueryClient = createAppQueryClient()) {
  const router = createMemoryRouter(
    [
      { path: '/welcome', element: <WelcomePage /> },
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
      {
        path: '/',
        element: (
          <RequireAuth>
            <Shell />
          </RequireAuth>
        ),
        children: [
          { path: 'dashboard', element: <p>Dashboard page</p> },
          { path: 'architectures/:jobId', element: <p>Job page</p> },
          { path: 'private', element: <PrivatePage /> },
        ],
      },
    ],
    { initialEntries: [path] },
  )
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { router, client, user: userEvent.setup() }
}

const where = (router: ReturnType<typeof createMemoryRouter>) => `${router.state.location.pathname}${router.state.location.search}`

async function fillLogin(user: ReturnType<typeof userEvent.setup>, email: string, password: string) {
  await user.type(await screen.findByLabelText('Email'), email)
  await user.type(screen.getByLabelText('Password'), password)
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
}

afterEach(() => {
  cleanup()
  useToastStore.setState({ toasts: [] })
})

describe('route guard', () => {
  it('shows a spinner while the session is checked', () => {
    fakeApi({ 'GET /api/v1/auth/me': () => 'pending' })
    renderApp('/dashboard')
    expect(screen.getByText('Checking your sign-in')).toBeTruthy()
    expect(screen.queryByText('Dashboard page')).toBeNull()
  })

  it('sends a signed-out visitor to sign in, remembering where they were going', async () => {
    fakeApi()
    const { router } = renderApp('/architectures/abc?x=1')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeTruthy()
    expect(where(router)).toBe('/login?next=%2Farchitectures%2Fabc%3Fx%3D1')
    expect(screen.queryByText('Job page')).toBeNull()
  })

  it('lets a signed-in user straight in and shows their email', async () => {
    const api = fakeApi()
    api.signedIn = ADA
    renderApp('/dashboard')
    expect(await screen.findByText('Dashboard page')).toBeTruthy()
    expect(screen.getByTestId('account-email').textContent).toBe(ADA.email)
  })

  it('a signed-in user opening /login goes to the app instead', async () => {
    const api = fakeApi()
    api.signedIn = ADA
    const { router } = renderApp('/login?next=%2Farchitectures%2Fabc')
    expect(await screen.findByText('Job page')).toBeTruthy()
    expect(where(router)).toBe('/architectures/abc')
  })

  it.each([
    [{ status: 503, body: { detail: 'Authentication is not configured.' } }, 'Authentication is not configured.'],
    [{ status: 404, body: { detail: 'Not Found' } }, 'This API has no sign-in endpoints. Update and restart the ArchonAI backend, then try again.'],
    ['network-error' as const, "Can't reach the ArchonAI API. Check that the backend is running, then try again."],
  ])('when the session cannot be checked: an error with a retry (%#)', async (reply, message) => {
    const api = fakeApi({ 'GET /api/v1/auth/me': () => reply })
    const { user } = renderApp('/dashboard')
    // 503 and network errors get the app's one automatic retry (about 1 s) before the error shows.
    expect(await screen.findByText("Can't check your sign-in", {}, { timeout: 3000 })).toBeTruthy()
    expect(screen.getByText(message)).toBeTruthy()
    const before = api.calls.length
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(api.calls.length).toBeGreaterThan(before))
  })

  it('any 401 from the API signs the user out and sends them to sign in', async () => {
    const api = fakeApi()
    api.signedIn = ADA
    const { router } = renderApp('/private')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeTruthy()
    expect(where(router)).toBe('/login?next=%2Fprivate')
  })
})

describe('welcome page', () => {
  const HERO = 'Turn your requirements into a reviewed AWS architecture'

  it.each(['/', '/dashboard'])('a signed-out visitor opening %s sees the welcome page first', async (path) => {
    fakeApi()
    const { router } = renderApp(path)
    expect(await screen.findByRole('heading', { level: 1, name: HERO })).toBeTruthy()
    expect(where(router)).toBe('/welcome')
    expect(screen.queryByText('Dashboard page')).toBeNull()
  })

  it('explains the app and offers both ways in', async () => {
    fakeApi()
    renderApp('/welcome')
    await screen.findByRole('heading', { level: 1, name: HERO })
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      'Architecture design',
      'Critic review',
      'Cost estimate',
      'Report and trace',
      'Describe your system',
      'The agents get to work',
      'Explore the results',
    ])
    const hrefs = (name: string) => screen.getAllByRole('link', { name }).map((a) => a.getAttribute('href'))
    expect(hrefs('Get started')).toEqual(['/register'])
    expect(hrefs('Create account')).toEqual(['/register', '/register'])
    expect(hrefs('Sign in')).toEqual(['/login', '/login', '/login'])
    expect(document.title).toBe('Welcome · ArchonAI')
  })

  it('Get started opens registration, and Back to welcome returns', async () => {
    fakeApi()
    const { user, router } = renderApp('/welcome')
    await user.click(await screen.findByRole('link', { name: 'Get started' }))
    expect(await screen.findByRole('heading', { name: 'Create an account' })).toBeTruthy()
    await user.click(screen.getByRole('link', { name: 'Back to welcome' }))
    expect(await screen.findByRole('heading', { level: 1, name: HERO })).toBeTruthy()
    expect(where(router)).toBe('/welcome')
  })

  it('the sign-in page links back to welcome too', async () => {
    fakeApi()
    renderApp('/login')
    expect((await screen.findByRole('link', { name: 'Back to welcome' })).getAttribute('href')).toBe('/welcome')
  })

  it('a signed-in user opening /welcome goes straight to the dashboard', async () => {
    const api = fakeApi()
    api.signedIn = ADA
    const { router } = renderApp('/welcome')
    expect(await screen.findByText('Dashboard page')).toBeTruthy()
    expect(where(router)).toBe('/dashboard')
  })
})

describe('sign in', () => {
  it('checks the fields before sending anything', async () => {
    const api = fakeApi()
    const { user } = renderApp('/login')
    await user.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(screen.getByText('Enter your email address.')).toBeTruthy()
    expect(screen.getByText('Enter your password.')).toBeTruthy()
    expect(screen.getByLabelText('Email').getAttribute('aria-invalid')).toBe('true')
    expect(api.calls.filter((c) => c.method === 'POST')).toEqual([])
  })

  it('wrong credentials: a generic message, still signed out', async () => {
    fakeApi()
    const { user, router } = renderApp('/login')
    await fillLogin(user, ADA.email, 'wrong password')
    expect((await screen.findByRole('alert')).textContent).toBe('Invalid email or password.')
    expect(where(router)).toBe('/login')
  })

  it('success: continues to the page the user wanted, with the email trimmed', async () => {
    const api = fakeApi()
    const { user, router } = renderApp('/architectures/abc')
    await fillLogin(user, `  ${ADA.email} `, PASSWORD)
    expect(await screen.findByText('Job page')).toBeTruthy()
    expect(where(router)).toBe('/architectures/abc')
    expect(api.calls.find((c) => c.path.endsWith('/login'))?.body).toEqual({ email: ADA.email, password: PASSWORD })
  })

  it('an unsafe ?next= is ignored after sign-in', async () => {
    fakeApi()
    const { user, router } = renderApp('/login?next=%2F%2Fevil.example')
    await fillLogin(user, ADA.email, PASSWORD)
    expect(await screen.findByText('Dashboard page')).toBeTruthy()
    expect(where(router)).toBe('/dashboard')
  })

  it('shows the server-side field message for a 422', async () => {
    fakeApi({
      'POST /api/v1/auth/login': () => ({ status: 422, body: { detail: [{ type: 'value_error', loc: ['body', 'email'], msg: 'Value error, Enter a valid email address.' }] } }),
    })
    const { user } = renderApp('/login')
    await fillLogin(user, 'ada@example.com', PASSWORD)
    expect(await screen.findByText('Value error, Enter a valid email address.')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('an unreachable API is reported in the form', async () => {
    fakeApi({ 'POST /api/v1/auth/login': () => 'network-error' })
    const { user } = renderApp('/login')
    await fillLogin(user, ADA.email, PASSWORD)
    expect((await screen.findByRole('alert')).textContent).toMatch(/Can't reach the ArchonAI API/)
  })

  it('the password can be shown and hidden', async () => {
    fakeApi()
    const { user } = renderApp('/login')
    const input = (await screen.findByLabelText('Password')) as HTMLInputElement
    expect(input.type).toBe('password')
    await user.click(screen.getByRole('button', { name: 'Show password' }))
    expect(input.type).toBe('text')
    expect(screen.getByRole('button', { name: 'Hide password' }).getAttribute('aria-pressed')).toBe('true')
  })

  it('links to registration, keeping ?next=', async () => {
    fakeApi()
    renderApp('/login?next=%2Farchitectures%2Fabc')
    expect((await screen.findByRole('link', { name: 'Create an account' })).getAttribute('href')).toBe('/register?next=%2Farchitectures%2Fabc')
  })
})

describe('registration', () => {
  const fill = async (user: ReturnType<typeof userEvent.setup>, email: string, password: string, confirmation: string) => {
    await user.type(await screen.findByLabelText('Email'), email)
    await user.type(screen.getByLabelText('Password'), password)
    await user.type(screen.getByLabelText('Confirm password'), confirmation)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
  }

  it('checks email, password length and confirmation before sending', async () => {
    const api = fakeApi()
    const { user } = renderApp('/register')
    await fill(user, 'not-an-email', 'short', 'different')
    expect(screen.getByText('Enter a valid email address, like you@example.com.')).toBeTruthy()
    expect(screen.getByText('Use at least 8 characters.')).toBeTruthy()
    expect(screen.getByText("The passwords don't match.")).toBeTruthy()
    expect(api.calls.filter((c) => c.method === 'POST')).toEqual([])
  })

  it('an email that is already registered: says so and offers sign-in', async () => {
    fakeApi()
    const { user } = renderApp('/register?next=%2Farchitectures%2Fabc')
    await fill(user, ADA.email, PASSWORD, PASSWORD)
    const message = await screen.findByText(/An account with this email already exists\./)
    expect(within(message).getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/login?next=%2Farchitectures%2Fabc')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('success: signed in, a confirmation toast, and on to the app', async () => {
    const api = fakeApi()
    const { user, router } = renderApp('/register')
    await fill(user, 'Grace@Example.com', PASSWORD, PASSWORD)
    expect(await screen.findByText('Dashboard page')).toBeTruthy()
    expect(where(router)).toBe('/dashboard')
    expect(screen.getByTestId('account-email').textContent).toBe('grace@example.com')
    expect(useToastStore.getState().toasts.map((t) => t.title)).toEqual(['Account created'])
    expect(api.calls.find((c) => c.path.endsWith('/register'))?.body).toEqual({ email: 'Grace@Example.com', password: PASSWORD })
  })

  it('a server error that is not about a field is shown in the form', async () => {
    fakeApi({ 'POST /api/v1/auth/register': () => ({ status: 503, body: { detail: 'Authentication is not configured.' } }) })
    const { user } = renderApp('/register')
    await fill(user, 'grace@example.com', PASSWORD, PASSWORD)
    expect((await screen.findByRole('alert')).textContent).toBe('Authentication is not configured.')
  })
})

describe('sign out', () => {
  it('ends the session, drops cached data and returns to sign in', async () => {
    const api = fakeApi()
    api.signedIn = ADA
    const { user, router, client } = renderApp('/dashboard')
    await screen.findByText('Dashboard page')
    act(() => client.setQueryData(['architectures', 'job', 'secret-job'], { job_id: 'secret-job' }))

    await user.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeTruthy()
    expect(where(router)).toBe('/login')
    expect(api.calls.some((c) => c.method === 'POST' && c.path === '/api/v1/auth/logout')).toBe(true)
    expect(client.getQueryData(['architectures', 'job', 'secret-job'])).toBeUndefined()
    expect(client.getQueryData(ME_QUERY_KEY)).toBeNull()
  })

  it('a failed sign-out keeps the user signed in and says so', async () => {
    const api = fakeApi({ 'POST /api/v1/auth/logout': () => 'network-error' })
    api.signedIn = ADA
    const { user } = renderApp('/dashboard')
    await user.click(await screen.findByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(useToastStore.getState().toasts.map((t) => t.title)).toEqual(["Couldn't sign out"]))
    expect(screen.getByText('Dashboard page')).toBeTruthy()
  })
})
