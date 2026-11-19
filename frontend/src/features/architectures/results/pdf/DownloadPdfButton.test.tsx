/** The Download PDF button: loading state, no duplicate exports, and a clear error. The generator is mocked here. */
import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Toaster } from '@/components/ui'
import { useToastStore } from '@/stores/toast.store'

import { DownloadPdfButton } from './DownloadPdfButton'
import { REAL_JOB, REAL_LIKE_RESULT } from './pdf-fixtures'

const generator = vi.hoisted(() => ({ downloadArchitecturePdf: vi.fn<(...args: unknown[]) => Promise<void>>() }))
vi.mock('./generate-pdf', () => generator)

function deferred() {
  let resolve!: () => void
  let reject!: (error: Error) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  generator.downloadArchitecturePdf.mockReset()
  useToastStore.setState({ toasts: [] })
})
afterEach(cleanup)

const button = () => screen.getByRole('button', { name: /PDF/ }) as HTMLButtonElement

describe('Download PDF button', () => {
  it('builds the PDF from the saved result and job, showing progress meanwhile', async () => {
    const run = deferred()
    generator.downloadArchitecturePdf.mockReturnValue(run.promise)
    render(<DownloadPdfButton result={REAL_LIKE_RESULT} job={REAL_JOB} />)
    expect(button().textContent).toBe('Download PDF')

    await userEvent.click(button())
    expect(generator.downloadArchitecturePdf).toHaveBeenCalledWith(REAL_LIKE_RESULT, REAL_JOB)
    expect(button().textContent).toContain('Creating PDF…')
    expect(button().disabled).toBe(true)
    expect(button().getAttribute('aria-busy')).toBe('true')

    await act(async () => run.resolve())
    expect(button().textContent).toBe('Download PDF')
    expect(button().disabled).toBe(false)
  })

  it('ignores more clicks while a PDF is being built', async () => {
    const run = deferred()
    generator.downloadArchitecturePdf.mockReturnValue(run.promise)
    render(<DownloadPdfButton result={REAL_LIKE_RESULT} job={REAL_JOB} />)
    const target = button()
    await userEvent.click(target)
    // A click that slips through before the button disables still does nothing.
    target.disabled = false
    await userEvent.click(target)
    await userEvent.click(target)
    expect(generator.downloadArchitecturePdf).toHaveBeenCalledTimes(1)
    await act(async () => run.resolve())
    await userEvent.click(button())
    expect(generator.downloadArchitecturePdf).toHaveBeenCalledTimes(2)
  })

  it('explains a failure and lets you try again', async () => {
    generator.downloadArchitecturePdf.mockRejectedValueOnce(new Error('font missing'))
    render(
      <>
        <DownloadPdfButton result={REAL_LIKE_RESULT} job={REAL_JOB} />
        <Toaster />
      </>,
    )
    await userEvent.click(button())
    expect(await screen.findByText("Couldn't create the PDF")).toBeTruthy()
    expect(useToastStore.getState().toasts[0].tone).toBe('danger')
    expect(screen.queryByText('font missing')).toBeNull() // no internal error text
    expect(button().disabled).toBe(false)
  })
})
