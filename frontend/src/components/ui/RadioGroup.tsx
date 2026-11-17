import { useId, useState, type ReactNode } from 'react'

import { cn } from '@/utils/cn'

import { FieldError, FieldHint } from './Field'

export interface RadioOption {
  value: string
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
}

interface RadioGroupProps {
  label: ReactNode
  options: RadioOption[]
  /** Controlled value; omit and use defaultValue for uncontrolled. */
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  name?: string
  hint?: ReactNode
  error?: ReactNode
  required?: boolean
  disabled?: boolean
  orientation?: 'vertical' | 'horizontal'
  className?: string
}

/** Native radio buttons in a fieldset (arrow keys move the selection). */
export function RadioGroup({
  label,
  options,
  value,
  defaultValue,
  onValueChange,
  name,
  hint,
  error,
  required,
  disabled,
  orientation = 'vertical',
  className,
}: RadioGroupProps) {
  const groupId = useId()
  const groupName = name ?? groupId
  const messageId = `${groupId}-message`
  const [uncontrolled, setUncontrolled] = useState(defaultValue)
  const selected = value ?? uncontrolled

  return (
    <fieldset
      role="radiogroup"
      disabled={disabled}
      aria-required={required || undefined}
      aria-invalid={error ? true : undefined}
      aria-describedby={error || hint ? messageId : undefined}
      className={cn('flex min-w-0 flex-col gap-2', className)}
    >
      <legend className={cn('mb-2 text-label', disabled && 'text-muted-foreground')}>
        {label}
        {required && (
          <span className="text-danger" aria-hidden="true">
            {' '}
            *
          </span>
        )}
      </legend>
      <div className={cn('flex gap-x-6 gap-y-2.5', orientation === 'vertical' ? 'flex-col' : 'flex-wrap')}>
        {options.map((option) => {
          const id = `${groupId}-${option.value}`
          const optionDisabled = disabled || option.disabled
          return (
            <div key={option.value} className="flex items-start gap-2.5">
              <input
                type="radio"
                id={id}
                name={groupName}
                value={option.value}
                checked={selected === option.value}
                disabled={option.disabled}
                aria-describedby={option.description ? `${id}-description` : undefined}
                data-invalid={error ? '' : undefined}
                onChange={() => {
                  setUncontrolled(option.value)
                  onValueChange?.(option.value)
                }}
                className={cn(
                  'mt-0.5 size-4 shrink-0 cursor-pointer appearance-none rounded-full border border-border-strong bg-surface transition-colors',
                  'hover:border-muted-foreground/60 data-invalid:border-danger checked:border-[5px] checked:border-primary',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              />
              <div className="min-w-0">
                <label
                  htmlFor={id}
                  className={cn('text-label', optionDisabled ? 'cursor-not-allowed text-muted-foreground' : 'cursor-pointer')}
                >
                  {option.label}
                </label>
                {option.description && (
                  <p id={`${id}-description`} className="text-meta text-muted-foreground">
                    {option.description}
                  </p>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {error ? <FieldError id={messageId}>{error}</FieldError> : hint ? <FieldHint id={messageId}>{hint}</FieldHint> : null}
    </fieldset>
  )
}
