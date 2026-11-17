import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from 'react'

import { cn } from '@/utils/cn'

type Side = 'top' | 'right' | 'bottom' | 'left'

const GAP = 6
const VIEWPORT_MARGIN = 8

interface TooltipProps {
  content: ReactNode
  /** One focusable element (button, link, ...). */
  children: ReactElement<{ 'aria-describedby'?: string }>
  side?: Side
  /** Hover delay in ms; keyboard focus shows it immediately. */
  delay?: number
  disabled?: boolean
  /**
   * Link the tooltip as the trigger's description (aria-describedby). Turn off
   * when the tooltip only repeats the trigger's accessible name.
   */
  describeTrigger?: boolean
  /** Classes for the wrapper around the trigger (default inline-flex). */
  className?: string
}

/** Place the tooltip next to the trigger, flipping to the other side or clamping to stay on screen. */
function place(trigger: DOMRect, tip: HTMLElement, preferred: Side) {
  const { width, height } = tip.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  let side = preferred
  if (side === 'top' && trigger.top - height - GAP < VIEWPORT_MARGIN) side = 'bottom'
  else if (side === 'bottom' && trigger.bottom + height + GAP > vh - VIEWPORT_MARGIN) side = 'top'
  else if (side === 'left' && trigger.left - width - GAP < VIEWPORT_MARGIN) side = 'right'
  else if (side === 'right' && trigger.right + width + GAP > vw - VIEWPORT_MARGIN) side = 'left'

  const centerX = trigger.left + trigger.width / 2 - width / 2
  const centerY = trigger.top + trigger.height / 2 - height / 2
  const position = {
    top: { left: centerX, top: trigger.top - height - GAP },
    bottom: { left: centerX, top: trigger.bottom + GAP },
    left: { left: trigger.left - width - GAP, top: centerY },
    right: { left: trigger.right + GAP, top: centerY },
  }[side]

  const clamp = (value: number, max: number) => Math.min(Math.max(value, VIEWPORT_MARGIN), max - VIEWPORT_MARGIN)
  tip.style.left = `${clamp(position.left, vw - width)}px`
  tip.style.top = `${clamp(position.top, vh - height)}px`
}

/**
 * Short hint on hover or keyboard focus; Escape, scrolling or leaving hides it.
 * Rendered in the browser's top layer (Popover API), so it is never clipped by
 * scroll containers and shows above open dialogs.
 */
export function Tooltip({
  content,
  children,
  side = 'top',
  delay = 300,
  disabled = false,
  describeTrigger = true,
  className,
}: TooltipProps) {
  const id = useId()
  const wrapperRef = useRef<HTMLSpanElement>(null)
  const tipRef = useRef<HTMLSpanElement>(null)
  const timer = useRef<number | undefined>(undefined)
  const [open, setOpen] = useState(false)

  const show = (immediate: boolean) => {
    if (disabled) return
    window.clearTimeout(timer.current)
    if (immediate) setOpen(true)
    else timer.current = window.setTimeout(() => setOpen(true), delay)
  }
  const hide = () => {
    window.clearTimeout(timer.current)
    setOpen(false)
  }

  useLayoutEffect(() => {
    const tip = tipRef.current
    const wrapper = wrapperRef.current
    if (!tip || !wrapper || typeof tip.showPopover !== 'function') return
    if (!open) {
      if (tip.matches(':popover-open')) tip.hidePopover()
      return
    }
    if (!tip.matches(':popover-open')) tip.showPopover()
    place(wrapper.getBoundingClientRect(), tip, side)
  }, [open, side, content])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') hide()
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('scroll', hide, true)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('scroll', hide, true)
    }
  }, [open])

  useEffect(() => () => window.clearTimeout(timer.current), [])
  useEffect(() => {
    if (disabled) hide()
  }, [disabled])

  const trigger =
    isValidElement(children) && describeTrigger && !disabled
      ? cloneElement(children, {
          'aria-describedby': [children.props['aria-describedby'], id].filter(Boolean).join(' '),
        })
      : children

  return (
    <span
      ref={wrapperRef}
      className={cn('inline-flex', className)}
      onPointerEnter={(event) => event.pointerType === 'mouse' && show(false)}
      onPointerLeave={hide}
      onPointerDown={hide}
      onFocus={(event) => (event.target as HTMLElement).matches(':focus-visible') && show(true)}
      onBlur={hide}
    >
      {trigger}
      {!disabled && (
        <span
          ref={tipRef}
          id={id}
          role="tooltip"
          popover="manual"
          className={cn(
            'pointer-events-none fixed inset-auto m-0 max-w-xs overflow-visible rounded-md border-0 px-2 py-1',
            'bg-foreground text-meta font-medium text-background shadow-overlay',
          )}
        >
          {content}
        </span>
      )}
    </span>
  )
}
