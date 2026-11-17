import { CircleAlert } from 'lucide-react'
import { createContext, useContext, useId, type ReactNode } from 'react'

import { cn } from '@/utils/cn'

interface FieldContextValue {
  id: string
  describedBy?: string
  invalid: boolean
  required?: boolean
  disabled?: boolean
}

const FieldContext = createContext<FieldContextValue | null>(null)

interface FieldProps {
  label: ReactNode
  /** Helper text under the control; replaced by the error when there is one. */
  hint?: ReactNode
  error?: ReactNode
  required?: boolean
  disabled?: boolean
  /** Use when the control needs a known id; otherwise one is generated. */
  id?: string
  className?: string
  children: ReactNode
}

/** Label, helper text and error for one control (Input, Textarea, Select, SearchInput). */
export function Field({ label, hint, error, required, disabled, id, className, children }: FieldProps) {
  const generatedId = useId()
  const controlId = id ?? generatedId
  const messageId = `${controlId}-message`
  const message = error ?? hint

  return (
    <FieldContext.Provider
      value={{ id: controlId, describedBy: message ? messageId : undefined, invalid: Boolean(error), required, disabled }}
    >
      <div className={cn('flex flex-col gap-1.5', className)}>
        <label htmlFor={controlId} className={cn('text-label', disabled && 'text-muted-foreground')}>
          {label}
          {required && (
            <span className="text-danger" aria-hidden="true">
              {' '}
              *
            </span>
          )}
        </label>
        {children}
        {error ? <FieldError id={messageId}>{error}</FieldError> : hint ? <FieldHint id={messageId}>{hint}</FieldHint> : null}
      </div>
    </FieldContext.Provider>
  )
}

export function FieldHint({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="text-meta text-muted-foreground">
      {children}
    </p>
  )
}

export function FieldError({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="flex items-start gap-1.5 text-meta text-danger">
      <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
      {children}
    </p>
  )
}

interface ControlProps {
  id?: string
  disabled?: boolean
  required?: boolean
  'aria-describedby'?: string
  'aria-invalid'?: boolean | 'true' | 'false' | 'grammar' | 'spelling'
}

/** Merge a control's own props with those from an enclosing <Field>. */
export function useFieldControl<P extends ControlProps>(props: P): P {
  const field = useContext(FieldContext)
  const invalid = props['aria-invalid'] === true || props['aria-invalid'] === 'true' || Boolean(field?.invalid)
  const describedBy = [field?.describedBy, props['aria-describedby']].filter(Boolean).join(' ') || undefined
  return {
    ...props,
    id: props.id ?? field?.id,
    disabled: props.disabled ?? field?.disabled,
    required: props.required ?? field?.required,
    'aria-describedby': describedBy,
    'aria-invalid': invalid || undefined,
  }
}

/** Shared look of text-like controls. */
export const CONTROL_CLASSES = cn(
  'w-full rounded-md border border-border-strong bg-surface text-body text-foreground transition-colors',
  'placeholder:text-muted-foreground/70 hover:border-muted-foreground/40',
  'focus-visible:border-ring focus-visible:outline-offset-0',
  'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-muted-foreground disabled:hover:border-border-strong',
  'aria-[invalid=true]:border-danger aria-[invalid=true]:focus-visible:outline-danger',
)
