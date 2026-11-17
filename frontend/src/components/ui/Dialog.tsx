import { useEffect, useRef, type ComponentProps } from 'react'

import { cn } from '@/utils/cn'

export interface DialogProps extends Omit<ComponentProps<'dialog'>, 'open' | 'onClose' | 'onCancel'> {
  open: boolean
  onClose: () => void
  /** Close when the backdrop is clicked (default true). */
  closeOnBackdrop?: boolean
}

/**
 * Modal base on the native <dialog> element, which supplies the accessibility
 * behavior: focus moves into the dialog and is kept there, the page behind is
 * inert, Escape requests close, and focus returns to the trigger on close.
 * Mark the element to focus first with `data-autofocus`. Children mount only
 * while open, so their state resets each time.
 */
export function Dialog({ open, onClose, closeOnBackdrop = true, className, children, ...props }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const pressedOnBackdrop = useRef(false)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  return (
    <dialog
      ref={ref}
      className={cn('bg-transparent p-0 text-foreground', className)}
      onCancel={(event) => {
        // Escape: let the parent decide, so `open` stays the single source of truth.
        event.preventDefault()
        onClose()
      }}
      onClose={() => {
        if (open) onClose()
      }}
      onPointerDown={(event) => {
        pressedOnBackdrop.current = event.target === event.currentTarget
      }}
      onClick={(event) => {
        // Only a press that started and ended on the backdrop (not a text selection drag).
        if (closeOnBackdrop && pressedOnBackdrop.current && event.target === event.currentTarget) onClose()
      }}
      {...props}
    >
      {open && children}
    </dialog>
  )
}
