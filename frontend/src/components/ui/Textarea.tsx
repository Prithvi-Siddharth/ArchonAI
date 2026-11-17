import { useState, type ComponentProps } from 'react'

import { cn } from '@/utils/cn'

import { CONTROL_CLASSES, useFieldControl } from './Field'

interface TextareaProps extends ComponentProps<'textarea'> {
  /** Show "used / maxLength" under the box (needs maxLength). */
  showCount?: boolean
}

/** Multi-line text input. Wrap in <Field> for a label, helper text and error. */
export function Textarea({ showCount = false, className, rows = 4, onChange, ...rest }: TextareaProps) {
  const props = useFieldControl(rest)
  const [uncontrolledLength, setUncontrolledLength] = useState(String(props.defaultValue ?? '').length)
  const length = props.value !== undefined ? String(props.value).length : uncontrolledLength
  const counted = showCount && props.maxLength !== undefined

  return (
    <div className="flex flex-col gap-1">
      <textarea
        rows={rows}
        className={cn(CONTROL_CLASSES, 'min-h-control-lg resize-y px-3 py-2', className)}
        onChange={(event) => {
          setUncontrolledLength(event.target.value.length)
          onChange?.(event)
        }}
        {...props}
      />
      {counted && (
        <p className="self-end text-meta text-muted-foreground tabular-nums">
          {length.toLocaleString('en')} / {props.maxLength?.toLocaleString('en')}
        </p>
      )}
    </div>
  )
}
