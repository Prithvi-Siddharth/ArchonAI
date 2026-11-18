import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useSubmissionsStore } from '@/stores/submissions.store'

import { ArchitectureRequestForm } from './ArchitectureRequestForm'

const EXAMPLES = [{ label: 'E-commerce platform', prompt: 'Design an e-commerce platform for 500,000 concurrent users.' }]

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** Stub the API: GET /examples answers with EXAMPLES; POST /jobs answers with `submitReply`. */
function stubApi(submitReply: () => Response) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/v1/architectures/examples')) return json(200, EXAMPLES)
    if (url.endsWith('/api/v1/architectures/jobs') && init?.method === 'POST') return submitReply()
    throw new Error(`unexpected request ${init?.method} ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  const posts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
  return { posts }
}

function renderForm() {
  const onSubmitted = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ArchitectureRequestForm onSubmitted={onSubmitted} />
    </QueryClientProvider>,
  )
  return { onSubmitted, user: userEvent.setup(), textbox: screen.getByLabelText(/describe the system to design/i) }
}

const submitButton = () => screen.getByRole('button', { name: 'Generate architecture' })

afterEach(() => {
  cleanup()
  useSubmissionsStore.getState().clear()
})

describe('ArchitectureRequestForm', () => {
  it('blocks a too-short request and explains why, without calling the API', async () => {
    const { posts } = stubApi(() => json(202, {}))
    const { user, textbox } = renderForm()

    await user.type(textbox, 'short')
    await user.click(submitButton())

    expect(screen.getByText('Add a little more detail: at least 10 characters (currently 5).')).toBeTruthy()
    expect(textbox.getAttribute('aria-invalid')).toBe('true')
    expect(posts()).toHaveLength(0)
  })

  it('sends the trimmed request, reports the new job and saves it for the dashboard', async () => {
    const job = { job_id: 'job-123', status: 'queued', status_url: '/api/v1/architectures/jobs/job-123' }
    const { posts } = stubApi(() => json(202, job))
    const { user, textbox, onSubmitted } = renderForm()

    await user.type(textbox, '   Design a blog for 10,000 readers.   ')
    await user.click(submitButton())

    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1))
    expect(posts()).toHaveLength(1)
    expect(posts()[0][1]?.body).toBe('{"user_request":"Design a blog for 10,000 readers."}')
    expect(onSubmitted.mock.calls[0][0]).toMatchObject({ job, request: 'Design a blog for 10,000 readers.' })
    expect(useSubmissionsStore.getState().submissions[0]).toMatchObject({
      jobId: 'job-123',
      requestPreview: 'Design a blog for 10,000 readers.',
    })
  })

  it("shows the API's validation message on the field", async () => {
    stubApi(() =>
      json(422, { detail: [{ type: 'string_too_short', loc: ['body', 'user_request'], msg: 'String should have at least 10 characters' }] }),
    )
    const { user, textbox } = renderForm()

    await user.type(textbox, 'Design a blog for 10,000 readers.')
    await user.click(submitButton())

    expect(await screen.findByText('String should have at least 10 characters')).toBeTruthy()
    expect(textbox.getAttribute('aria-invalid')).toBe('true')
  })

  it('keeps the text and shows the backend message when the job queue is down', async () => {
    stubApi(() => json(503, { detail: 'Job queue is unavailable. Please retry later.' }))
    const { user, textbox, onSubmitted } = renderForm()

    await user.type(textbox, 'Design a blog for 10,000 readers.')
    await user.click(submitButton())

    expect((await screen.findByRole('alert')).textContent).toBe('Job queue is unavailable. Please retry later.')
    expect((textbox as HTMLTextAreaElement).value).toBe('Design a blog for 10,000 readers.')
    expect(onSubmitted).not.toHaveBeenCalled()
  })

  it('fills an empty box from an example', async () => {
    stubApi(() => json(202, {}))
    const { user, textbox } = renderForm()

    await user.click(await screen.findByRole('button', { name: 'E-commerce platform' }))

    expect((textbox as HTMLTextAreaElement).value).toBe(EXAMPLES[0].prompt)
  })
})
