import { Menu } from 'lucide-react'
import { useLocation } from 'react-router'

import { Button } from '@/components/ui'
import { useUIStore } from '@/stores/ui.store'

import { findPageMeta } from './navigation'
import { ThemeToggle } from './ThemeToggle'

export function Header() {
  const openSidebar = useUIStore((state) => state.openSidebar)
  const { pathname } = useLocation()
  const page = findPageMeta(pathname)

  return (
    <header className="flex h-header shrink-0 items-center gap-3 border-b border-border bg-surface px-4 lg:px-6">
      <Button variant="ghost" size="icon" onClick={openSidebar} aria-label="Open navigation" className="-ml-2 lg:hidden">
        <Menu className="size-4" aria-hidden="true" />
      </Button>

      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-2">
          {page && (
            <>
              <li className="hidden text-muted-foreground sm:block">{page.section}</li>
              <li className="hidden text-border-strong sm:block" aria-hidden="true">
                /
              </li>
            </>
          )}
          <li className="truncate font-medium" aria-current="page">
            {page ? page.label : 'Page not found'}
          </li>
        </ol>
      </nav>

      <ThemeToggle />
    </header>
  )
}
