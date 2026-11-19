import { CircleAlert, CircleCheck, Info, TriangleAlert, X, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useToastStore, type ToastItem, type ToastTone } from '@/stores/toast.store'
import { cn } from '@/utils/cn'

import { TONE_TEXT } from './tones'

const ICONS: Record<ToastTone, LucideIcon> = {
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  danger: CircleAlert,
}

function ToastView({ item }: { item: ToastItem }) {
  const dismiss = useToastStore((state) => state.dismiss)
  const [paused, setPaused] = useState(false)
  const Icon = ICONS[item.tone]

  // Auto-dismiss, paused while hovered or focused so it can be read and acted on.
  useEffect(() => {
    if (paused || item.duration <= 0) return
    const timer = window.setTimeout(() => dismiss(item.id), item.duration)
    return () => window.clearTimeout(timer)
  }, [paused, item.id, item.duration, dismiss])

  return (
    <li
      role={item.tone === 'danger' ? 'alert' : undefined}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className="pointer-events-auto flex w-full items-start gap-3 rounded-lg border border-border bg-surface-elevated p-4 shadow-overlay"
    >
      <Icon className={cn('mt-0.5 size-4 shrink-0', TONE_TEXT[item.tone])} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-label">{item.title}</p>
        {item.description && <p className="mt-0.5 text-meta text-muted-foreground">{item.description}</p>}
        {item.action && (
          <button
            type="button"
            onClick={() => {
              item.action?.onClick()
              dismiss(item.id)
            }}
            className="mt-2 rounded-sm text-meta font-medium text-primary hover:underline"
          >
            {item.action.label}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={() => dismiss(item.id)}
        aria-label="Dismiss notification"
        className="-mt-1 -mr-1 flex size-6 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-surface-muted hover:text-foreground"
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
    </li>
  )
}

/** Renders queued toasts; mounted once in AppProviders. Show one with `toast()` from stores/toast.store. */
export function Toaster() {
  const toasts = useToastStore((state) => state.toasts)
  return (
    <section aria-label="Notifications" className="pointer-events-none fixed inset-x-4 bottom-4 z-50 sm:inset-x-auto sm:right-4 sm:w-96">
      {/* Always mounted, so screen readers announce toasts added to it. */}
      <ol aria-live="polite" className="flex flex-col gap-2">
        {toasts.map((item) => (
          <ToastView key={item.id} item={item} />
        ))}
      </ol>
    </section>
  )
}
