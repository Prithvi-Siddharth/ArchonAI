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

/** The section and link a path belongs to, or null for an unknown path. */
export function findNavLocation(pathname: string): { section: NavSection; item: NavItem } | null {
  for (const section of NAV_SECTIONS) {
    const item = section.items.find(({ to }) => pathname === to || pathname.startsWith(`${to}/`))
    if (item) return { section, item }
  }
  return null
}
