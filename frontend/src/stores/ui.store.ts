import { create } from 'zustand'

export type Theme = 'light' | 'dark'

/** Must match the key read by the pre-paint script in index.html. */
export const THEME_STORAGE_KEY = 'archonai-theme'

/** The theme already on <html>: index.html resolves the saved or system theme before first paint. */
function appliedTheme(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Storage blocked (e.g. private mode): the theme still applies for this visit.
  }
}

interface UIState {
  theme: Theme
  /** The mobile navigation drawer; on desktop the sidebar is always visible. */
  isSidebarOpen: boolean
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  openSidebar: () => void
  closeSidebar: () => void
}

export const useUIStore = create<UIState>()((set, get) => ({
  theme: appliedTheme(),
  isSidebarOpen: false,
  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },
  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),
  openSidebar: () => set({ isSidebarOpen: true }),
  closeSidebar: () => set({ isSidebarOpen: false }),
}))
