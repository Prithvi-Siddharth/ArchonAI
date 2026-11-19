/**
 * Finish alerts: working out which jobs just finished, the toast and desktop notification, and the
 * Settings card. fetch and the browser's Notification are stubbed in every test: nothing reaches a
 * real backend and no real notification is shown.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Toaster } from '@/components/ui'
import { HISTORY_QUERY_KEY } from '@/features/architectures/history/useJobHistory'
import { useToastStore } from '@/stores/toast.store'
import type { JobHistoryItem, JobHistoryResponse } from '@/types/api'
import type { JobStatus } from '@/types/architecture'

import { DESKTOP_PREF_STORAGE_KEY, useDesktopPref } from './desktop'
import { FinishAlerts } from './FinishAlerts'
import { ALERTED_STORAGE_KEY, alertText, claimAlert, newlyFinished, statusMap } from './finish-alerts'
import { NotificationsCard } from './NotificationsCard'

const SUMMARY = { approved: true, critic_score: 80, architecture_version: 1, aws_service_count: 8, estimated_monthly_range: '$1', max_revisions_reached: false }
const REQUEST = 'Design a video streaming platform for 2 million daily users with 4K playback'

function job(n: number, status: JobStatus, overrides: Partial<JobHistoryItem> = {}): JobHistoryItem {
  const finished = status === 'succeeded' || status === 'failed'
  return {
    job_id: `${String(n).padStart(8, '0')}-aaaa-bbbb-cccc-dddddddddddd`,
    user_request: REQUEST,
    status,
    attempts: status === 'queued' ? 0 : 1,
    created_at: new Date(Date.now() - n * 60_000).toISOString(),
    started_at: status === 'queued' ? null : new Date().toISOString(),
    finished_at: finished ? new Date().toISOString() : null,
    updated_at: new Date().toISOString(),
    error: status === 'failed' ? { status_code: 429, message: 'LLM provider rate limit reached. Please retry later.' } : null,
    summary: status === 'succeeded' ? SUMMARY : null,
    ...overrides,
  }
}

// --- Fake browser Notification ------------------------------------------------------------------

class FakeNotification {
  static permission: NotificationPermission = 'granted'
  static instances: FakeNotification[] = []
  static requestPermission = vi.fn(async () => FakeNotification.permission)
  onclick: (() => void) | null = null
  close = vi.fn()
  title: string
  options: NotificationOptions
  constructor(title: string, options: NotificationOptions) {
    this.title = title
    this.options = options
    FakeNotification.instances.push(this)
  }
}

const tab = { visibility: 'visible' as DocumentVisibilityState, focused: true }

beforeEach(() => {
  localStorage.clear()
  FakeNotification.permission = 'granted'
  FakeNotification.instances = []
  FakeNotification.requestPermission.mockClear()
  vi.stubGlobal('Notification', FakeNotification)
  tab.visibility = 'visible'
  tab.focused = true
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => tab.visibility })
  vi.spyOn(document, 'hasFocus').mockImplementation(() => tab.focused)
  useDesktopPref.setState({ enabled: false })
  useToastStore.setState({ toasts: [] })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  Reflect.deleteProperty(document, 'visibilityState')
})

const goAway = () => {
  tab.visibility = 'hidden'
  tab.focused = false
}
const toasts = () => useToastStore.getState().toasts

// --- Pure logic ---------------------------------------------------------------------------------

describe('which jobs just finished', () => {
  it('reports jobs that were queued or running and are now succeeded or failed', () => {
    const before = statusMap([job(1, 'queued'), job(2, 'running'), job(3, 'running'), job(4, 'succeeded')])
    const now = [job(1, 'succeeded'), job(2, 'failed'), job(3, 'running'), job(4, 'succeeded')]
    expect(newlyFinished(before, now).map((j) => j.job_id.slice(0, 8))).toEqual(['00000001', '00000002'])
  })

  it('never reports a job it has not seen unfinished (opening the app does not replay old results)', () => {
    expect(newlyFinished(statusMap([]), [job(1, 'succeeded'), job(2, 'failed')])).toEqual([])
    expect(newlyFinished(statusMap([job(1, 'succeeded')]), [job(1, 'succeeded')])).toEqual([])
  })

  it('a job waiting to retry is still queued, so it is not a finish', () => {
    const waiting = job(1, 'queued', { error: { status_code: 429, message: 'rate limit' }, attempts: 1 })
    expect(newlyFinished(statusMap([job(1, 'running')]), [waiting])).toEqual([])
    expect(newlyFinished(statusMap([waiting]), [job(1, 'failed')])).toHaveLength(1)
  })

  it('a job that moves on from running to running, or drops out of the list, is not a finish', () => {
    expect(newlyFinished(statusMap([job(1, 'running'), job(2, 'running')]), [job(1, 'running')])).toEqual([])
  })
})

describe('one alert per job', () => {
  it('the first claim wins and later ones lose, across tabs (shared storage)', () => {
    expect(claimAlert('job-1')).toBe(true)
    expect(claimAlert('job-1')).toBe(false)
    expect(claimAlert('job-2')).toBe(true)
  })

  it('remembers only the newest 50, and survives corrupt storage', () => {
    for (let i = 0; i < 60; i++) claimAlert(`job-${i}`)
    expect(JSON.parse(localStorage.getItem(ALERTED_STORAGE_KEY) ?? '[]')).toHaveLength(50)
    localStorage.setItem(ALERTED_STORAGE_KEY, '{not json')
    expect(claimAlert('fresh')).toBe(true)
  })
})

describe('the words of an alert', () => {
  it('success with results opens the results', () => {
    const text = alertText(job(1, 'succeeded'))
    expect(text).toMatchObject({ title: 'Architecture ready', tone: 'success', actionLabel: 'View results', path: `/architectures/${job(1, 'succeeded').job_id}/results` })
    expect(text.body.length).toBeLessThanOrEqual(70)
    expect(text.body.endsWith('…')).toBe(true)
  })

  it('success without a result summary opens the job page instead', () => {
    expect(alertText(job(1, 'succeeded', { summary: null }))).toMatchObject({ actionLabel: 'View job', path: `/architectures/${job(1, 'succeeded').job_id}` })
  })

  it('failure carries the error message and opens the job page', () => {
    const text = alertText(job(1, 'failed'))
    expect(text).toMatchObject({ title: 'Generation failed', tone: 'danger', actionLabel: 'View job' })
    expect(text.body).toContain('LLM provider rate limit reached.')
  })

  it('an empty request still reads sensibly', () => {
    expect(alertText(job(1, 'failed', { user_request: '   ', error: null })).body).toBe('Your request')
  })
})

// --- The watcher --------------------------------------------------------------------------------

function Where() {
  const location = useLocation()
  return <p data-testid="where">{location.pathname}</p>
}

/** Renders the watcher with a fake job list. `setJobs` changes what the next read returns. */
function watch(initial: JobHistoryItem[], path = '/dashboard') {
  let jobs = initial
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input, 'http://localhost')
      if (url.pathname !== '/api/v1/architectures/jobs') throw new Error(`unexpected request ${input}`)
      const counts = { queued: 0, running: 0, succeeded: 0, failed: 0 }
      jobs.forEach((j) => counts[j.status]++)
      const body: JobHistoryResponse = { items: jobs, total: jobs.length, limit: 20, offset: 0, counts }
      return new Response(JSON.stringify(body), { status: 200 })
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(
    [
      {
        path: '*',
        element: (
          <>
            <FinishAlerts />
            <Toaster />
            <Where />
          </>
        ),
      },
    ],
    { initialEntries: [path] },
  )
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  const refresh = async (next: JobHistoryItem[]) => {
    jobs = next
    await act(async () => {
      await client.invalidateQueries({ queryKey: HISTORY_QUERY_KEY })
      // TanStack Query hands the new data to React a tick later.
      await new Promise((resolve) => setTimeout(resolve, 5))
    })
  }
  // Waits until the first read of the job list has landed, so the next change is seen as a change.
  const settle = async () => {
    await waitFor(() => expect(client.getQueriesData({ queryKey: HISTORY_QUERY_KEY }).some(([, data]) => data !== undefined)).toBe(true))
    await act(async () => void (await new Promise((resolve) => setTimeout(resolve, 5))))
  }
  return { refresh, settle, router }
}

describe('FinishAlerts', () => {
  it('stays quiet about jobs that were already finished when the app opened', async () => {
    const { refresh, settle } = watch([job(1, 'succeeded'), job(2, 'failed')])
    await settle()
    await refresh([job(1, 'succeeded'), job(2, 'failed')])
    expect(toasts()).toEqual([])
  })

  it('tells you when a running job succeeds, once, with a button to the results', async () => {
    const { refresh, settle, router } = watch([job(1, 'running')])
    await settle()
    expect(toasts()).toEqual([])

    await refresh([job(1, 'succeeded')])
    expect(toasts()).toHaveLength(1)
    expect(toasts()[0]).toMatchObject({ title: 'Architecture ready', tone: 'success', duration: 12_000 })
    expect(toasts()[0].action?.label).toBe('View results')

    await refresh([job(1, 'succeeded')]) // reading it again does not repeat the alert
    expect(toasts()).toHaveLength(1)

    await userEvent.click(await screen.findByRole('button', { name: 'View results' }))
    expect(router.state.location.pathname).toBe(`/architectures/${job(1, 'succeeded').job_id}/results`)
    expect(toasts()).toEqual([]) // using the button closes the toast
  })

  it('tells you when a job fails, with the reason', async () => {
    const { refresh, settle } = watch([job(1, 'queued')])
    await settle()
    await refresh([job(1, 'running')])
    expect(toasts()).toEqual([]) // starting is not finishing
    await refresh([job(1, 'failed')])
    expect(toasts()).toHaveLength(1)
    expect(toasts()[0]).toMatchObject({ title: 'Generation failed', tone: 'danger' })
    expect(toasts()[0].description).toContain('LLM provider rate limit reached.')
    expect(toasts()[0].action?.label).toBe('View job')
  })

  it('does not alert for a job that is only waiting to retry', async () => {
    const waiting = job(1, 'queued', { attempts: 1, error: { status_code: 429, message: 'rate limit' } })
    const { refresh, settle } = watch([job(1, 'running')])
    await settle()
    await refresh([waiting])
    expect(toasts()).toEqual([])
    await refresh([job(1, 'succeeded')])
    expect(toasts()).toHaveLength(1)
  })

  it('alerts for each of several jobs that finish together', async () => {
    const { refresh, settle } = watch([job(1, 'running'), job(2, 'running'), job(3, 'running')])
    await settle()
    await refresh([job(1, 'succeeded'), job(2, 'failed'), job(3, 'running')])
    expect(toasts().map((t) => t.title)).toEqual(['Architecture ready', 'Generation failed'])
  })

  it.each(['', '/results'])('does not pop up for the job you are already looking at (%s)', async (suffix) => {
    const { refresh, settle } = watch([job(1, 'running')], `/architectures/${job(1, 'running').job_id}${suffix}`)
    await settle()
    await refresh([job(1, 'succeeded')])
    expect(toasts()).toEqual([])
  })

  it('still pops up for a job when you are looking at a different one', async () => {
    const { refresh, settle } = watch([job(1, 'running'), job(2, 'running')], `/architectures/${job(2, 'running').job_id}`)
    await settle()
    await refresh([job(1, 'succeeded'), job(2, 'running')])
    expect(toasts()).toHaveLength(1)
  })

  it('does not announce a job another tab already announced', async () => {
    const { refresh, settle } = watch([job(1, 'running')])
    await settle()
    claimAlert(job(1, 'running').job_id) // the other tab got there first
    await refresh([job(1, 'succeeded')])
    expect(toasts()).toEqual([])
  })
})

describe('FinishAlerts: polling', () => {
  it('keeps checking every 10 seconds while the tab is hidden, and alerts without you coming back', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      useDesktopPref.setState({ enabled: true })
      let jobs = [job(1, 'running')]
      const reads: number[] = []
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => {
          reads.push(Date.now())
          const body: JobHistoryResponse = { items: jobs, total: jobs.length, limit: 20, offset: 0, counts: { queued: 0, running: 0, succeeded: 0, failed: 0 } }
          return new Response(JSON.stringify(body), { status: 200 })
        }),
      )
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const router = createMemoryRouter([{ path: '*', element: <FinishAlerts /> }], { initialEntries: ['/dashboard'] })
      render(
        <QueryClientProvider client={client}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      )
      await waitFor(() => expect(reads).toHaveLength(1))
      goAway()
      jobs = [job(1, 'succeeded')]
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_500)
      })
      expect(reads.length).toBeGreaterThanOrEqual(2) // it polled although the tab is hidden
      expect(toasts().map((t) => t.title)).toEqual(['Architecture ready'])
      expect(FakeNotification.instances.map((n) => n.title)).toEqual(['Architecture ready'])
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('FinishAlerts: desktop notification', () => {
  const finishOne = async (path?: string) => {
    const harness = watch([job(1, 'running')], path)
    await harness.settle()
    await harness.refresh([job(1, 'succeeded')])
    return harness
  }

  it('shows one when it is on, allowed, and the tab is out of sight', async () => {
    useDesktopPref.setState({ enabled: true })
    const { refresh, settle, router } = watch([job(1, 'running')])
    await settle()
    goAway()
    const focus = vi.spyOn(window, 'focus').mockImplementation(() => undefined)
    await refresh([job(1, 'succeeded')])

    expect(FakeNotification.instances).toHaveLength(1)
    const note = FakeNotification.instances[0]
    expect(note.title).toBe('Architecture ready')
    expect(note.options.tag).toBe(job(1, 'succeeded').job_id)
    expect(note.options.body).toContain('Design a video streaming platform')

    await act(async () => note.onclick?.())
    expect(focus).toHaveBeenCalled()
    expect(note.close).toHaveBeenCalled()
    expect(router.state.location.pathname).toBe(`/architectures/${job(1, 'succeeded').job_id}/results`)
  })

  it('also shows for a job you are looking at when the tab is in the background (the toast is skipped)', async () => {
    useDesktopPref.setState({ enabled: true })
    const { refresh, settle } = watch([job(1, 'running')], `/architectures/${job(1, 'running').job_id}`)
    await settle()
    goAway()
    await refresh([job(1, 'succeeded')])
    expect(toasts()).toEqual([])
    expect(FakeNotification.instances).toHaveLength(1)
  })

  it('does not show one while you are looking at the tab: the toast is enough', async () => {
    useDesktopPref.setState({ enabled: true })
    await finishOne()
    expect(toasts()).toHaveLength(1)
    expect(FakeNotification.instances).toEqual([])
  })

  it('does not show one when it is turned off', async () => {
    goAway()
    await finishOne()
    expect(toasts()).toHaveLength(1)
    expect(FakeNotification.instances).toEqual([])
  })

  it.each<NotificationPermission>(['default', 'denied'])('does not show one when the browser permission is "%s"', async (state) => {
    useDesktopPref.setState({ enabled: true })
    FakeNotification.permission = state
    goAway()
    await finishOne()
    expect(FakeNotification.instances).toEqual([])
    expect(toasts()).toHaveLength(1)
  })

  it('a browser without notifications still gets the toast, and nothing breaks', async () => {
    vi.stubGlobal('Notification', undefined)
    useDesktopPref.setState({ enabled: true })
    goAway()
    await finishOne()
    expect(toasts()).toHaveLength(1)
  })

  it('a browser that refuses to build a notification does not break the alert', async () => {
    useDesktopPref.setState({ enabled: true })
    goAway()
    vi.stubGlobal(
      'Notification',
      Object.assign(
        function Broken() {
          throw new TypeError('Illegal constructor')
        },
        { permission: 'granted' },
      ),
    )
    await finishOne()
    expect(toasts()).toHaveLength(1)
  })

  it('does not show one for a job another tab already announced', async () => {
    useDesktopPref.setState({ enabled: true })
    const { refresh, settle } = watch([job(1, 'running')])
    await settle()
    goAway()
    claimAlert(job(1, 'running').job_id)
    await refresh([job(1, 'succeeded')])
    expect(FakeNotification.instances).toEqual([])
  })
})

// --- The Settings card --------------------------------------------------------------------------

describe('Notifications card', () => {
  const desktop = () => within(screen.getByTestId('desktop-notifications'))

  it('says in-app pop-ups are always on, and offers to enable desktop ones', () => {
    FakeNotification.permission = 'default'
    render(<NotificationsCard />)
    expect(screen.getByText('Always on')).toBeTruthy()
    expect(desktop().getByRole('button', { name: 'Enable desktop notifications' })).toBeTruthy()
    expect(FakeNotification.requestPermission).not.toHaveBeenCalled() // never asks by itself
  })

  it('asks for permission only when the button is clicked, then turns on', async () => {
    FakeNotification.permission = 'default'
    FakeNotification.requestPermission.mockImplementationOnce(async () => {
      FakeNotification.permission = 'granted'
      return 'granted'
    })
    render(<NotificationsCard />)
    await userEvent.click(desktop().getByRole('button', { name: 'Enable desktop notifications' }))
    expect(FakeNotification.requestPermission).toHaveBeenCalledTimes(1)
    expect(await desktop().findByText('On')).toBeTruthy()
    expect(useDesktopPref.getState().enabled).toBe(true)
    expect(localStorage.getItem(DESKTOP_PREF_STORAGE_KEY)).toBe('on')
  })

  it('explains what to do when the browser blocks notifications', async () => {
    FakeNotification.permission = 'default'
    FakeNotification.requestPermission.mockImplementationOnce(async () => {
      FakeNotification.permission = 'denied'
      return 'denied'
    })
    render(<NotificationsCard />)
    await userEvent.click(desktop().getByRole('button', { name: 'Enable desktop notifications' }))
    expect(await desktop().findByText(/blocked for this site in your browser/)).toBeTruthy()
    expect(useDesktopPref.getState().enabled).toBe(false)
    expect(desktop().queryByRole('button', { name: 'Enable desktop notifications' })).toBeNull()
  })

  it('can be turned off and on again without asking the browser again', async () => {
    useDesktopPref.setState({ enabled: true })
    render(<NotificationsCard />)
    await userEvent.click(desktop().getByRole('button', { name: 'Turn off' }))
    expect(desktop().getByText('Off')).toBeTruthy()
    expect(localStorage.getItem(DESKTOP_PREF_STORAGE_KEY)).toBe('off')
    await userEvent.click(desktop().getByRole('button', { name: 'Turn on' }))
    expect(desktop().getByText('On')).toBeTruthy()
    expect(FakeNotification.requestPermission).not.toHaveBeenCalled()
  })

  it('sends a test: a pop-up and a desktop notification', async () => {
    useDesktopPref.setState({ enabled: true })
    render(<NotificationsCard />)
    await userEvent.click(desktop().getByRole('button', { name: 'Send a test' }))
    expect(toasts().map((t) => t.title)).toEqual(['Test notification'])
    expect(FakeNotification.instances.map((n) => n.title)).toEqual(['Test notification'])
  })

  it('says so when the browser has no notifications', () => {
    vi.stubGlobal('Notification', undefined)
    render(<NotificationsCard />)
    expect(screen.getByText('This browser can’t show desktop notifications.')).toBeTruthy()
  })

  it('says so on an address where browsers refuse them', () => {
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false })
    try {
      render(<NotificationsCard />)
      expect(screen.getByText(/only work on localhost or an HTTPS address/)).toBeTruthy()
    } finally {
      Reflect.deleteProperty(window, 'isSecureContext')
    }
  })
})

describe('toast action button', () => {
  it('runs the action once and closes the toast', async () => {
    const onClick = vi.fn()
    render(<Toaster />)
    act(() => {
      useToastStore.getState().show({ title: 'Architecture ready', action: { label: 'View results', onClick } })
    })
    await userEvent.click(await screen.findByRole('button', { name: 'View results' }))
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(toasts()).toEqual([])
  })
})
