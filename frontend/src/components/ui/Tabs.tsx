import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react'

import { cn } from '@/utils/cn'

export interface TabItem {
  id: string
  label: string
}

interface TabsProps {
  /** Accessible name of the tab list, e.g. "Result sections". */
  label: string
  items: readonly TabItem[]
  /** id of the selected tab. */
  value: string
  onValueChange: (id: string) => void
  /** Content of the selected tab (only the selected panel is rendered). */
  children: ReactNode
  className?: string
}

/**
 * Accessible tabs (WAI-ARIA tabs pattern): one tab stop for the list, arrow
 * keys / Home / End move between tabs and select them, the panel follows in
 * the tab order. The list scrolls sideways on narrow screens.
 */
export function Tabs({ label, items, value, onValueChange, children, className }: TabsProps) {
  const baseId = useId()
  const listRef = useRef<HTMLDivElement>(null)
  const tabRefs = useRef(new Map<string, HTMLButtonElement>())
  const tabId = (id: string) => `${baseId}-tab-${id}`
  const panelId = (id: string) => `${baseId}-panel-${id}`

  // Keep the selected tab visible inside the scrolling list (without scrolling the page).
  useEffect(() => {
    const list = listRef.current
    const tab = tabRefs.current.get(value)
    if (!list || !tab) return
    if (tab.offsetLeft < list.scrollLeft || tab.offsetLeft + tab.offsetWidth > list.scrollLeft + list.clientWidth) {
      list.scrollLeft = Math.max(0, tab.offsetLeft - 16)
    }
  }, [value])

  const selectAt = (index: number) => {
    const item = items[(index + items.length) % items.length]
    onValueChange(item.id)
    tabRefs.current.get(item.id)?.focus()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = items.findIndex((item) => item.id === value)
    const target: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: items.length - 1,
    }
    if (event.key in target) {
      event.preventDefault()
      selectAt(target[event.key])
    }
  }

  return (
    <div className={className}>
      <div
        ref={listRef}
        role="tablist"
        aria-label={label}
        onKeyDown={handleKeyDown}
        className="relative flex overflow-x-auto border-b border-border [scrollbar-width:thin]"
      >
        {items.map((item) => {
          const selected = item.id === value
          return (
            <button
              key={item.id}
              ref={(element) => {
                if (element) tabRefs.current.set(item.id, element)
                else tabRefs.current.delete(item.id)
              }}
              type="button"
              role="tab"
              id={tabId(item.id)}
              aria-selected={selected}
              aria-controls={selected ? panelId(item.id) : undefined}
              tabIndex={selected ? 0 : -1}
              onClick={() => onValueChange(item.id)}
              className={cn(
                '-mb-px shrink-0 border-b-2 px-3 py-2.5 text-label whitespace-nowrap transition-colors',
                'focus-visible:outline-offset-[-2px]',
                selected
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:border-border-strong hover:text-foreground',
              )}
            >
              {item.label}
            </button>
          )
        })}
      </div>
      <div
        role="tabpanel"
        id={panelId(value)}
        aria-labelledby={tabId(value)}
        tabIndex={0}
        className="pt-6 focus-visible:outline-offset-4"
      >
        {children}
      </div>
    </div>
  )
}
