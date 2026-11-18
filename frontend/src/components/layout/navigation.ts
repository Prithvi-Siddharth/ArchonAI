import { History, LayoutDashboard, Settings, SquarePlus, type LucideIcon } from 'lucide-react'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
}

export interface NavSection {
  title: string
  items: NavItem[]
}

/** The sidebar's sections and links; the header breadcrumb and tab titles come from here too. */
export const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Workspace',
    items: [
      { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard },
      { label: 'New Architecture', to: '/architectures/new', icon: SquarePlus },
      { label: 'Architecture History', to: '/architectures/history', icon: History },
    ],
  },
  {
    title: 'System',
    items: [{ label: 'Settings', to: '/settings', icon: Settings }],
  },
]

/** Development-only pages: reachable by URL, never listed in the sidebar. */
export const DEV_PAGES = [{ section: 'Development', label: 'Components', to: '/dev/components' }]

const matches = (pathname: string, to: string) => pathname === to || pathname.startsWith(`${to}/`)

/** Breadcrumb section and page label for a path, or null for an unknown path. */
export function findPageMeta(pathname: string): { section: string; label: string } | null {
  for (const section of NAV_SECTIONS) {
    const item = section.items.find(({ to }) => matches(pathname, to))
    if (item) return { section: section.title, label: item.label }
  }
  // A job's tracking page: /architectures/{jobId}.
  const jobPage = /^\/architectures\/([^/]+)\/?$/.exec(pathname)
  if (jobPage) return { section: 'Workspace', label: `Job ${decodeURIComponent(jobPage[1]).slice(0, 8)}` }
  if (import.meta.env.DEV) {
    const page = DEV_PAGES.find(({ to }) => matches(pathname, to))
    if (page) return { section: page.section, label: page.label }
  }
  return null
}
