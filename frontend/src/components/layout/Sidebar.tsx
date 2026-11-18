import { Layers, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react'
import { NavLink } from 'react-router'

import { Button, Dialog, Tooltip } from '@/components/ui'
import { useUIStore } from '@/stores/ui.store'
import { cn } from '@/utils/cn'

import { NAV_SECTIONS } from './navigation'

export function Brand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-foreground text-background">
        <Layers className="size-4" aria-hidden="true" />
      </span>
      <div className={cn('min-w-0 leading-tight', collapsed && 'sr-only')}>
        <p className="truncate text-card-title">ArchonAI</p>
        <p className="truncate text-meta text-muted-foreground">AWS architecture design</p>
      </div>
    </div>
  )
}

function SidebarNav({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex-1 space-y-6 overflow-x-hidden overflow-y-auto px-3 py-5">
      {NAV_SECTIONS.map((section) => (
        <div key={section.title}>
          {collapsed ? (
            <div className="mx-2 mb-2 border-t border-border" role="presentation" />
          ) : (
            <p className="px-3 pb-2 text-overline text-muted-foreground uppercase">{section.title}</p>
          )}
          <ul className="space-y-0.5">
            {section.items.map(({ label, to, icon: Icon }) => (
              <li key={to}>
                <Tooltip content={label} side="right" disabled={!collapsed} describeTrigger={false} className="flex w-full">
                  <NavLink
                    to={to}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'flex h-control-md w-full items-center gap-3 rounded-md text-body transition-colors',
                        collapsed ? 'justify-center' : 'px-3',
                        isActive
                          ? 'bg-surface-muted font-medium text-foreground'
                          : 'text-muted-foreground hover:bg-surface-muted hover:text-foreground',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon className={cn('size-4 shrink-0', isActive && 'text-primary')} aria-hidden="true" />
                        <span className={cn('truncate', collapsed && 'sr-only')}>{label}</span>
                      </>
                    )}
                  </NavLink>
                </Tooltip>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

/** Desktop (lg and up): full width or an icon rail; the choice is remembered. */
function DesktopSidebar() {
  const collapsed = useUIStore((state) => state.isSidebarCollapsed)
  const toggleCollapsed = useUIStore((state) => state.toggleSidebarCollapsed)
  const toggleLabel = collapsed ? 'Expand sidebar' : 'Collapse sidebar'

  return (
    <aside
      className={cn(
        'hidden shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-150 motion-reduce:transition-none lg:flex',
        collapsed ? 'w-sidebar-collapsed' : 'w-sidebar',
      )}
    >
      <div className="flex h-header shrink-0 items-center border-b border-border px-4">
        <Brand collapsed={collapsed} />
      </div>
      <SidebarNav collapsed={collapsed} />
      <div className="shrink-0 border-t border-border p-3">
        <Tooltip content={toggleLabel} side="right" disabled={!collapsed} describeTrigger={false} className="flex w-full">
          {/* Same shape as the nav links above, so the icons line up. */}
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={toggleLabel}
            className={cn(
              'flex h-control-md w-full items-center gap-3 rounded-md text-body text-muted-foreground transition-colors',
              'hover:bg-surface-muted hover:text-foreground',
              collapsed ? 'justify-center' : 'px-3',
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4 shrink-0" aria-hidden="true" />
            ) : (
              <>
                <PanelLeftClose className="size-4 shrink-0" aria-hidden="true" />
                Collapse
              </>
            )}
          </button>
        </Tooltip>
      </div>
    </aside>
  )
}

/** Below lg: a modal drawer opened from the header's menu button. */
function MobileSidebar() {
  const isOpen = useUIStore((state) => state.isSidebarOpen)
  const close = useUIStore((state) => state.closeSidebar)

  return (
    <Dialog
      open={isOpen}
      onClose={close}
      aria-label="Navigation"
      className="m-0 h-dvh max-h-none w-72 max-w-[85vw] lg:hidden"
    >
      <div className="flex h-full flex-col border-r border-border bg-surface shadow-overlay">
        <div className="flex h-header shrink-0 items-center justify-between gap-2 border-b border-border px-4">
          <Brand />
          <Button variant="ghost" size="icon" onClick={close} aria-label="Close navigation" data-autofocus>
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>
        <SidebarNav onNavigate={close} />
      </div>
    </Dialog>
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
