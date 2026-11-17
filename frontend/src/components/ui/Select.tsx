import { ChevronDown } from 'lucide-react'
import type { ComponentProps } from 'react'

import { cn } from '@/utils/cn'

import { CONTROL_CLASSES, useFieldControl } from './Field'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

interface SelectProps extends Omit<ComponentProps<'select'>, 'children'> {
  options: SelectOption[]
  /** Shown while nothing is selected (value ""). */
  placeholder?: string
}

/** Native select (full keyboard and screen-reader support), styled to match the inputs. */
export function Select({ options, placeholder, className, ...rest }: SelectProps) {
  const props = useFieldControl(rest)
  // Uncontrolled with no starting value: browsers auto-select the first enabled
  // option, so start on the placeholder instead. Controlled use is unaffected.
  const startOnPlaceholder = placeholder !== undefined && props.value === undefined && props.defaultValue === undefined
  return (
    <div className="relative">
      <select
        className={cn(CONTROL_CLASSES, 'h-control-md cursor-pointer appearance-none pr-9 pl-3', className)}
        {...props}
        {...(startOnPlaceholder ? { defaultValue: '' } : {})}
      >
        {placeholder !== undefined && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
    </div>
  )
}
