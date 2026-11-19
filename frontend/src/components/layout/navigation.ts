import { Activity, Gauge, History, Info, KeyRound, LayoutDashboard, Settings, SquarePlus, UserRound, type LucideIcon } from 'lucide-react'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  /** Show how many of the user's jobs are in progress next to the link. */
  showActiveJobs?: boolean
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
      { label: 'Activity', to: '/activity', icon: Activity, showActiveJobs: true },
      { label: 'Monitoring', to: '/monitoring', icon: Gauge },
    ],
  },
  {
    title: 'System',
    items: [
      { label: 'Bring Your Own Key', to: '/byok', icon: KeyRound },
      { label: 'Settings', to: '/settings', icon: Settings },
    ],
  },
  {
    title: 'Help',
    items: [
      { label: 'About', to: '/about', icon: Info },
      { label: 'Creator', to: '/creator', icon: UserRound },
    ],
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
  // A job's tracking page (/architectures/{jobId}) and results page (/architectures/{jobId}/results).
  const jobPage = /^\/architectures\/([^/]+)(\/results)?\/?$/.exec(pathname)
  if (jobPage) {
    const short = decodeURIComponent(jobPage[1]).slice(0, 8)
    return { section: 'Workspace', label: jobPage[2] ? `Results ${short}` : `Job ${short}` }
  }
  if (import.meta.env.DEV) {
    const page = DEV_PAGES.find(({ to }) => matches(pathname, to))
    if (page) return { section: page.section, label: page.label }
  }
  return null
}
