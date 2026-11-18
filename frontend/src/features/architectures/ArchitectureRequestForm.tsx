import { CircleAlert } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import { ApiError } from '@/api/client'
import { Button, Card, CardContent, CardFooter, ConfirmDialog, Field, Textarea } from '@/components/ui'
import { TONE_SOFT } from '@/components/ui/tones'
import type { ExamplePrompt, JobSubmittedResponse } from '@/types/api'
import { cn } from '@/utils/cn'

import { ExamplePrompts } from './ExamplePrompts'
import { REQUEST_MAX_LENGTH, requestLength, validateRequest } from './request-validation'
import { useSubmitArchitectureJob } from './useArchitectureApi'

export interface SubmittedJob {
  job: JobSubmittedResponse
  /** The text that was sent (trimmed). */
  request: string
  /** ISO time the API accepted the job. */
  submittedAt: string
}

const PLACEHOLDER =
  'e.g. Design a video streaming platform for 2 million daily users with 4K playback, ' +
  'global delivery, 99.95% availability and a budget of about $20,000 a month.'

const GENERIC_ERROR = 'Something went wrong while submitting. Please try again.'

interface ArchitectureRequestFormProps {
  onSubmitted: (submitted: SubmittedJob) => void
  /** Focus the text box on mount (used when returning from the success panel). */
  autoFocus?: boolean
}

/** The design-request form: client-side checks that match the backend, then POST /jobs. */
export function ArchitectureRequestForm({ onSubmitted, autoFocus = false }: ArchitectureRequestFormProps) {
  const [text, setText] = useState('')
  const [submitAttempted, setSubmitAttempted] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const counterId = useId()
  const submit = useSubmitArchitectureJob()

  const length = requestLength(text)
  const tooLong = length > REQUEST_MAX_LENGTH
  const clientError = submitAttempted || tooLong ? validateRequest(text) : undefined

  // The API's 422 message for this field (only if the local checks passed but the server disagreed).
  const apiError = submit.error
  const serverFieldError =
    apiError instanceof ApiError && apiError.kind === 'validation' ? apiError.fieldErrors.user_request : undefined
  const formError =
    apiError && !serverFieldError ? (apiError instanceof ApiError ? apiError.message : GENERIC_ERROR) : undefined

  const handleChange = (value: string) => {
    setText(value)
    if (submit.isError) submit.reset() // a new edit replaces the last server error
  }

  // Examples: fill an empty box directly; ask before replacing text the user wrote.
  const [pendingExample, setPendingExample] = useState<ExamplePrompt | null>(null)
  const [focusRequest, setFocusRequest] = useState(0)

  const fillWithExample = (prompt: string) => {
    handleChange(prompt)
    setFocusRequest((count) => count + 1)
  }

  const handleExample = (example: ExamplePrompt) => {
    if (text.trim() === '' || text === example.prompt) fillWithExample(example.prompt)
    else setPendingExample(example)
  }

  // After filling, put the cursor at the end of the text. Runs after the confirm
  // dialog's own effect has closed it and returned focus to the example button.
  useEffect(() => {
    const textarea = textareaRef.current
    if (focusRequest === 0 || !textarea) return
    textarea.focus()
    textarea.setSelectionRange(textarea.value.length, textarea.value.length)
  }, [focusRequest])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submit.isPending) return
    setSubmitAttempted(true)
    if (validateRequest(text)) {
      textareaRef.current?.focus()
      return
    }
    const request = text.trim()
    submit.mutate(request, {
      onSuccess: (job) => onSubmitted({ job, request, submittedAt: new Date().toISOString() }),
    })
  }

  // Ctrl+Enter (Cmd+Enter on macOS) submits from the text box.
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <>
      <Card>
        <form onSubmit={handleSubmit} noValidate aria-label="New architecture request">
          <CardContent className="space-y-5 py-5">
            <ExamplePrompts onSelect={handleExample} disabled={submit.isPending} />

            <Field
              label="Describe the system to design"
              required
              hint="Plain English is fine. Specific numbers (users, traffic, uptime, budget) lead to better designs."
              error={clientError ?? serverFieldError}
            >
              <Textarea
                ref={textareaRef}
                autoFocus={autoFocus}
                rows={9}
                value={text}
                onChange={(event) => handleChange(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={PLACEHOLDER}
                aria-describedby={counterId}
                disabled={submit.isPending}
              />
              <div className="flex items-center justify-between gap-3 text-meta text-muted-foreground">
                <span className="hidden sm:inline">Ctrl or ⌘ + Enter to submit</span>
                <span id={counterId} className={cn('ml-auto tabular-nums', tooLong && 'font-medium text-danger')}>
                  {length.toLocaleString('en')} / {REQUEST_MAX_LENGTH.toLocaleString('en')} characters
                </span>
              </div>
            </Field>

            {formError && (
              <div role="alert" className={cn('flex items-start gap-2.5 rounded-md border px-3 py-2.5', TONE_SOFT.danger)}>
                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <p>{formError}</p>
              </div>
            )}
          </CardContent>
          <CardFooter>
            <Button type="submit" loading={submit.isPending}>
              {submit.isPending ? 'Submitting…' : 'Generate architecture'}
            </Button>
          </CardFooter>
        </form>
      </Card>

      <ConfirmDialog
        open={pendingExample !== null}
        title="Replace your description?"
        description={pendingExample ? `Your current text will be replaced by the “${pendingExample.label}” example.` : ''}
        confirmLabel="Replace"
        tone="destructive"
        onCancel={() => setPendingExample(null)}
        onConfirm={() => {
          if (pendingExample) fillWithExample(pendingExample.prompt)
          setPendingExample(null)
        }}
      />
    </>
  )
}
