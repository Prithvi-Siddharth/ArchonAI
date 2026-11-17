import { Check } from 'lucide-react'
import { useId, type ComponentProps, type ReactNode } from 'react'

import { cn } from '@/utils/cn'

import { FieldError } from './Field'

interface CheckboxProps extends Omit<ComponentProps<'input'>, 'type'> {
  label: ReactNode
  description?: ReactNode
  error?: ReactNode
}

/** Native checkbox (Space toggles) with a custom box, label, description and error. */
export function Checkbox({ label, description, error, id, className, disabled, ...props }: CheckboxProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const descriptionId = description ? `${inputId}-description` : undefined
  const errorId = error ? `${inputId}-error` : undefined

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <div className="flex items-start gap-2.5">
        <span className="relative mt-0.5 flex size-4 shrink-0">
          <input
            type="checkbox"
            id={inputId}
            disabled={disabled}
            aria-describedby={[descriptionId, errorId].filter(Boolean).join(' ') || undefined}
            aria-invalid={error ? true : undefined}
            className={cn(
              'peer size-4 cursor-pointer appearance-none rounded-sm border border-border-strong bg-surface transition-colors',
              'checked:border-primary checked:bg-primary hover:border-muted-foreground/60',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'aria-[invalid=true]:border-danger',
            )}
            {...props}
          />
          <Check
            className="pointer-events-none absolute inset-0 size-4 p-[2px] text-primary-foreground opacity-0 peer-checked:opacity-100"
            strokeWidth={3}
            aria-hidden="true"
          />
        </span>
        <div className="min-w-0">
          <label
            htmlFor={inputId}
            className={cn('text-label', disabled ? 'cursor-not-allowed text-muted-foreground' : 'cursor-pointer')}
          >
            {label}
          </label>
          {description && (
            <p id={descriptionId} className="text-meta text-muted-foreground">
              {description}
            </p>
          )}
        </div>
      </div>
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </div>
  )
}
