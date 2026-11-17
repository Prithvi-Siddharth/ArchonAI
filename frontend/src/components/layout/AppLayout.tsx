import { useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router'

import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useUIStore } from '@/stores/ui.store'

import { Header } from './Header'
import { findNavLocation } from './navigation'
import { Sidebar } from './Sidebar'

/** Tailwind's `lg` breakpoint (64rem), where the sidebar stops being a drawer. */
const DESKTOP_QUERY = '(min-width: 64rem)'

export function AppLayout() {
  const { pathname } = useLocation()
  const closeSidebar = useUIStore((state) => state.closeSidebar)
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
  const mainRef = useRef<HTMLElement>(null)

  useDocumentTitle(findNavLocation(pathname)?.item.label ?? 'Page not found')

  // A drawer left open on a small screen shouldn't reappear after resizing to desktop and back.
  useEffect(() => {
    if (isDesktop) closeSidebar()
  }, [isDesktop, closeSidebar])

  // <main> is the scroll container, so start each page at the top.
  useEffect(() => {
    mainRef.current?.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main ref={mainRef} className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
