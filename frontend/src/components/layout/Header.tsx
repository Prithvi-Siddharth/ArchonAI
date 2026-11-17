import { Menu } from 'lucide-react'
import { useLocation } from 'react-router'

import { Button } from '@/components/ui/Button'
import { useUIStore } from '@/stores/ui.store'

import { findNavLocation } from './navigation'
import { ThemeToggle } from './ThemeToggle'

export function Header() {
  const openSidebar = useUIStore((state) => state.openSidebar)
  const { pathname } = useLocation()
  const location = findNavLocation(pathname)

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4 lg:px-6">
      <Button variant="ghost" size="icon" onClick={openSidebar} aria-label="Open navigation" className="-ml-2 lg:hidden">
        <Menu className="size-4" aria-hidden="true" />
      </Button>

      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-2 text-sm">
          {location && (
            <>
              <li className="hidden text-muted-foreground sm:block">{location.section.title}</li>
              <li className="hidden text-border-strong sm:block" aria-hidden="true">
                /
              </li>
            </>
          )}
          <li className="truncate font-medium" aria-current="page">
            {location ? location.item.label : 'Page not found'}
          </li>
        </ol>
      </nav>

      <ThemeToggle />
    </header>
  )
}
