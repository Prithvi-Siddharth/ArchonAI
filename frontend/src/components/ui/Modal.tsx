import { X } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

import { cn } from '@/utils/cn'

import { Button } from './Button'
import { Dialog } from './Dialog'

const SIZES = { sm: 'sm:max-w-sm', md: 'sm:max-w-lg', lg: 'sm:max-w-2xl' } as const

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  children?: ReactNode
  /** Action buttons, right-aligned (stacked on small screens). */
  footer?: ReactNode
  size?: keyof typeof SIZES
  role?: 'dialog' | 'alertdialog'
  /** Hide the X button (e.g. while an action is running). */
  hideCloseButton?: boolean
  closeOnBackdrop?: boolean
}

/** A titled, centered dialog with an optional scrollable body and footer actions. */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
  role = 'dialog',
  hideCloseButton = false,
  closeOnBackdrop,
}: ModalProps) {
  const titleId = useId()
  const descriptionId = useId()

  return (
    <Dialog
      open={open}
      onClose={onClose}
      closeOnBackdrop={closeOnBackdrop}
      role={role}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      className={cn('m-auto max-h-none w-[calc(100%-2rem)] max-w-none', SIZES[size])}
    >
      <div className="flex max-h-[calc(100dvh-2rem)] flex-col rounded-lg border border-border bg-surface-elevated shadow-overlay">
        <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-3">
          <div className="min-w-0">
            <h2 id={titleId} className="text-section-title">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="mt-1 text-muted-foreground">
                {description}
              </p>
            )}
          </div>
          {!hideCloseButton && (
            <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close" className="-mt-1 -mr-2">
              <X className="size-4" aria-hidden="true" />
            </Button>
          )}
        </div>
        {children && <div className="min-h-0 overflow-y-auto px-5 py-2">{children}</div>}
        {footer && (
          <div className="mt-2 flex flex-col-reverse gap-2 border-t border-border px-5 py-4 sm:flex-row sm:justify-end">
            {footer}
          </div>
        )}
      </div>
    </Dialog>
  )
}

interface ConfirmDialogProps {
  open: boolean
  onCancel: () => void
  /** May return a promise; the dialog shows a loading state until it settles. */
  onConfirm: () => void | Promise<void>
  title: string
  description: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** "destructive" for irreversible actions. */
  tone?: 'primary' | 'destructive'
}

/** Ask before an important action. Focus starts on Cancel, the safe choice. */
export function ConfirmDialog({
  open,
  onCancel,
  onConfirm,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'primary',
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false)

  const confirm = async () => {
    setBusy(true)
    try {
      await onConfirm()
    } finally {
      setBusy(false)
    }
  }
  // While the action runs, Escape and the backdrop can't dismiss it.
  const cancel = () => {
    if (!busy) onCancel()
  }

  return (
    <Modal
      open={open}
      onClose={cancel}
      title={title}
      description={description}
      size="sm"
      role="alertdialog"
      hideCloseButton
      footer={
        <>
          <Button variant="outline" onClick={cancel} disabled={busy} data-autofocus>
            {cancelLabel}
          </Button>
          <Button variant={tone} onClick={confirm} loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  )
}
