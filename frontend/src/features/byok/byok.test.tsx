/**
 * The Bring Your Own Key page, against a fake settings API.
 * fetch is stubbed in every test: nothing reaches a real backend, and the keys are fakes.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { useToastStore } from '@/stores/toast.store'
import type { LLMSettings, LLMSettingsUpdate } from '@/types/api'

import { validateApiKey, validateModel } from './llm-validation'
import { ByokPage } from './ByokPage'

const KEY = 'gsk_TESTKEY1234567890abcdef'
const PROVIDERS = [
  { id: 'groq', label: 'Groq', default_model: 'groq-default-model', key_url: 'https://console.groq.com/keys' },
  { id: 'gemini', label: 'Google Gemini', default_model: 'gemini-default-model', key_url: 'https://aistudio.google.com/apikey' },
]
const EMPTY: LLMSettings = { configured: false, provider: null, model: null, key_hint: null, updated_at: null, encryption_available: true, providers: PROVIDERS }
const SAVED: LLMSettings = { ...EMPTY, configured: true, provider: 'groq', model: null, key_hint: 'cdef', updated_at: '2026-11-19T10:00:00Z' }

type Reply = { status: number; body?: unknown } | 'network-error'

/** A tiny fake of GET/PUT/DELETE /settings/llm that remembers what was saved. */
function fakeApi(initial: LLMSettings = EMPTY, overrides: { put?: (body: LLMSettingsUpdate) => Reply } = {}) {
  const state = { settings: initial, puts: [] as LLMSettingsUpdate[], deletes: 0, calls: [] as string[] }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      state.calls.push(`${method} ${path}`)
      if (path !== '/api/v1/settings/llm') throw new Error(`unexpected request ${method} ${path}`)
      let reply: Reply
      if (method === 'GET') reply = { status: 200, body: state.settings }
      else if (method === 'PUT') {
        const body = JSON.parse(String(init?.body)) as LLMSettingsUpdate
        state.puts.push(body)
        reply =
          overrides.put?.(body) ??
          (() => {
            state.settings = {
              ...state.settings,
              configured: true,
              provider: body.provider,
              model: body.model ?? null,
              key_hint: body.api_key ? body.api_key.slice(-4) : state.settings.key_hint,
              updated_at: new Date().toISOString(),
            }
            return { status: 200, body: state.settings }
          })()
      } else {
        state.deletes += 1
        state.settings = { ...EMPTY, providers: PROVIDERS }
        reply = { status: 204 }
      }
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
      <ByokPage />
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

const keyBox = () => screen.getByLabelText('API key') as HTMLInputElement
const modelBox = () => screen.getByLabelText('Model (optional)') as HTMLInputElement
const providerBox = () => screen.getByLabelText('Provider') as HTMLSelectElement

// jsdom has no modal <dialog>: open and close it by toggling the `open` attribute, as browsers do.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
})

afterEach(() => {
  cleanup()
  useToastStore.setState({ toasts: [] })
  vi.unstubAllGlobals()
})

describe('validation', () => {
  it('requires a key only when one is needed, and checks its shape', () => {
    expect(validateApiKey('', true, 'Groq')).toBe('Enter your Groq API key.')
    expect(validateApiKey('   ', false, 'Groq')).toBeUndefined()
    expect(validateApiKey('short', true, 'Groq')).toMatch(/8 to 512/)
    expect(validateApiKey('x'.repeat(513), true, 'Groq')).toMatch(/8 to 512/)
    expect(validateApiKey('has space inside1', true, 'Groq')).toMatch(/spaces/)
    expect(validateApiKey(`  ${KEY}  `, true, 'Groq')).toBeUndefined()
  })

  it('checks the model name', () => {
    expect(validateModel('')).toBeUndefined()
    expect(validateModel('llama-3.3-70b:free')).toBeUndefined()
    expect(validateModel('models/gemini-2.0')).toBeUndefined()
    expect(validateModel('bad model')).toMatch(/letters, digits/)
    expect(validateModel('m'.repeat(101))).toMatch(/up to 100/)
  })
})

describe('Bring Your Own Key page', () => {
  it('starts on the server default, with the providers offered', async () => {
    fakeApi()
    renderPage()
    expect(await screen.findByText('Server default')).toBeTruthy()
    expect(within(providerBox()).getAllByRole('option').map((o) => o.textContent)).toEqual(['Groq', 'Google Gemini'])
    expect(keyBox().type).toBe('password')
    expect(modelBox().placeholder).toBe('groq-default-model')
    expect(screen.queryByRole('button', { name: 'Remove key' })).toBeNull()
    expect(screen.getByRole('link', { name: /Get a key/ }).getAttribute('href')).toBe('https://console.groq.com/keys')
  })

  it('saves a key, sends it once, empties the box and shows only the last four characters', async () => {
    const api = fakeApi()
    const user = renderPage()
    await screen.findByText('Server default')

    await user.type(keyBox(), `  ${KEY}  `)
    await user.type(modelBox(), 'my-model')
    await user.click(screen.getByRole('button', { name: 'Save key' }))

    expect(await screen.findByText('Using your own key')).toBeTruthy()
    expect(api.puts).toEqual([{ provider: 'groq', api_key: KEY, model: 'my-model' }])
    expect(keyBox().value).toBe('')
    const status = screen.getByTestId('llm-status').textContent ?? ''
    expect(status).toContain('key ending …cdef')
    expect(status).toContain('Model: my-model')
    expect(document.body.textContent).not.toContain(KEY)
    expect(useToastStore.getState().toasts.map((t) => t.title)).toEqual(['API key saved'])
    expect(screen.getByRole('button', { name: 'Remove key' })).toBeTruthy()
  })

  it('never keeps the key in browser storage', async () => {
    fakeApi()
    const user = renderPage()
    await screen.findByText('Server default')
    await user.type(keyBox(), KEY)
    await user.click(screen.getByRole('button', { name: 'Save key' }))
    await screen.findByText('Using your own key')
    expect(JSON.stringify({ ...localStorage })).not.toContain(KEY)
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(KEY)
  })

  it('can show and hide what was typed', async () => {
    fakeApi()
    const user = renderPage()
    await screen.findByText('Server default')
    await user.type(keyBox(), KEY)
    await user.click(screen.getByRole('button', { name: 'Show password' }))
    expect(keyBox().type).toBe('text')
    await user.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(keyBox().type).toBe('password')
  })

  it('checks the fields before sending anything', async () => {
    const api = fakeApi()
    const user = renderPage()
    await screen.findByText('Server default')

    await user.click(screen.getByRole('button', { name: 'Save key' }))
    expect(screen.getByText('Enter your Groq API key.')).toBeTruthy()
    expect(keyBox().getAttribute('aria-invalid')).toBe('true')

    await user.type(keyBox(), 'short')
    await user.type(modelBox(), 'bad model!')
    await user.click(screen.getByRole('button', { name: 'Save key' }))
    expect(screen.getByText(/The API key must be 8 to 512/)).toBeTruthy()
    expect(screen.getByText(/The model name can only use/)).toBeTruthy()
    expect(api.puts).toEqual([])
  })

  it('a saved key is kept when the box is left empty and only the model changes', async () => {
    const api = fakeApi(SAVED)
    const user = renderPage()
    expect(await screen.findByText('Using your own key')).toBeTruthy()
    expect(screen.getByText(/Leave empty to keep the saved key/)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Save changes' }) as HTMLButtonElement).disabled).toBe(true)

    await user.type(modelBox(), 'new-model')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(api.puts).toEqual([{ provider: 'groq', model: 'new-model' }]))
    expect(api.puts[0]).not.toHaveProperty('api_key')
    expect(await screen.findByText(/Model: new-model/)).toBeTruthy()
  })

  it('switching provider needs a new key and clears the model', async () => {
    const api = fakeApi({ ...SAVED, model: 'old-model' })
    const user = renderPage()
    await screen.findByText('Using your own key')
    expect(modelBox().value).toBe('old-model')

    await user.selectOptions(providerBox(), 'gemini')
    expect(modelBox().value).toBe('')
    expect(modelBox().placeholder).toBe('gemini-default-model')
    expect(screen.getByRole('link', { name: /Get a key/ }).getAttribute('href')).toBe('https://aistudio.google.com/apikey')

    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(screen.getByText('Enter your Google Gemini API key.')).toBeTruthy()
    expect(api.puts).toEqual([])

    await user.type(keyBox(), 'AIzaSyFAKEKEY0987654321zyxwvu')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(api.puts).toEqual([{ provider: 'gemini', api_key: 'AIzaSyFAKEKEY0987654321zyxwvu', model: null }]))
  })

  it('asks before removing the key, and Cancel keeps it', async () => {
    const api = fakeApi(SAVED)
    const user = renderPage()
    await user.click(await screen.findByRole('button', { name: 'Remove key' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText('Remove your API key?')).toBeTruthy()
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(api.deletes).toBe(0)
    expect(screen.getByText('Using your own key')).toBeTruthy()
  })

  it('removes the key and returns to the server default', async () => {
    const api = fakeApi(SAVED)
    const user = renderPage()
    await user.click(await screen.findByRole('button', { name: 'Remove key' }))
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Remove key' }))

    expect(await screen.findByText('Server default')).toBeTruthy()
    expect(api.deletes).toBe(1)
    expect(screen.queryByRole('button', { name: 'Remove key' })).toBeNull()
    expect(useToastStore.getState().toasts.map((t) => t.title)).toEqual(['API key removed'])
  })

  it('shows a server error in the form and keeps what was typed', async () => {
    fakeApi(EMPTY, { put: () => ({ status: 503, body: { detail: 'Saving API keys is not configured on the server.' } }) })
    const user = renderPage()
    await screen.findByText('Server default')
    await user.type(keyBox(), KEY)
    await user.click(screen.getByRole('button', { name: 'Save key' }))
    expect((await screen.findByRole('alert', {}, { timeout: 4000 })).textContent).toBe('Saving API keys is not configured on the server.')
    expect(keyBox().value).toBe(KEY)
  })

  it('shows a field message from a 422', async () => {
    fakeApi(EMPTY, { put: () => ({ status: 422, body: { detail: [{ type: 'value_error', loc: ['body', 'api_key'], msg: 'The API key must be 8 to 512 characters.' }] } }) })
    const user = renderPage()
    await screen.findByText('Server default')
    await user.type(keyBox(), KEY)
    await user.click(screen.getByRole('button', { name: 'Save key' }))
    expect(await screen.findByText('The API key must be 8 to 512 characters.')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('locks the form when the server cannot encrypt keys', async () => {
    fakeApi({ ...EMPTY, encryption_available: false })
    renderPage()
    expect(await screen.findByText(/isn’t available on this server yet/)).toBeTruthy()
    expect(keyBox().disabled).toBe(true)
    expect(providerBox().disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Save key' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows an error with retry when the settings cannot be loaded', async () => {
    const api = fakeApi()
    api.settings = EMPTY
    let failing = true
    const real = globalThis.fetch
    vi.stubGlobal('fetch', vi.fn(async (...args: Parameters<typeof fetch>) => (failing ? new Response(JSON.stringify({ detail: 'Settings store is unavailable. Please retry later.' }), { status: 503 }) : real(...args))))
    const user = renderPage()
    expect(await screen.findByText("Couldn't load your AI provider settings", {}, { timeout: 4000 })).toBeTruthy()
    failing = false
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Server default')).toBeTruthy()
  })
})
