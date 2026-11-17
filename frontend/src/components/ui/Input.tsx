import type { LucideIcon } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'

import { cn } from '@/utils/cn'

import { CONTROL_CLASSES, useFieldControl } from './Field'

export interface InputProps extends ComponentProps<'input'> {
  /** Icon inside the left edge (e.g. a search glass). */
  leadingIcon?: LucideIcon
  /** Element inside the right edge (e.g. a clear button). */
  trailing?: ReactNode
}

/** Single-line text input. Wrap in <Field> for a label, helper text and error. */
export function Input({ leadingIcon: Icon, trailing, className, type = 'text', ...rest }: InputProps) {
  const props = useFieldControl(rest)
  const input = (
    <input
      type={type}
      className={cn(CONTROL_CLASSES, 'h-control-md', Icon ? 'pl-9' : 'pl-3', trailing != null ? 'pr-9' : 'pr-3', className)}
      {...props}
    />
  )
  if (!Icon && trailing == null) return input

  return (
    <div className="relative">
      {Icon && (
        <Icon
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
      )}
      {input}
      {trailing != null && <div className="absolute inset-y-0 right-1 flex items-center">{trailing}</div>}
    </div>
  )
}
