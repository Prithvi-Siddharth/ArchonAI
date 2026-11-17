import { create } from 'zustand'

import { readStorage, writeStorage } from '@/utils/storage'

export type Theme = 'light' | 'dark'

/** Must match the key read by the pre-paint script in index.html. */
export const THEME_STORAGE_KEY = 'archonai-theme'
export const SIDEBAR_COLLAPSED_STORAGE_KEY = 'archonai-sidebar-collapsed'

/** The theme already on <html>: index.html resolves the saved or system theme before first paint. */
function appliedTheme(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
  writeStorage(THEME_STORAGE_KEY, theme)
}

interface UIState {
  theme: Theme
  /** Mobile navigation drawer (below the lg breakpoint). */
  isSidebarOpen: boolean
  /** Desktop sidebar shown as an icon rail; remembered across visits. */
  isSidebarCollapsed: boolean
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  openSidebar: () => void
  closeSidebar: () => void
  toggleSidebarCollapsed: () => void
}

export const useUIStore = create<UIState>()((set, get) => ({
  theme: appliedTheme(),
  isSidebarOpen: false,
  isSidebarCollapsed: readStorage(SIDEBAR_COLLAPSED_STORAGE_KEY) === 'true',
  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },
  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),
  openSidebar: () => set({ isSidebarOpen: true }),
  closeSidebar: () => set({ isSidebarOpen: false }),
  toggleSidebarCollapsed: () => {
    const collapsed = !get().isSidebarCollapsed
    writeStorage(SIDEBAR_COLLAPSED_STORAGE_KEY, String(collapsed))
    set({ isSidebarCollapsed: collapsed })
  },
}))
