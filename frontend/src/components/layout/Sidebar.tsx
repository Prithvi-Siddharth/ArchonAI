import { Layers, X } from 'lucide-react'
import { useEffect } from 'react'
import { NavLink } from 'react-router'

import { Button } from '@/components/ui/Button'
import { useUIStore } from '@/stores/ui.store'
import { cn } from '@/utils/cn'

import { NAV_SECTIONS } from './navigation'

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex size-8 items-center justify-center rounded-md bg-foreground text-background">
        <Layers className="size-4" aria-hidden="true" />
      </span>
      <div className="leading-tight">
        <p className="text-sm font-semibold">ArchonAI</p>
        <p className="text-xs text-muted-foreground">AWS architecture design</p>
      </div>
    </div>
  )
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
      {NAV_SECTIONS.map((section) => (
        <div key={section.title}>
          <p className="px-3 pb-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
            {section.title}
          </p>
          <ul className="space-y-0.5">
            {section.items.map(({ label, to, icon: Icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                      isActive
                        ? 'bg-surface-muted font-medium text-foreground'
                        : 'text-muted-foreground hover:bg-surface-muted hover:text-foreground',
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon className={cn('size-4 shrink-0', isActive && 'text-primary')} aria-hidden="true" />
                      {label}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

/** Always visible from the lg breakpoint up. */
function DesktopSidebar() {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-surface lg:flex">
      <div className="flex h-14 shrink-0 items-center border-b border-border px-4">
        <Brand />
      </div>
      <SidebarNav />
    </aside>
  )
}

/** Below lg: a drawer opened from the header's menu button. */
function MobileSidebar() {
  const isOpen = useUIStore((state) => state.isSidebarOpen)
  const close = useUIStore((state) => state.closeSidebar)

  useEffect(() => {
    if (!isOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isOpen, close])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
      <div className="absolute inset-0 bg-black/50" onClick={close} aria-hidden="true" />
      <aside className="relative flex h-full w-72 max-w-[85vw] flex-col border-r border-border bg-surface shadow-xl">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <Brand />
          <Button variant="ghost" size="icon" onClick={close} aria-label="Close navigation" autoFocus>
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>
        <SidebarNav onNavigate={close} />
      </aside>
    </div>
  )
}

export function Sidebar() {
  return (
    <>
      <DesktopSidebar />
      <MobileSidebar />
    </>
  )
}
